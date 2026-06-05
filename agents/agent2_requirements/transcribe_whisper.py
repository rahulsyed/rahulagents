#!/usr/bin/env python3
"""transcribe_whisper.py — transcribe a WAV with faster-whisper (offline after first run).

Usage: transcribe_whisper.py <audio.wav> [model] [language]
  model:    tiny | base | small | medium | large-v3   (default: base)
  language: e.g. en   (default: auto-detect)

Prints timestamped segments as:
    [mm:ss] recognized text...

Why faster-whisper (vs the bundled PocketSphinx path): far higher accuracy on long,
noisy product-demo audio, CTranslate2-backed so it runs CPU-only at reasonable speed,
and ships prebuilt wheels (works on Python 3.14 where pocketsphinx won't compile).
The model is downloaded once from HuggingFace then cached under ~/.cache, so reruns
are fully offline. This is the "network available -> prefer Whisper" path noted in
CLAUDE.md Stage 4.

Whisper ingests the whole file and segments it internally, so no manual chunking is
needed (unlike the PocketSphinx helper).
"""
import sys


def fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: transcribe_whisper.py <audio.wav> [model] [language]", file=sys.stderr)
        return 2
    audio = sys.argv[1]
    model_name = sys.argv[2] if len(sys.argv) > 2 else "base"
    language = sys.argv[3] if len(sys.argv) > 3 else None

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("[faster-whisper not installed: pip install faster-whisper]", file=sys.stderr)
        return 1

    # int8 keeps memory/CPU modest; good enough for an operational paraphrase.
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio, language=language, vad_filter=True)

    print(f"# model={model_name} language={info.language} "
          f"prob={info.language_probability:.2f} duration={fmt_ts(info.duration)}",
          file=sys.stderr)

    for seg in segments:
        text = seg.text.strip()
        if text:
            print(f"[{fmt_ts(seg.start)}] {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
