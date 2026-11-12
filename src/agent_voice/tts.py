"""Client for the OmniVoice REST contract (``/health`` + ``/synthesize``).

The contract is the one used by scorbo2's ``server_omnivoice.py`` and
TalkWithMe: POST ``/synthesize`` with the reference clip as base64 WAV and its
transcript, get the synthesized WAV back as base64.
"""

from __future__ import annotations

import base64
import io
import wave
from typing import Any

import httpx

from agent_voice.voices import Voice


class TTS:
    """One TTS server."""

    def __init__(
        self,
        base_url: str,
        *,
        num_steps: int = 10,
        guidance_scale: float = 1.2,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.num_steps = num_steps
        self.guidance_scale = guidance_scale
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def health(self) -> dict[str, Any] | None:
        """``GET /health`` as a dict, or None if the server is unreachable."""
        try:
            r = self._client.get(f"{self.base_url}/health", timeout=5.0)
            r.raise_for_status()
            data: dict[str, Any] = r.json()
        except (httpx.HTTPError, ValueError):
            return None
        return data

    def synthesize(self, text: str, voice: Voice) -> bytes:
        """Return ``text`` spoken in ``voice`` as WAV bytes."""
        body = {
            "text": text,
            "audio_base64": base64.b64encode(voice.ref_audio.read_bytes()).decode(),
            "prompt_text": voice.ref_text,
            "language": voice.language,
            "num_steps": self.num_steps,
            "guidance_scale": self.guidance_scale,
        }
        r = self._client.post(f"{self.base_url}/synthesize", json=body)
        r.raise_for_status()
        return base64.b64decode(r.json()["audio_base64"])


class ElevenLabsTTS:
    """ElevenLabs text-to-speech: POST text, get 24 kHz PCM, return it as WAV."""

    BASE_URL = "https://api.elevenlabs.io"
    SAMPLE_RATE = 24000

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "eleven_flash_v2_5",
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={"xi-api-key": api_key},
            timeout=timeout,
            transport=transport,
        )

    MIN_SPEED, MAX_SPEED = 0.7, 1.2  # ElevenLabs' allowed speaking-rate range

    def synthesize(self, text: str, voice_id: str, speed: float = 1.0) -> bytes:
        """Return ``text`` spoken by ElevenLabs voice ``voice_id`` as WAV bytes.

        ``speed`` is clamped to 0.7-1.2; 1.0 sends no voice settings at all, so
        the voice keeps its stored defaults.
        """
        body: dict[str, object] = {"text": text, "model_id": self.model}
        speed = min(max(speed, self.MIN_SPEED), self.MAX_SPEED)
        if speed != 1.0:
            body["voice_settings"] = {"speed": speed}
        r = self._client.post(
            f"/v1/text-to-speech/{voice_id}",
            params={"output_format": f"pcm_{self.SAMPLE_RATE}"},
            json=body,
        )
        r.raise_for_status()
        return pcm_to_wav(r.content, self.SAMPLE_RATE)


def pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw mono 16-bit little-endian PCM in a WAV header."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()
