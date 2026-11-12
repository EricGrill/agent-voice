import io
import json
import wave
from pathlib import Path

import httpx

from agent_voice.config import Config
from agent_voice.play import rate_args
from agent_voice.speaker import Speaker
from agent_voice.tts import ElevenLabsTTS, split_speed
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


def test_speed_sent_and_clamped() -> None:
    calls: list[httpx.Request] = []
    tts = ElevenLabsTTS("k", transport=fake_eleven(calls))
    tts.synthesize("Hi.", "v1")
    tts.synthesize("Hi.", "v1", 1.15)
    tts.synthesize("Hi.", "v1", 3.0)
    bodies = [json.loads(c.content) for c in calls]
    assert "voice_settings" not in bodies[0]
    assert bodies[1]["voice_settings"] == {"speed": 1.15}
    assert bodies[2]["voice_settings"] == {"speed": 1.2}


def test_voice_speed_overrides_config(config: Config, library: Path) -> None:
    (library / "alpha" / "elevenlabs.txt").write_text("voice123")
    (library / "alpha" / "speed.txt").write_text("0.9\n")
    eleven: list[httpx.Request] = []
    cfg = Config(**{**eleven_config(config).__dict__, "speed": 1.2})
    s = Speaker(cfg, tts_transport=fake_tts([]), eleven_transport=fake_eleven(eleven))
    s.speak("<say>Hello.</say>")
    assert json.loads(eleven[0].content)["voice_settings"] == {"speed": 0.9}


def test_split_speed() -> None:
    assert split_speed(1.0, "elevenlabs") == (1.0, 1.0)
    assert split_speed(1.1, "elevenlabs") == (1.1, 1.0)
    synth, rate = split_speed(1.5, "elevenlabs")
    assert synth == 1.2 and abs(rate - 1.25) < 1e-9
    assert split_speed(0.6, "elevenlabs") == (0.7, 0.6 / 0.7)
    assert split_speed(1.5, "omnivoice") == (1.0, 1.5)
    assert split_speed(5.0, "omnivoice") == (1.0, 2.0)


def test_rate_args() -> None:
    assert rate_args(["/usr/bin/afplay"], 1.0) == []
    assert rate_args(["/usr/bin/afplay"], 1.25) == ["-r", "1.250", "-q", "1"]
    assert rate_args(["/x/ffplay", "-nodisp"], 1.5) == ["-af", "atempo=1.500"]
    assert rate_args(["/usr/bin/paplay"], 1.5) == []
