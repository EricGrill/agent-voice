"""Play a WAV with whatever the host has: afplay, winsound, paplay, aplay, ffplay."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

CANDIDATES: tuple[tuple[str, list[str]], ...] = (
    ("afplay", []),
    ("paplay", []),
    ("aplay", ["-q"]),
    ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
)


def find_player() -> list[str] | None:
    """The playback argv prefix for this host, or None if nothing is installed."""
    for name, extra in CANDIDATES:
        exe = shutil.which(name)
        if exe:
            return [exe, *extra]
    return None


def rate_args(argv: list[str], rate: float) -> list[str]:
    """Extra player arguments to play ``rate`` times faster, pitch kept.

    afplay (time-pitch, high quality) and ffplay (atempo) support it; other
    players play at normal speed.
    """
    if abs(rate - 1.0) < 0.01:
        return []
    name = Path(argv[0]).name
    if name == "afplay":
        return ["-r", f"{rate:.3f}", "-q", "1"]
    if name == "ffplay":
        return ["-af", f"atempo={rate:.3f}"]
    return []


def play(path: Path, rate: float = 1.0) -> bool:
    """Play ``path`` synchronously at ``rate``; False if no player is available."""
    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME)
        return True
    argv = find_player()
    if argv is None:
        return False
    subprocess.run([*argv, *rate_args(argv, rate), str(path)], check=False)
    return True
