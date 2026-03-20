#!/usr/bin/env python3
# /// script
# dependencies = ["pyyaml"]
# requires-python = ">=3.9"
# ///
"""Claude Code Sound Hook - plays sound clips on hook events.

Usage: uv run sound_hook.py [config_path]
Reads hook event JSON from stdin.
"""

import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import yaml

PLAYER_CMDS = {
    "afplay": lambda f: ["afplay", f],
    "mpv": lambda f: ["mpv", "--no-video", "--really-quiet", f],
    "ffplay": lambda f: ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", f],
    "paplay": lambda f: ["paplay", f],
    "aplay": lambda f: ["aplay", "-q", f],
}
PLAYER_ORDER = ["afplay", "mpv", "ffplay", "paplay", "aplay"]
DEVNULL = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
_IS_MACOS = sys.platform == "darwin"
_MAX_LOOP_SECS = (
    120  # Safety timeout: self-terminate after 2 min if Stop event never fires
)
_MACOS_LOOP_JS = """
ObjC.import('AVFoundation');
ObjC.import('Foundation');
function run(argv) {
    var url = $.NSURL.fileURLWithPath(argv[0]);
    var loops = parseInt(argv[1]);
    var maxSecs = parseFloat(argv[2]);
    var err = Ref();
    var p = $.AVAudioPlayer.alloc.initWithContentsOfURLError(url, err);
    if (!p) $.exit(1);
    p.numberOfLoops = loops;
    p.play;
    var deadline = $.NSDate.dateWithTimeIntervalSinceNow(maxSecs);
    while (p.playing && $.NSDate.date.compare(deadline) < 0) {
        $.NSRunLoop.currentRunLoop.runUntilDate($.NSDate.dateWithTimeIntervalSinceNow(1));
    }
}
"""


def detect_player(cfg: str) -> str | None:
    if cfg != "auto" and shutil.which(cfg):
        return cfg
    for p in PLAYER_ORDER:
        if shutil.which(p):
            return p
    return None


def play_cmd_str(player: str, sound_file: str) -> str:
    """Build a shell command string for use in bash -c loops."""
    parts = PLAYER_CMDS[player](sound_file)
    return " ".join(shlex.quote(p) for p in parts)


def stop_until(event: str, pid_dir: Path) -> None:
    for until_file in pid_dir.glob("*.until"):
        if until_file.read_text().strip() != event:
            continue
        pid_file = until_file.with_suffix(".pid")
        if pid_file.exists():
            try:
                os.killpg(int(pid_file.read_text().strip()), signal.SIGTERM)
            except (ProcessLookupError, ValueError, PermissionError):
                pass
            pid_file.unlink(missing_ok=True)
        until_file.unlink(missing_ok=True)


def spawn_loop(
    cmd_str: str,
    pid_dir: Path,
    event: str,
    until: str = "",
    native_cmd: list[str] | None = None,
) -> None:
    if native_cmd:
        proc = subprocess.Popen(native_cmd, start_new_session=True, **DEVNULL)
    else:
        proc = subprocess.Popen(
            ["bash", "-c", f"while true; do {cmd_str}; done"],
            start_new_session=True,
            **DEVNULL,
        )
    (pid_dir / f"{event}.pid").write_text(str(proc.pid))
    if until:
        (pid_dir / f"{event}.until").write_text(until)


def main() -> None:
    config_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get(
            "SOUND_HOOK_CONFIG",
            str(Path.home() / ".claude" / "sound_hook_config.yaml"),
        )
    )
    config_path = Path(config_path).expanduser()

    if not config_path.is_file():
        sys.exit(0)

    try:
        input_data = json.load(sys.stdin)
        event = input_data.get("hook_event_name", "")
        session_id = input_data.get("session_id", "default")
    except Exception:
        sys.exit(0)

    if not event:
        sys.exit(0)

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    except Exception:
        sys.exit(0)

    pid_dir = Path(f"/tmp/claude-sound-hooks/{session_id}")
    pid_dir.mkdir(parents=True, exist_ok=True)

    # Stop any loops whose "until" matches this event
    stop_until(event, pid_dir)

    # Look up config for this event
    entry = config.get(event)
    if not isinstance(entry, dict):
        sys.exit(0)

    sound_file = entry.get("sound_file", "")
    if not sound_file:
        sys.exit(0)
    sound_file = os.path.expanduser(sound_file)
    if not os.path.isfile(sound_file):
        sys.exit(0)

    loop = entry.get("loop", False)
    repeat = entry.get("repeat", 0)
    until = entry.get("until", "")
    player_cfg = config.get("player", "auto")
    player = detect_player(player_cfg)
    if not player:
        sys.exit(0)

    cmd_str = play_cmd_str(player, sound_file)

    # Prefer native gapless looping when available
    native_loop_cmd = None
    if _IS_MACOS:
        native_loop_cmd = [
            "osascript",
            "-l",
            "JavaScript",
            "-e",
            _MACOS_LOOP_JS,
            "--",
            sound_file,
            "-1",
        ]
    elif player == "mpv":
        native_loop_cmd = [
            "mpv",
            "--no-video",
            "--really-quiet",
            "--loop-file=inf",
            sound_file,
        ]
    elif player == "ffplay":
        native_loop_cmd = [
            "ffplay",
            "-nodisp",
            "-loglevel",
            "quiet",
            "-loop",
            "0",
            sound_file,
        ]

    # loop: false → play once
    if not loop:
        subprocess.Popen(
            PLAYER_CMDS[player](sound_file),
            start_new_session=True,
            **DEVNULL,
        )
        sys.exit(0)

    # loop: true + until → loop until that event fires
    if until:
        spawn_loop(cmd_str, pid_dir, event, until, native_cmd=native_loop_cmd)
        sys.exit(0)

    # loop: true + repeat → play N times
    if repeat and int(repeat) > 0:
        n = int(repeat)
        native_repeat = None
        if _IS_MACOS:
            native_repeat = [
                "osascript",
                "-l",
                "JavaScript",
                "-e",
                _MACOS_LOOP_JS,
                "--",
                sound_file,
                str(n - 1),
            ]
        elif player == "mpv":
            native_repeat = [
                "mpv",
                "--no-video",
                "--really-quiet",
                f"--loop-file={n}",
                sound_file,
            ]
        if native_repeat:
            subprocess.Popen(native_repeat, start_new_session=True, **DEVNULL)
        else:
            subprocess.Popen(
                ["bash", "-c", f"for i in $(seq 1 {n}); do {cmd_str}; done"],
                start_new_session=True,
                **DEVNULL,
            )
        sys.exit(0)

    # loop: true, no until, no repeat → loop forever
    spawn_loop(cmd_str, pid_dir, event, native_cmd=native_loop_cmd)


if __name__ == "__main__":
    main()
