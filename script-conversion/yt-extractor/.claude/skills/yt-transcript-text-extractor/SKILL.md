---
name: yt-transcript-text-extractor
description: Extract the full transcript of a YouTube video, remove duplicated text, group content by related topics, turn tutorial parts into simple step-by-step guides, and save it as a Markdown note in the user's Obsidian vault. Use when the user gives a YouTube URL and asks to transcribe, extract text, take notes, summarize into Obsidian, or "make this tutorial easy to follow".
---

# YT Transcript Text Extractor

Turns a YouTube video into an easy-to-follow Obsidian note: deduped transcript → topic groups → simple tutorial steps.

**Output folder:** `C:\Users\Earllie James\OneDrive\Documents\Obsidian Vault\1200 YT Transcripts\`
**Script:** `scripts/fetch_transcript.py` (relative to this skill dir, `C:\Users\Earllie James\Desktop\AI-tuts\script-conversion\yt-extractor\.claude\skills\yt-transcript-text-extractor\`)
**Template:** `templates/note_template.md`

Captions only — no audio transcription. If the video has no captions, tell the user and stop.

## Workflow

### 1. Dependency
Run `pip show youtube-transcript-api`. If missing: `pip install youtube-transcript-api`.

### 2. Fetch + mechanical dedup
```
python "C:/Users/Earllie James/Desktop/AI-tuts/script-conversion/yt-extractor/.claude/skills/yt-transcript-text-extractor/scripts/fetch_transcript.py" "<URL>" --out "<scratchpad>/<video_id>.json"
```
Options: `--lang <code>` (default `en`), `--chunk <seconds>` (default 60).
The script already strips `[Music]`/`>>` noise, rolling-caption overlap, consecutive repeats and stutters.
On `ERROR:` output → report message to user and stop.

Read the JSON: `video_id, url, title, channel, language, auto_generated, chunks[{start, ts, text}], full_text`.
For very long videos read `chunks` in parts rather than all of `full_text` at once.

### 3. Semantic dedup
- Merge ideas said more than once (recaps, "as I mentioned", intro previews of later content) into one point — keep the clearest wording and the earliest timestamp.
- Drop filler: sponsor reads, "like and subscribe", channel promos, greetings/outros, off-topic banter.
- Auto-captions (`auto_generated: true`) mishear terms — fix obvious tech terms from context (e.g. "react hooks", "npm install"). If unsure, keep original and add `(unclear in video)`.

### 4. Group by relatedness
Identify 2–8 topic groups from the content. Each group: `###` heading, 1–2 sentence summary, key points with timestamp links `[mm:ss](https://youtu.be/<id>?t=<start seconds>)`. Order groups in the order they appear in the video.

### 5. Tutorials (only if present)
A tutorial = the video shows how to do something: install, configure, build, code, commands, "first… then… next…".
For each tutorial add under `## 🛠 Tutorials`:
- **Goal** (one sentence), **You need** (prerequisites/tools/versions mentioned)
- Numbered steps in plain, simple language — explain *why* each step matters in one short line, like to a beginner
- Commands/code in fenced code blocks, exactly as said/shown
- Timestamp link per step
- **Watch out for:** pitfalls the speaker mentions
If no tutorial content, omit the section entirely.

### 6. Write the note
- Follow `templates/note_template.md` structure (frontmatter, TL;DR, Topics, Tutorials, Key Takeaways, Related, collapsed full transcript).
- Tags: `youtube`, `transcript` + 2–4 lowercase-hyphenated topic tags.
- Related: `[[wikilinks]]` to likely topic notes (e.g. `[[ReactJS]]`, `[[AI]]`).
- Full transcript: every chunk as `> **[ts]** text` lines, blank `>` between, inside the `> [!note]-` callout.
- Filename: `YYYY-MM-DD - <title>.md`, strip `\ / : * ? " < > |`, trim to ~100 chars. Create the folder if missing. If the file exists, add ` (2)`, ` (3)`...
- Write with the Write tool (UTF-8).

### 7. Report
Tell the user: saved path, number of topic groups, number of tutorials (or "none"), and whether captions were auto-generated.

## Rules
- Never invent steps, commands, or facts not in the transcript.
- Keep code/commands verbatim.
- Simple language in explanations; no jargon without a short definition.
- Multiple URLs → process each into its own note.
