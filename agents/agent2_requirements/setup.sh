#!/usr/bin/env bash
# setup.sh — install the toolchain the Video2Spec pipeline needs.
set -e

echo "==> System packages (ffmpeg + imagemagick)"
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -q && sudo apt-get install -y ffmpeg imagemagick
elif command -v brew >/dev/null 2>&1; then
  brew install ffmpeg imagemagick
else
  echo "    Install ffmpeg and imagemagick manually for your OS."
fi

echo "==> Python: offline ASR (works without network/GPU)"
pip install pocketsphinx --break-system-packages -q || pip install pocketsphinx -q

cat <<'EOF'

==> Optional, much better accuracy if you have network + (ideally) a GPU:
      pip install openai-whisper --break-system-packages
    then edit scripts/transcribe_chunk.py to use whisper (see the docstring).

==> Verify:
      ffmpeg -version | head -1
      python3 -c "import pocketsphinx; print('pocketsphinx OK')"
      convert --version | head -1
EOF
echo "Done."
