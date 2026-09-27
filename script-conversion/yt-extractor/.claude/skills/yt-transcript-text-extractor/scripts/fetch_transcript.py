"""Fetch a YouTube video's captions, clean + dedupe them, emit JSON.

Usage:
    python fetch_transcript.py <url-or-id> [--lang en] [--out path.json] [--chunk 60]
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request

from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
NOISE_RE = re.compile(r"\[(music|applause|laughter|laughs|inaudible|silence|__)\]|>>|♪", re.I)
STUTTER_RE = re.compile(r"\b(\w+(?:\s+\w+){0,2})(?:\s+\1\b)+", re.I)


def fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_video_id(value):
    value = value.strip()
    if ID_RE.match(value):
        return value
    u = urllib.parse.urlparse(value if "://" in value else "https://" + value)
    host = (u.hostname or "").lower()
    if host.endswith("youtu.be"):
        cand = u.path.lstrip("/").split("/")[0]
    elif "youtube" in host:
        qs = urllib.parse.parse_qs(u.query)
        if "v" in qs:
            cand = qs["v"][0]
        else:
            parts = [p for p in u.path.split("/") if p]
            cand = parts[1] if len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v") else ""
    else:
        cand = ""
    if not ID_RE.match(cand):
        fail(f"Could not find a YouTube video ID in: {value}")
    return cand


def fetch_metadata(video_id):
    url = "https://www.youtube.com/oembed?" + urllib.parse.urlencode(
        {"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"}
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)
        return data.get("title", video_id), data.get("author_name", "")
    except Exception:
        return video_id, ""


def fetch_transcript(video_id, lang):
    api = YouTubeTranscriptApi()
    try:
        langs = [lang] if lang == "en" else [lang, "en"]
        return api.fetch(video_id, languages=langs)
    except NoTranscriptFound:
        pass
    # Fallback: any language, manual preferred over auto-generated.
    transcripts = sorted(api.list(video_id), key=lambda t: t.is_generated)
    if not transcripts:
        raise NoTranscriptFound(video_id, [lang], None)
    return transcripts[0].fetch()


def clean_text(text):
    text = NOISE_RE.sub(" ", text.replace("\n", " "))
    return re.sub(r"\s+", " ", text).strip()


def strip_overlap(prev, cur, max_words=20):
    """Drop words at the start of `cur` that repeat the tail of `prev` (rolling captions)."""
    pw, cw = prev.split(), cur.split()
    for n in range(min(len(pw), len(cw), max_words), 0, -1):
        if [w.lower() for w in pw[-n:]] == [w.lower() for w in cw[:n]]:
            return " ".join(cw[n:])
    return cur


def dedupe(snippets):
    out, prev = [], ""
    for s in snippets:
        raw = clean_text(s.text)
        if not raw or raw.lower() == prev.lower():
            continue
        text = strip_overlap(prev, raw) if prev else raw
        prev = raw
        if text:
            out.append({"start": s.start, "text": text})
    return out


def fmt_ts(seconds):
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def chunk(segments, size):
    chunks, cur, cur_start = [], [], None
    for seg in segments:
        if cur_start is None:
            cur_start = seg["start"]
        cur.append(seg["text"])
        if seg["start"] - cur_start >= size:
            chunks.append((cur_start, cur))
            cur, cur_start = [], None
    if cur:
        chunks.append((cur_start, cur))
    return [
        {"start": int(st), "ts": fmt_ts(st), "text": STUTTER_RE.sub(r"\1", " ".join(parts))}
        for st, parts in chunks
    ]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--out")
    ap.add_argument("--chunk", type=int, default=60, help="seconds per chunk")
    args = ap.parse_args()

    video_id = parse_video_id(args.video)
    try:
        fetched = fetch_transcript(video_id, args.lang)
    except TranscriptsDisabled:
        fail("Captions are disabled for this video.")
    except NoTranscriptFound:
        fail("No captions found for this video in any language.")
    except VideoUnavailable:
        fail("Video is unavailable (private, removed, or wrong ID).")
    except CouldNotRetrieveTranscript as e:
        fail(f"Could not retrieve transcript: {e.__class__.__name__}")

    title, channel = fetch_metadata(video_id)
    chunks = chunk(dedupe(fetched.snippets), args.chunk)
    result = {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": title,
        "channel": channel,
        "language": fetched.language_code,
        "auto_generated": fetched.is_generated,
        "chunks": chunks,
        "full_text": " ".join(c["text"] for c in chunks),
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"Saved {len(chunks)} chunks, {len(result['full_text'].split())} words -> {args.out}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
