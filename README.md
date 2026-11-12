# agent-voice

**Give any LLM agent a cloned voice.** The agent's reply goes in; one
in-character spoken line comes out of your speakers in a voice cloned from a
3–10 second clip.

```sh
my-agent --reply | agent-voice pipe --voice skippy
```

```
[writer/omnivoice] Parser is fixed and all forty-one tests pass, Rico. You can stop hovering now.
```

The tag in front is `[<how the line was chosen>/<engine that spoke it>]`.

- **Two channels.** The screen keeps the full technical reply. The speaker
  gets one line — either the agent tags it (`<say>...</say>`) or a small
  "writer" model reads the reply and decides what the character would say.
- **Any agent, any language.** A CLI, a stdin pipe, and a tiny HTTP server
  (`POST /say`). Nothing to import unless you want to.
- **Optional ElevenLabs.** Give a voice an ElevenLabs voice ID and a key, and
  ElevenLabs speaks it, falling back to OmniVoice if the call fails.
- **Any OmniVoice server.** Speaks the `/health` + `/synthesize` contract used
  by [scorbo2/ai-playground](https://github.com/scorbo2/ai-playground/tree/master/TTS)
  and [TalkWithMe](https://github.com/scorbo2/TalkWithMe). If you already run
  one, it works unchanged.
- **Small.** Python 3.11+, one dependency (`httpx`), standard-library HTTP
  server, ~650 lines, 27 tests, mypy strict.

It grew out of a Claude Code session that wanted to talk as
[Skippy](https://expeditionaryforce.fandom.com/wiki/Skippy) without a browser
in the loop.

## Quick start

```sh
git clone https://github.com/rodaddy/agent-voice.git
cd agent-voice
sh install.sh --demo          # venv, install, demo voice (macOS), then a report
```

Then edit `agent-voice.env` (it's created for you) so `AGENT_VOICE_TTS_URL`
points at your OmniVoice server, and:

```sh
.venv/bin/agent-voice doctor                          # everything green?
.venv/bin/agent-voice speak --voice demo "It works."  # hear it
```

`doctor` names every missing piece and the fix for it. The full walkthrough —
including standing up the OmniVoice server, making a real voice, and picking a
writer model — is in **[INSTALL.md](INSTALL.md)**.

## The three doors

| You have... | Use | Example |
|---|---|---|
| A string | `agent-voice speak` | `agent-voice speak --voice skippy "Build is green."` |
| An agent's reply on stdout | `agent-voice pipe` | `my-agent \| agent-voice pipe --voice skippy` |
| Anything that can POST JSON | `agent-voice serve` | `curl localhost:7161/say -d '{"text":"...","voice":"skippy"}'` |

## How the spoken line is chosen

`pipe` and `POST /say` take a whole reply and pick what to say (`--mode auto`):

1. **`<say>` tag.** If the agent wrote `<say>One spoken line.</say>`, exactly
   that is spoken. Tags quoted inside code spans are ignored, so an agent can
   *talk about* the tag safely. Tell your agent: *"End every reply with one
   spoken line wrapped as `<say>...</say>`: one or two short sentences, in
   character, plain words only."*
2. **Writer model.** Otherwise, if `AGENT_VOICE_LLM_URL` is set, the reply is
   sent to that OpenAI-compatible model together with the voice's `persona.md`,
   and the model answers with one or two sentences in character (capped at
   `AGENT_VOICE_MAX_WORDS`, never cut mid-sentence). A small local model is
   plenty — a 9B on a laptop writes the line in ~2.5 s.
3. **Direct.** Otherwise the text itself is spoken, markup stripped.

`--mode tag|writer|direct` forces one of them. Utterances are serialized, so
two agents talking at once take turns instead of overlapping.

## Voices

A voice is a directory. Make as many as you like.

```
voices/skippy/
  ref.wav        3-10 s of the voice, mono, 24 kHz  (longer is slower and no better)
  ref.txt        the exact words spoken in ref.wav
  language.txt   optional, default "English"
  persona.md     optional: who this voice IS -- the writer model speaks as this
  elevenlabs.txt optional: an ElevenLabs voice ID (see below)
```

## ElevenLabs (optional)

A voice can be spoken by [ElevenLabs](https://elevenlabs.io) instead of your
OmniVoice server. Both are needed:

1. **A voice ID** in `voices/<name>/elevenlabs.txt` (just the ID; surrounding
   whitespace is ignored). In ElevenLabs, add the voice to **My Voices**, then
   use **Copy voice ID** from its menu.
2. **An API key** in `AGENT_VOICE_ELEVENLABS_API_KEY`. A key with
   text-to-speech access is enough.

| Variable | Default | Meaning |
|---|---|---|
| `AGENT_VOICE_ELEVENLABS_API_KEY` | (unset) | ElevenLabs API key; unset or empty = OmniVoice only |
| `AGENT_VOICE_ELEVENLABS_MODEL` | `eleven_flash_v2_5` | any ElevenLabs TTS `model_id` |

How it behaves:

- **Which engine.** ElevenLabs speaks when the key is set **and** the voice has
  an `elevenlabs.txt`. Every other voice, and every voice when no key is set,
  goes to OmniVoice as before. You can mix both in one library.
- **Request.** `POST https://api.elevenlabs.io/v1/text-to-speech/<voice id>`
  with `output_format=pcm_24000`; the raw 24 kHz mono 16-bit PCM that comes
  back is wrapped in a WAV header, so playback and `out/` work the same for
  both engines. Timeout 30 s.
- **Fallback.** If the call fails (any HTTP error status such as a bad key,
  unknown voice or exhausted quota, a timeout, or no network), agent-voice
  prints `elevenlabs failed: <first 200 chars of the reply>; using OmniVoice`
  to stderr and speaks the line with the voice's `ref.wav` through OmniVoice.
  The line is never lost to an ElevenLabs outage, which is why a voice
  **still needs `ref.wav` and `ref.txt`**: without them it is not a voice at
  all. If OmniVoice is down too, the error is raised as usual.
- **Seeing which engine spoke.** `pipe` prints `[tag/elevenlabs] ...` or
  `[tag/omnivoice] ...`; `Spoken.engine` and the Python API say the same.
  A run of `omnivoice` with no `elevenlabs failed` line means no key reached
  the process or the voice has no `elevenlabs.txt`.
- **Keys.** ElevenLabs keys are 51 characters (`sk_` + 48). A truncated
  paste is rejected with `invalid_api_key_length`. Keep the key in your
  environment or a secrets manager rather than in `agent-voice.env`, and
  never commit it.
- **Cost.** Only the chosen line is sent (one or two sentences, ~100
  characters). Flash v2.5 is ElevenLabs' cheapest model; check your plan's
  per-character price and usage page.
- **Voices you may use.** Use premade, Voice Library or your own designed
  voices. Do not clone a real person's voice without their consent; that
  breaks ElevenLabs' terms.

## Making a voice

`examples/make-voice-macos.sh voices/demo` builds a throwaway voice from the
macOS `say` command. `examples/persona-ship-ai.md` is a starting persona.
Cutting a real clip from a recording is in [INSTALL.md](INSTALL.md#3-make-a-voice).

## HTTP server

```sh
agent-voice serve                       # http://127.0.0.1:7161
curl -s localhost:7161/health
curl -s localhost:7161/say -H 'content-type: application/json' \
  -d '{"text": "Deployed.\n<say>It is live. Try not to break it.</say>", "voice": "skippy"}'
```

```json
{"spoken": "It is live. Try not to break it.", "wav": "out/skippy-20260828T025959Z.wav", "voice": "skippy", "source": "tag", "engine": "omnivoice"}
```

`POST /say` takes `text`, optional `voice`, optional `mode`; answers `204` when
there was nothing to say, `404` for an unknown voice, `502` if the TTS or
writer failed.

## Python

```python
from agent_voice import Config, Speaker

speaker = Speaker(Config.from_env())
spoken = speaker.speak(agent_reply, "skippy")   # Spoken(text, wav, voice, source, engine) or None
```

## Configuration

Environment variables, or the same names in `agent-voice.env` in the working
directory (the environment wins). `agent-voice doctor` shows what is in effect.

| Variable | Default | Meaning |
|---|---|---|
| `AGENT_VOICE_TTS_URL` | `http://127.0.0.1:8181` | OmniVoice server (scorbo2's runs on 8181) |
| `AGENT_VOICE_VOICES_DIR` | `voices` | the voice library |
| `AGENT_VOICE_VOICE` | first voice | default voice name |
| `AGENT_VOICE_LLM_URL` | (unset) | OpenAI-compatible base URL of the writer; unset = no writer |
| `AGENT_VOICE_LLM_MODEL` | | writer model id |
| `AGENT_VOICE_LLM_API_KEY` | | sent as `Authorization: Bearer` if set |
| `AGENT_VOICE_ELEVENLABS_API_KEY` | (unset) | ElevenLabs key; unset = OmniVoice only ([ElevenLabs](#elevenlabs-optional)) |
| `AGENT_VOICE_ELEVENLABS_MODEL` | `eleven_flash_v2_5` | ElevenLabs model |
| `AGENT_VOICE_NUM_STEPS` | `10` | OmniVoice diffusion steps (10–20 on scorbo2's server) |
| `AGENT_VOICE_GUIDANCE_SCALE` | `1.2` | |
| `AGENT_VOICE_MAX_WORDS` | `35` | cap on a writer-produced line |
| `AGENT_VOICE_OUT_DIR` | `out` | where WAVs are saved |
| `AGENT_VOICE_PLAY` | `true` | `false` to only save the WAV |
| `AGENT_VOICE_HOST` / `_PORT` | `127.0.0.1` / `7161` | for `agent-voice serve` |

## Integrations

- **[Claude Code](integrations/claude-code/)** — two hooks and a toggle make a
  Claude Code session speak each reply (where this tool came from).
- **Anything else** needs only a way to run `agent-voice pipe` with the reply
  on stdin, or to POST the reply to `/say`. Shell agents, LangChain callbacks,
  cron jobs, CI notifications — all the same three lines.

## Commands

```
agent-voice speak  [--voice NAME] TEXT           say exactly this
agent-voice pipe   [--voice NAME] [--mode M]     reply on stdin -> spoken line
agent-voice serve                                HTTP: POST /say, GET /health
agent-voice voices                               list the library
agent-voice health                               TTS + library as JSON
agent-voice doctor                               what's missing, and the fix
```

`--no-play` before the subcommand saves the WAV without playing it.

## Development

```sh
sh install.sh --dev
.venv/bin/pytest && .venv/bin/ruff check && .venv/bin/ruff format --check && .venv/bin/mypy
```

See [CONTRIBUTING.md](CONTRIBUTING.md). MIT licensed.
