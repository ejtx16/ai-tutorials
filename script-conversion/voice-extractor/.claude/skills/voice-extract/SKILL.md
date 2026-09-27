---
name: voice-extract
description: Transcribe a voice memo / voice note / audio recording, analyze it (summary, key points, action items), and file a structured note into the Obsidian knowledge base. Use when the user mentions a voice memo, voice note, audio recording, transcribing audio, or turning speech into notes.
---

# Voice Extract → Obsidian Knowledge Base

Turn a voice memo into a structured Obsidian note.

## Configuration

- Vault: `C:\Users\Earllie James\OneDrive\Documents\Obsidian Vault`
- Notes folder inside vault: `1100 Voice Memos`
- Index note: `1100 Voice Memos\_Index.md`
- Transcription script: `scripts/transcribe.py` (relative to this skill's folder)

## Steps

### 1. Locate the audio

Use the file path(s) the user provided. If none given, look for recently modified audio files (`*.m4a`, `*.mp3`, `*.wav`, `*.ogg`, `*.opus`, `*.aac`, `*.flac`) in Downloads and Desktop, and confirm the candidate with the user before transcribing.

### 2. Transcribe

```powershell
python "<this-skill-folder>\scripts\transcribe.py" "<audio-path>"
```

(`<this-skill-folder>` = the directory containing this SKILL.md.)

Prints JSON: `{"language", "duration", "segments": [{"start", "end", "text"}]}`.
Progress messages go to stderr. First ever run downloads the model (one-time, ~500MB) — this can take a few minutes; use a generous timeout or run in background.

Optional `--model tiny|base|small|medium|large-v3` (default `small`). Suggest `medium` only if the user complains about accuracy.
Optional `--language <code>|auto` (default `en`). Use `auto` if the memo is not in English, or a specific code (e.g. `tl`) if known.

### 3. Analyze

From the transcript text (you do this yourself — no extra tools):

- **Summary**: 2-3 sentences capturing what the memo is about.
- **Key Points**: bulleted main ideas, concrete and specific.
- **Action Items**: any tasks/intentions spoken in the memo as `- [ ]` checkboxes. Omit the section entirely if there are none.
- **Title**: derive a 3-6 word title from the content (filename-safe: no `\ / : * ? " < > |`).

### 4. Write the note

Path: `<vault>\1100 Voice Memos\YYYY-MM-DD <title>.md` (today's date; if that file already exists, append ` 2`, ` 3`, ...).

```markdown
---
date: YYYY-MM-DD
source: <original audio filename>
duration: <M min S sec>
type: voice-memo
---

# <title>

## Summary
<summary>

## Key Points
- <point>

## Action Items
- [ ] <task>

## Transcript
[00:00] <segment text>
[00:07] <segment text>
```

Timestamps: `[MM:SS]` from each segment's `start`. Merge very short segments into readable lines (aim for one line per sentence-ish chunk, not one per word).

### 5. Update the index

Append to `<vault>\1100 Voice Memos\_Index.md` (create with a `# Voice Memos` heading if missing):

```markdown
- [[YYYY-MM-DD <title>]] — <one-line gist>
```

### 6. Report

Tell the user the note path and give the summary inline. Mention action items if any were found.
