#!/usr/bin/env python3
"""agent1_download.py - download a video to the project inbox (yt-dlp).

Usage:
    python agents/agent1_download.py <url> <out_dir>

Prints progress, then the absolute path of the downloaded file on the LAST line
(the orchestrator reads that line). If yt-dlp isn't installed it prints install
instructions and exits non-zero. A local file path is handled by the orchestrator
directly, so this script is only invoked for real URLs.
"""
import os
import shutil
import subprocess
import sys


def main():
    if len(sys.argv) != 3:
        print("usage: agent1_download.py <url> <out_dir>", file=sys.stderr)
        return 2
    url, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)

    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        print("[agent1] yt-dlp not found. Install:  python -m pip install yt-dlp", file=sys.stderr)
        return 1

    template = os.path.join(out, "source.%(ext)s")
    # Prefer an mp4 the rest of the pipeline (ffmpeg) handles cleanly.
    subprocess.run([ytdlp, "-f", "mp4/bestvideo*+bestaudio/best",
                    "--merge-output-format", "mp4", "-o", template, url], check=True)

    files = [f for f in os.listdir(out) if f.startswith("source.")]
    if not files:
        print("[agent1] download produced no file", file=sys.stderr)
        return 1
    path = os.path.abspath(os.path.join(out, files[0]))
    print(path)  # LAST line = the orchestrator's handle
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
