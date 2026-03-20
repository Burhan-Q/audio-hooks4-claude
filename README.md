# Claude Code Sound Hook

Play sound clips in response to Claude Code hook events.

## Requirements

- [uv](https://docs.astral.sh/uv/) (runs the script with inline dependencies)
- An audio player: `afplay` (macOS, built-in), `mpv`, `ffplay`, `paplay`, or `aplay`

## Setup

### 1. Place the files

Put `sound_hook.py` and `sound_hook_config.yaml` somewhere accessible (e.g., `~/Documents/_code/`).

### 2. Register hooks in Claude Code settings

Add hook entries to `~/.claude/settings.json` for each event you want to handle. Every event needs its own entry pointing to the same script:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "uv run /path/to/sound_hook.py /path/to/sound_hook_config.yaml"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "uv run /path/to/sound_hook.py /path/to/sound_hook_config.yaml"
          }
        ]
      }
    ]
  }
}
```

Register **all** events you plan to use in the YAML config, plus any events referenced by `until` (e.g., if you loop `until: Stop`, the `Stop` event must also be registered as a hook).

### 3. Configure sounds

Edit `sound_hook_config.yaml` to map events to sound files:

```yaml
player: auto  # auto | afplay | mpv | ffplay | paplay | aplay

UserPromptSubmit:
  sound_file: ~/sounds/thinking.mp3
  loop: true
  until: Stop

Stop:
  sound_file: ~/sounds/done.mp3
```

## Configuration Reference

Each top-level key in the YAML is a hook event name with these options:

| Option       | Type    | Default | Description                                      |
|--------------|---------|---------|--------------------------------------------------|
| `sound_file` | string  | —       | **Required.** Path to the audio file (`~` ok).   |
| `loop`       | bool    | `false` | Enable looping.                                  |
| `repeat`     | int     | `0`     | Play N times (only with `loop: true`, no `until`).|
| `until`      | string  | —       | Stop looping when this event fires.              |

### Playback modes

| Config                              | Behavior                          |
|-------------------------------------|-----------------------------------|
| `loop: false` (default)             | Play once                         |
| `loop: true` + `until: EventName`   | Loop until that event fires       |
| `loop: true` + `repeat: N`          | Play exactly N times              |
| `loop: true` (no `until`/`repeat`)  | Loop forever                      |

### Available events

`SessionStart`, `InstructionsLoaded`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `PermissionRequest`, `Notification`, `SubagentStart`, `SubagentStop`, `Stop`, `StopFailure`, `TeammateIdle`, `TaskCompleted`, `ConfigChange`, `WorktreeCreate`, `WorktreeRemove`, `PreCompact`, `PostCompact`, `Elicitation`, `ElicitationResult`, `SessionEnd`

## Safety timeout

Looping sounds self-terminate after 2 minutes if the expected stop event never fires (e.g., if Claude Code crashes). This is configured via `_MAX_LOOP_SECS` in `sound_hook.py`.

## Gapless looping

On macOS, looping uses `AVAudioPlayer` via JavaScript for Automation for gapless playback. On other platforms, `mpv --loop-file` and `ffplay -loop` are used when available, with a `bash` while-loop as a fallback.

## Troubleshooting

**No sound plays:** Verify the sound file path exists and that `uv` is on your PATH. Test manually:
```bash
echo '{"hook_event_name":"Stop","session_id":"test"}' | uv run /path/to/sound_hook.py /path/to/sound_hook_config.yaml
```

**Sound won't stop:** Find and kill the orphaned process:
```bash
ps aux | grep -E 'osascript.*AVFoundation|afplay' | grep -v grep
kill <PID>
```

**Loop has audible gaps (non-macOS):** Install `mpv` for native gapless looping support.
