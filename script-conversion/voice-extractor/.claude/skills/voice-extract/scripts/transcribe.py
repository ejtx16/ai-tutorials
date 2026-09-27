#!/usr/bin/env python3
"""Transcribe an audio file with faster-whisper and print JSON to stdout.

Usage: transcribe.py <audio-path> [--model small]

Output JSON shape:
{
  "language": "en",
  "duration": 12.34,
  "segments": [{"start": 0.0, "end": 3.2, "text": "..."}]
}
"""

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcribe audio to JSON")
    parser.add_argument("audio", help="Path to audio file (m4a/mp3/wav/ogg/opus/...)")
    parser.add_argument("--model", default="small",
                        help="Whisper model size: tiny, base, small, medium, large-v3")
    parser.add_argument("--language", default="en",
                        help="Language code (e.g. en, tl) or 'auto' to detect")
    args = parser.parse_args()

    audio_path = Path(args.audio)
    if not audio_path.is_file():
        print(f"error: file not found: {audio_path}", file=sys.stderr)
        return 1

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("error: faster-whisper not installed. Run: pip install faster-whisper",
              file=sys.stderr)
        return 1

    # First run downloads the model to the local HuggingFace cache.
    print(f"loading model '{args.model}'...", file=sys.stderr)
    model = WhisperModel(args.model, device="cpu", compute_type="int8")

    print(f"transcribing {audio_path.name}...", file=sys.stderr)
    language = None if args.language == "auto" else args.language
    try:
        segments, info = model.transcribe(str(audio_path), language=language,
                                          vad_filter=True)
    except Exception as exc:
        print(f"error: transcription failed: {exc}", file=sys.stderr)
        return 1

    out = {
        "language": info.language,
        "duration": round(info.duration, 2),
        "segments": [
            {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
            for s in segments
        ],
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
