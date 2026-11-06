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
- Deno or a supported Node.js runtime (for YouTube JavaScript challenges)
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

`requirements.txt` installs `yt-dlp[default]`, including yt-dlp's JavaScript challenge components. The app enables Deno and Node.js as runtime candidates. Install Deno locally with `brew install deno` (or install a supported Node.js runtime); the Render build script and Docker image install Deno automatically.

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

## 🔒 YouTube Sign-In Checks

YouTube may require sign-in verification for a video or block requests from a hosting provider's IP address. Cookies can help when the video requires an authenticated session, but they do not guarantee that YouTube will allow a request from a hosted server.

### Local development

Use a browser profile that is already signed in to YouTube:

```bash
YOUTUBE_COOKIES_FROM_BROWSER=chrome python3 app.py
```

Replace `chrome` with a browser supported by yt-dlp; an optional profile can be included, for example `firefox:default`. Alternatively, set `YOUTUBE_COOKIES_FILE` to the path of a Netscape-format cookie export. For backwards compatibility, the app also checks root-level `cookies.txt` and `yt_session_config.dat` files when no environment cookie or browser is configured.

### Hosted deployments

For Render or another host, add `YOUTUBE_COOKIES` as a secret environment variable containing a Netscape-format cookie export, or its base64-encoded text. `YOUTUBE_COOKIES_FILE` is useful when a cookie file is mounted securely; do not rely on `YOUTUBE_COOKIES_FROM_BROWSER` on a headless server without that browser profile. The legacy `COOKIES_CONTENT` environment variable is also accepted.

The app prioritizes cookie environment variables, then an explicitly configured browser, then local cookie files. It copies file/content cookies into a private temporary file for each operation and removes that copy afterward.

### YouTube player-response errors

If YouTube reports that yt-dlp failed to extract a player response, update the project dependencies and restart/redeploy the app so the latest yt-dlp and JavaScript challenge components are installed:

```bash
pip install --upgrade "yt-dlp[default]"
```

Confirm that Deno or a supported Node.js runtime is available to the running app. YouTube changes can temporarily break extraction even when dependencies are current; if the error continues, check the yt-dlp issue tracker or retry later. Cookies do not fix every player-response failure, and a hosting provider may still be blocked by YouTube.

### Keep cookie exports private

Cookie exports can grant access to your account. Never commit or share them, and do not put them in the Docker image. The repository ignores common cookie-export filenames and the Docker build excludes them, but ignore rules do not remove a file already tracked by Git. Treat any cookie file shared or committed—including the legacy `yt_session_config.dat`—as compromised: revoke the affected Google sessions, remove the file from the repository and its Git history if it was committed, and only then create a fresh cookie export if needed. Avoid publishing cookie values in logs or support requests.
