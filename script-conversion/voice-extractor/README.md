# Voice Extractor

A Claude Code skill that turns a voice memo into a tidy Obsidian note.

You give it an audio file. It writes down what you said, sums it up, pulls out your to-dos, and saves it all as a note in your Obsidian vault.

## What you need

- [Claude Code](https://claude.com/claude-code)
- Python 3.9 or newer
- The `faster-whisper` package:

  ```bash
  pip install faster-whisper
  ```

- An [Obsidian](https://obsidian.md) vault

## Setup

1. Copy the `.claude/skills/voice-extract` folder into your project (or into `~/.claude/skills/` to use it everywhere).
2. Open `SKILL.md` and change the **Vault** path to your own Obsidian vault folder.

## How to use

Start Claude Code and ask in plain words:

```
Transcribe my voice memo C:\Users\me\Downloads\idea.m4a
```

Don't have the path handy? Say "turn my latest voice note into notes" and Claude will look in Downloads and Desktop, then ask you to confirm.

Supported files: `.m4a`, `.mp3`, `.wav`, `.ogg`, `.opus`, `.aac`, `.flac`

## What you get

A new note in `1100 Voice Memos/` named like `2026-09-27 My Great Idea.md`, with:

- **Summary**: 2-3 sentences
- **Key Points**: the main ideas
- **Action Items**: checkboxes for any tasks you mentioned
- **Transcript**: full text with `[MM:SS]` timestamps

A link to the note is also added to `1100 Voice Memos/_Index.md`.

## Tips

- **First run is slow.** It downloads the speech model once (about 500 MB).
- **Not in English?** Say what language it is, e.g. "it's in Tagalog".
- **Transcript has mistakes?** Ask Claude to use the `medium` model. It's slower but more accurate.

## Files

```
voice-extractor/
└── .claude/skills/voice-extract/
    ├── SKILL.md            # steps Claude follows
    └── scripts/
        └── transcribe.py   # turns audio into text
```
