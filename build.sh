#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "==> Upgrading pip and installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Install Deno into the ignored local bin directory for yt-dlp's JavaScript challenges
if ! command -v deno &> /dev/null; then
  echo "==> Deno not found. Installing Deno for yt-dlp JavaScript challenge support..."
  curl -fsSL https://deno.land/install.sh | DENO_INSTALL="$PWD" sh
fi

# Ensure FFmpeg is available on Render Linux instances
if ! command -v ffmpeg &> /dev/null; then
  echo "==> ffmpeg not found in PATH. Downloading static Linux FFmpeg binary..."
  mkdir -p bin
  curl -fsSL https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz | tar -xJ --strip-components=2 -C bin --wildcards '*/bin/ffmpeg' '*/bin/ffprobe' || true
  chmod +x bin/ffmpeg bin/ffprobe || true
  export PATH="$PWD/bin:$PATH"
  echo "==> FFmpeg binary installed to bin/ directory."
fi

echo "==> Build completed successfully!"
