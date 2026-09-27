# YT Transcript Extractor

A Claude Code skill that turns a YouTube video into a tidy Obsidian note.

You give it a YouTube link. It grabs the video's captions, removes repeats and filler, groups the ideas by topic, turns any tutorial into simple steps, and saves it all as a note in your Obsidian vault.

## What you need

- [Claude Code](https://claude.com/claude-code)
- Python 3.9 or newer
- The `youtube-transcript-api` package:

  ```bash
  pip install youtube-transcript-api
  ```

- An [Obsidian](https://obsidian.md) vault

## Setup

1. Copy the `.claude/skills/yt-transcript-text-extractor` folder into your project (or into `~/.claude/skills/` to use it everywhere).
2. Open `SKILL.md` and change the **Output folder** and **Script** paths to match your computer.

## How to use

Start Claude Code and ask in plain words:

```
make notes from this video: https://youtu.be/VIDEO_ID
```

Or use the slash command:

```
/yt-transcript-text-extractor https://youtu.be/VIDEO_ID
```

Got several videos? Paste all the links. You get one note per video.

## What you get

A new note in `1200 YT Transcripts/` named like `2026-09-27 - Video Title.md`, with:

- **TL;DR**: 3-5 bullet summary
- **Topics**: main ideas grouped together, with clickable timestamps
- **🛠 Tutorials**: simple numbered steps and exact commands (only for how-to videos)
- **Key Takeaways**
- **Full transcript**: cleaned up and folded away

## Tips

- **Captions are required.** If a video has no captions, it can't be used.
- **Private, age-restricted or removed videos** won't work.
- **Auto captions can mishear words.** Claude fixes obvious ones and marks unsure parts as `(unclear in video)`.

## Files

```
yt-extractor/
└── .claude/skills/yt-transcript-text-extractor/
    ├── SKILL.md                    # steps Claude follows
    ├── scripts/
    │   └── fetch_transcript.py     # downloads and cleans captions
    └── templates/
        └── note_template.md        # layout of the note
```
