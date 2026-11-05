# QuickGrab — Video & Audio Web Downloader

A modern, fast, and responsive web application built with **Flask** and **yt-dlp** that allows users to paste any video or playlist link and download high-quality videos (MP4) or audio tracks (MP3), including full playlists bundled into clean ZIP archives.

Designed according to the Figma design specifications with DM Sans typography, fluid responsive layout, and polished UX.

---

## ✨ Features

- **Any Supported Platform:** Downloads from YouTube, TikTok, Instagram, Vimeo, Facebook, X (Twitter), SoundCloud, Twitch, Reddit, and 1,000+ websites.
- **Single Video / Audio:**
  - Video qualities: `1080p Full HD`, `720p HD`, `480p`, or `Best available`.
  - Audio extraction: High quality MP3 at `320 kbps`, `192 kbps`, or `128 kbps`.
- **Complete Playlists:**
  - One-click toggle for entire playlists.
  - Automatically downloads every item in the playlist and archives them into a clean `.zip` package.
- **Real-Time Progress Tracking:** Live download progress bar displaying percentage, download speed (MB/s), ETA, and status stages.
- **One-Click Paste:** Instant clipboard paste button with playlist URL auto-detection.
- **Auto-Cleanup:** Background task automatically purges downloaded files older than 30 minutes to preserve server disk space.
- **Zero Heavy Build Step:** Serves ultra-fast HTML/CSS/JS with Tailwind and Google Fonts without requiring node_modules at runtime.
- **Render Ready:** Pre-configured with `render.yaml`, `build.sh`, `Procfile`, and `Dockerfile` for deployment on Render.

---

## 🚀 Running Locally

### 1. Requirements
- Python 3.10+
- FFmpeg (for video muxing and audio conversion to MP3)
  - On macOS: `brew install ffmpeg`
  - On Ubuntu/Debian: `sudo apt update && sudo apt install -y ffmpeg`
  - On Windows: Install via `winget install Gyan.FFmpeg` or download from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)

### 2. Setup
```bash
# Clone or navigate to the directory
cd Website

# (Optional) Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the Development Server
```bash
python3 app.py
```
Open your browser and visit: **`http://localhost:3000`**

---

## ☁️ Deploying to Render (Free & Paid Tiers)

Render makes hosting Python web apps seamless. You can deploy using either **Native Python** or **Docker**.

### Option 1: Native Python Runtime (Recommended)
1. Push your repository to GitHub or GitLab.
2. In [Render Dashboard](https://dashboard.render.com/), click **New +** → **Web Service**.
3. Connect your repository.
4. Configure the settings:
   - **Environment:** `Python`
   - **Build Command:** `./build.sh`
   - **Start Command:** `gunicorn app:app --workers 2 --threads 4 --timeout 180 --bind 0.0.0.0:$PORT`
   - **Plan:** Free or Starter
5. Click **Deploy Web Service**!

> *Note:* `build.sh` automatically ensures `ffmpeg` is available by downloading a static Linux build if Render's base image does not include it.

---

### Option 2: Docker Deployment
Render natively builds and runs Dockerfiles with full system package support:
1. In Render Dashboard, click **New +** → **Web Service**.
2. Connect your repository.
3. Select **Docker** as the runtime.
4. Render will automatically detect the provided [Dockerfile](Dockerfile) which installs `ffmpeg` and starts `gunicorn`.
5. Click **Deploy Web Service**!

---

### Option 3: Render Blueprint (`render.yaml`)
In Render Dashboard, select **New +** → **Blueprint** and point to your repository. It will automatically detect `render.yaml` and configure everything.

---

## 📁 Project Structure

```
├── app.py                # Main Flask backend with yt-dlp download management & REST API
├── requirements.txt      # Python dependencies (Flask, yt-dlp, gunicorn)
├── Procfile              # Gunicorn configuration for Render/Heroku
├── build.sh              # Production build script with automatic Linux FFmpeg downloader
├── Dockerfile            # Container definition with FFmpeg pre-installed
├── render.yaml           # Render Infrastructure-as-Code Blueprint
├── templates/
│   └── index.html        # Single-page web application matching the Figma design
└── downloads/            # Working directory for in-flight and temporary downloads
```

---

## 🔒 Optional Cookies for Restricted / Age-Gated Videos
If you encounter bot checks or age-gated videos on certain platforms, you can place a standard `cookies.txt` file in the project root directory. `app.py` will automatically detect and use it for yt-dlp requests.
