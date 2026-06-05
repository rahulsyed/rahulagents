#!/usr/bin/env python3
"""transcribe_chunk.py — transcribe a slice of a WAV with offline PocketSphinx.

Usage: transcribe_chunk.py <audio.wav> <start_seconds> <end_seconds>
Prints a "[start-end]" header then the recognized text to stdout.

Why PocketSphinx: its pip wheel bundles an en-us acoustic model, so it works in
network-isolated sandboxes where Whisper/cloud model downloads are blocked.
If you have network + GPU, swap in openai-whisper for much higher accuracy:

    import whisper
    model = whisper.load_model("base")          # or "small"
    text = model.transcribe(slice_wav)["text"]

Keep chunks <= 420s so long videos never time out.
"""
import subprocess
import sys
import tempfile
import os


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: transcribe_chunk.py <audio.wav> <start_s> <end_s>", file=sys.stderr)
        return 2
    audio, start, end = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])

    try:
        from pocketsphinx import AudioFile
    except ImportError:
        print("[pocketsphinx not installed: pip install pocketsphinx --break-system-packages]",
              file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as td:
        chunk = os.path.join(td, "chunk.wav")
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-ss", str(start), "-t", str(end - start),
             "-i", audio, "-ar", "16000", "-ac", "1", chunk, "-y"],
            check=True,
        )
        segs = []
        for phrase in AudioFile(audio_file=chunk, frate=100):
            s = str(phrase).strip()
            if s:
                segs.append(s)

    print(f"\n===== [{start}-{end}s] =====")
    print(" ".join(segs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
