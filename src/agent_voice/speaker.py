"""The Speaker: text in, persona line chosen, voice synthesized, audio played."""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx

from agent_voice.config import Config
from agent_voice.play import play
from agent_voice.tags import spoken_line, strip_markup
from agent_voice.tts import TTS, ElevenLabsTTS
from agent_voice.voices import Voice, list_voices, load_voice
from agent_voice.writer import Writer

Mode = Literal["auto", "tag", "writer", "direct"]
DIRECT_MAX_CHARS = 600


@dataclass(frozen=True)
class Spoken:
    """What was said and where the audio went."""

    text: str
    wav: Path
    voice: str
    source: str  # "tag" | "writer" | "direct"
    engine: str = "omnivoice"  # "omnivoice" | "elevenlabs"


class Speaker:
    """Chooses the line, synthesizes it, and plays it -- one utterance at a time."""

    def __init__(
        self,
        config: Config,
        *,
        tts_transport: httpx.BaseTransport | None = None,
        llm_transport: httpx.BaseTransport | None = None,
        eleven_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self.tts = TTS(
            config.tts_url,
            num_steps=config.num_steps,
            guidance_scale=config.guidance_scale,
            transport=tts_transport,
        )
        self.eleven = (
            ElevenLabsTTS(
                config.elevenlabs_api_key,
                model=config.elevenlabs_model,
                transport=eleven_transport,
            )
            if config.elevenlabs_api_key
            else None
        )
        self.writer = (
            Writer(
                config.llm_url,
                config.llm_model,
                api_key=config.llm_api_key,
                max_words=config.max_words,
                transport=llm_transport,
            )
            if config.has_writer
            else None
        )
        self._lock = threading.Lock()  # never talk over yourself

    def voices(self) -> list[str]:
        """Names in the library."""
        return list_voices(self.config.voices_dir)

    def choose(
        self, text: str, voice: Voice, mode: Mode = "auto"
    ) -> tuple[str, str] | None:
        """Pick the line to speak: ``(line, source)`` or None for silence."""
        tagged = spoken_line(text)
        if mode in ("auto", "tag") and tagged:
            return tagged, "tag"
        if mode == "tag":
            return None
        if mode in ("auto", "writer") and self.writer is not None:
            line = self.writer.line_for(text, voice.persona)
            return (line, "writer") if line else None
        if mode == "writer":
            return None
        plain = strip_markup(text)[:DIRECT_MAX_CHARS]
        return (plain, "direct") if plain else None

    def speak(
        self,
        text: str,
        voice_name: str = "",
        mode: Mode = "auto",
        *,
        play_audio: bool | None = None,
    ) -> Spoken | None:
        """Speak ``text`` (per ``mode``) in ``voice_name``; return what was said."""
        voice = load_voice(self.config.voices_dir, voice_name or self.config.voice)
        chosen = self.choose(text, voice, mode)
        if chosen is None:
            return None
        line, source = chosen
        with self._lock:
            wav, engine = self._synthesize(line, voice)
            path = self._save(wav, voice.name)
            should_play = self.config.play if play_audio is None else play_audio
            if should_play and play(path):
                path.unlink()
        return Spoken(
            text=line, wav=path, voice=voice.name, source=source, engine=engine
        )

    def _synthesize(self, line: str, voice: Voice) -> tuple[bytes, str]:
        """ElevenLabs when this voice has an id and a key is set; else OmniVoice."""
        if self.eleven is not None and voice.elevenlabs_voice_id:
            try:
                speed = voice.speed or self.config.elevenlabs_speed
                return self.eleven.synthesize(
                    line, voice.elevenlabs_voice_id, speed
                ), "elevenlabs"
            except httpx.HTTPError as e:
                why = (
                    e.response.text[:200] if isinstance(e, httpx.HTTPStatusError) else e
                )
                print(f"elevenlabs failed: {why}; using OmniVoice", file=sys.stderr)
        return self.tts.synthesize(line, voice), "omnivoice"

    def _save(self, wav: bytes, voice: str) -> Path:
        self.config.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        path = self.config.out_dir / f"{voice}-{stamp}.wav"
        path.write_bytes(wav)
        return path
