#!/usr/bin/env bash
# video2spec.sh — Stages 1-4 of the Video2Spec pipeline.
# Usage: ./video2spec.sh <video.(mp4|mov|mkv|webm)> <output_dir> <slug>
# Produces: <out>/<slug>.audio.wav, <out>/frames/, <out>/contact_*.jpg, <out>/<slug>.transcript_raw.txt
# Stages 5-6 (HD capture + SRS authoring) are done by the agent after reviewing contact sheets.
set -euo pipefail

VIDEO="${1:?Usage: video2spec.sh <video> <output_dir> <slug>}"
OUT="${2:?output dir required}"
SLUG="${3:?slug required}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$OUT/frames" "$OUT/hd" "$OUT/shots"

echo "==> Stage 1: Probe"
DUR=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$VIDEO")
DUR_INT=${DUR%.*}
RES=$(ffprobe -v quiet -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$VIDEO" 2>/dev/null || echo "?")
echo "    duration=${DUR_INT}s  resolution=${RES}"

# choose frame interval
if   [ "$DUR_INT" -le 300 ];  then INT=8
elif [ "$DUR_INT" -le 1200 ]; then INT=20
else                               INT=25
fi
echo "    frame interval = ${INT}s"

echo "==> Stage 2: Extract audio (mono 16kHz)"
ffmpeg -loglevel error -i "$VIDEO" -ar 16000 -ac 1 "$OUT/${SLUG}.audio.wav" -y

echo "==> Stage 3: Survey frames + contact sheets"
ffmpeg -loglevel error -i "$VIDEO" -vf "fps=1/${INT},scale=800:-1" -q:v 5 "$OUT/frames/f_%03d.jpg" -y
NFRAMES=$(ls "$OUT/frames" | wc -l | tr -d ' ')
echo "    extracted ${NFRAMES} frames"
# contact sheets in batches of 30
if command -v montage >/dev/null 2>&1; then
  i=0; batch=1
  files=$(ls "$OUT/frames"/f_*.jpg | sort)
  echo "$files" | split -l 30 - "$OUT/.cbatch_"
  for b in "$OUT"/.cbatch_*; do
    montage $(cat "$b") -tile 5x6 -geometry 260x+2+2 -title "${SLUG} contact ${batch}" "$OUT/contact_${batch}.jpg" 2>/dev/null || true
    batch=$((batch+1))
  done
  rm -f "$OUT"/.cbatch_*
  echo "    built $((batch-1)) contact sheet(s) — AGENT MUST view these"
else
  echo "    (montage not found; agent should view frames/ directly)"
fi

echo "==> Stage 4: Transcribe (chunked at 420s)"
RAW="$OUT/${SLUG}.transcript_raw.txt"; : > "$RAW"
s=0
while [ "$s" -lt "$DUR_INT" ]; do
  e=$((s+420)); [ "$e" -gt "$DUR_INT" ] && e=$DUR_INT
  echo "    chunk ${s}-${e}s"
  python3 "$SCRIPT_DIR/transcribe_chunk.py" "$OUT/${SLUG}.audio.wav" "$s" "$e" >> "$RAW" 2>/dev/null || \
    echo "[chunk ${s}-${e}: transcription failed]" >> "$RAW"
  s=$e
done
WORDS=$(wc -w < "$RAW" | tr -d ' ')
echo "    transcript words: ${WORDS}"

cat <<EOF

==> Stages 1-4 complete for '${SLUG}'.
    Audio:       $OUT/${SLUG}.audio.wav
    Frames:      $OUT/frames/ (${NFRAMES})
    Contact:     $OUT/contact_*.jpg   <-- AGENT: view these now
    Raw transcript: $RAW

NEXT (agent):
  5) View contact sheets, pick key screens, grab HD frames:
       ffmpeg -ss <sec> -i "$VIDEO" -frames:v 1 -q:v 2 "$OUT/hd/<name>.jpg" -y
     View each, read the UI, then:
       convert "$OUT/hd/<name>.jpg" -resize 1200x -quality 82 "$OUT/shots/NN-<name>.jpg"
  6) Author the SRS with build_srs.py (see prompts/srs-authoring.md).
EOF
