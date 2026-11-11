import io
import wave
from pathlib import Path

import httpx

from agent_voice.config import Config
from agent_voice.speaker import Speaker
from agent_voice.tts import ElevenLabsTTS
from agent_voice.voices import load_voice
from tests.conftest import fake_tts

PCM = b"\x01\x00" * 2400  # 0.1 s of 24 kHz mono 16-bit audio


def fake_eleven(calls: list[httpx.Request], status: int = 200) -> httpx.MockTransport:
    def handle(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if status != 200:
            return httpx.Response(status, json={"detail": "nope"})
        return httpx.Response(200, content=PCM)

    return httpx.MockTransport(handle)


def eleven_config(config: Config) -> Config:
    return Config(**{**config.__dict__, "llm_url": "", "elevenlabs_api_key": "k"})


def test_voice_reads_elevenlabs_id(library: Path) -> None:
    assert load_voice(library, "alpha").elevenlabs_voice_id == ""
    (library / "alpha" / "elevenlabs.txt").write_text("voice123\n")
    assert load_voice(library, "alpha").elevenlabs_voice_id == "voice123"


def test_elevenlabs_returns_wav() -> None:
    calls: list[httpx.Request] = []
    wav = ElevenLabsTTS("k", transport=fake_eleven(calls)).synthesize("Hi.", "v1")
    req = calls[0]
    assert req.url.path == "/v1/text-to-speech/v1"
    assert req.url.params["output_format"] == "pcm_24000"
    assert req.headers["xi-api-key"] == "k"
    with wave.open(io.BytesIO(wav)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (24000, 1, 2)
        assert w.readframes(w.getnframes()) == PCM


def test_speaker_prefers_elevenlabs(config: Config, library: Path) -> None:
    (library / "alpha" / "elevenlabs.txt").write_text("voice123")
    omni: list[dict] = []
    eleven: list[httpx.Request] = []
    s = Speaker(
        eleven_config(config),
        tts_transport=fake_tts(omni),
        eleven_transport=fake_eleven(eleven),
    )
    spoken = s.speak("<say>Hello.</say>")
    assert spoken is not None and spoken.engine == "elevenlabs"
    assert len(eleven) == 1 and omni == []


def test_speaker_falls_back_to_omnivoice(config: Config, library: Path) -> None:
    (library / "alpha" / "elevenlabs.txt").write_text("voice123")
    omni: list[dict] = []
    eleven: list[httpx.Request] = []
    s = Speaker(
        eleven_config(config),
        tts_transport=fake_tts(omni),
        eleven_transport=fake_eleven(eleven, status=401),
    )
    spoken = s.speak("<say>Hello.</say>")
    assert spoken is not None and spoken.engine == "omnivoice"
    assert len(eleven) == 1 and omni[0]["text"] == "Hello."


def test_no_key_means_omnivoice(config: Config, library: Path) -> None:
    (library / "alpha" / "elevenlabs.txt").write_text("voice123")
    omni: list[dict] = []
    eleven: list[httpx.Request] = []
    s = Speaker(
        Config(**{**config.__dict__, "llm_url": ""}),
        tts_transport=fake_tts(omni),
        eleven_transport=fake_eleven(eleven),
    )
    spoken = s.speak("<say>Hello.</say>")
    assert spoken is not None and spoken.engine == "omnivoice" and eleven == []
