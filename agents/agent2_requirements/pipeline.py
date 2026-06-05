#!/usr/bin/env python3
"""pipeline.py - Cross-platform Stages 1-4 of the Video2Spec pipeline.

Usage:
    python scripts/pipeline.py <video> <output_dir> <slug> [model]

Does the same work as video2spec.ps1 / video2spec.sh but in pure Python so it runs
identically on Windows, Linux, and macOS (and inside the Docker image used for the
hosted UI). External tools required on PATH: ffmpeg, ffprobe, and ImageMagick
(either `montage` (IM6) or `magick montage` (IM7)). Transcription uses faster-whisper
via transcribe_whisper.py.

Progress is printed line-by-line to stdout so a caller (ui_server.py) can stream it.
Stages 5-6 (HD capture + SRS authoring) are performed by the Claude Code agent.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _augment_windows_path():
    """On Windows, a process spawned from some shells inherits a stale PATH that
    misses winget/MSI installs (ffmpeg, ImageMagick). Refresh from the persisted
    user + machine PATH so tool discovery is reliable however we were launched.
    No-op on Linux/macOS (Docker already has the right PATH)."""
    if os.name != "nt":
        return
    try:
        import winreg
        extra = []
        for root, sub in (
            (winreg.HKEY_CURRENT_USER, r"Environment"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        ):
            try:
                with winreg.OpenKey(root, sub) as k:
                    val, _ = winreg.QueryValueEx(k, "Path")
                    extra.append(os.path.expandvars(val))
            except OSError:
                pass
        if extra:
            os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + os.pathsep.join(extra)
    except Exception:
        pass


_augment_windows_path()


def log(msg):
    print(msg, flush=True)


def need(tool):
    p = shutil.which(tool)
    if not p:
        raise RuntimeError(f"Required tool not found on PATH: {tool}")
    return p


def montage_cmd():
    """Return the ImageMagick montage invocation for this platform."""
    if shutil.which("montage"):
        return ["montage"]
    if shutil.which("magick"):
        return ["magick", "montage"]
    raise RuntimeError("ImageMagick not found (need `montage` or `magick`).")


def run(cmd):
    subprocess.run(cmd, check=True)


def main():
    if len(sys.argv) < 4:
        print("usage: pipeline.py <video> <output_dir> <slug> [model]", file=sys.stderr)
        return 2
    video, out, slug = sys.argv[1], sys.argv[2], sys.argv[3]
    model = sys.argv[4] if len(sys.argv) > 4 else "small"

    if not os.path.isfile(video):
        print(f"Video not found: {video}", file=sys.stderr)
        return 1
    need("ffmpeg"); need("ffprobe")
    for sub in ("frames", "hd", "shots"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)

    # Stage 1 - Probe
    log("==> Stage 1: Probe")
    dur = subprocess.check_output(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", video], text=True).strip()
    dur_int = int(float(dur))
    res = subprocess.check_output(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", video],
        text=True).strip()
    log(f"    duration={dur_int}s  resolution={res}")
    interval = 8 if dur_int <= 300 else 20 if dur_int <= 1200 else 25
    log(f"    frame interval = {interval}s")

    # Stage 2 - Audio
    log("==> Stage 2: Extract audio (mono 16kHz)")
    audio = os.path.join(out, f"{slug}.audio.wav")
    run(["ffmpeg", "-loglevel", "error", "-i", video, "-ar", "16000", "-ac", "1", audio, "-y"])

    # Stage 3 - Frames + contact sheets
    log("==> Stage 3: Survey frames + contact sheets")
    run(["ffmpeg", "-loglevel", "error", "-i", video, "-vf",
         f"fps=1/{interval},scale=800:-1", "-q:v", "5",
         os.path.join(out, "frames", "f_%03d.jpg"), "-y"])
    frames = sorted(f for f in os.listdir(os.path.join(out, "frames"))
                    if f.startswith("f_") and f.endswith(".jpg"))
    log(f"    extracted {len(frames)} frames")
    mcmd = montage_cmd()
    batch = 1
    for i in range(0, len(frames), 30):
        slice_paths = [os.path.join(out, "frames", f) for f in frames[i:i + 30]]
        run(mcmd + slice_paths + ["-tile", "5x6", "-geometry", "260x+2+2",
            "-title", f"{slug} contact {batch}", os.path.join(out, f"contact_{batch}.jpg")])
        batch += 1
    log(f"    built {batch - 1} contact sheet(s) - AGENT MUST view these")

    # Stage 4 - Transcribe (faster-whisper)
    log(f"==> Stage 4: Transcribe (faster-whisper, model={model})")
    raw = os.path.join(out, f"{slug}.transcript_raw.txt")
    with open(raw, "w", encoding="utf-8") as fh:
        subprocess.run([sys.executable, os.path.join(HERE, "transcribe_whisper.py"),
                        audio, model], check=False, stdout=fh)
    words = len(open(raw, encoding="utf-8").read().split())
    log(f"    transcript words: {words}")

    log("")
    log(f"==> Stages 1-4 complete for '{slug}'.")
    log(f"    Audio:          {audio}")
    log(f"    Frames:         {os.path.join(out, 'frames')} ({len(frames)})")
    log(f"    Contact sheets: {os.path.join(out, 'contact_*.jpg')}  (AGENT: view these now)")
    log(f"    Raw transcript: {raw}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
