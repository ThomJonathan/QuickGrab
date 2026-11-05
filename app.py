import os
import re
import sys
import time
import uuid
import shutil
import zipfile
import threading
from datetime import datetime
from typing import Dict, Any, Optional

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    after_this_request,
    Response,
)
import yt_dlp

app = Flask(__name__)

# Base downloads directory
DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Prepend local bin directory to PATH if present (used for Render static ffmpeg)
LOCAL_BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")
if os.path.exists(LOCAL_BIN):
    os.environ["PATH"] = f"{LOCAL_BIN}:{os.environ.get('PATH', '')}"

# In-memory store for active and completed download tasks
# Maps download_id -> DownloadTask instance
downloads_lock = threading.Lock()
download_tasks: Dict[str, "DownloadTask"] = {}

# Common options for yt-dlp to ensure stability, bypass common blocks, and avoid bot detection
BASE_YTDL_OPTS: Dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "force_ipv4": True,
    "socket_timeout": 30,
    "retries": 10,
    "fragment_retries": 10,
    "check_formats": False,
    "http_headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Mode": "navigate",
    },
    # Use robust client chain (Android + iOS bypass bot challenges without skipping manifests)
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "ios", "mweb", "web"],
        }
    },
}

# 1. Check if cookies are supplied via Environment Variable (ideal for Render deployment)
YT_COOKIES_ENV = os.environ.get("YOUTUBE_COOKIES") or os.environ.get("COOKIES_CONTENT")
if YT_COOKIES_ENV:
    cookie_dest = os.path.join(DOWNLOAD_DIR, "yt_cookies.txt")
    try:
        import base64
        # Support either raw Netscape cookie text or base64-encoded cookie text
        if "\n" in YT_COOKIES_ENV or "\t" in YT_COOKIES_ENV:
            cookie_text = YT_COOKIES_ENV
        else:
            try:
                cookie_text = base64.b64decode(YT_COOKIES_ENV).decode("utf-8")
            except Exception:
                cookie_text = YT_COOKIES_ENV

        with open(cookie_dest, "w", encoding="utf-8") as f:
            f.write(cookie_text)
        BASE_YTDL_OPTS["cookiefile"] = cookie_dest
        print(f"Loaded YouTube cookies from environment variable into {cookie_dest}")
    except Exception as e:
        print(f"Failed to write YOUTUBE_COOKIES env: {e}")

# 2. Check if a local cookies file exists in workspace
COOKIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0:
    BASE_YTDL_OPTS["cookiefile"] = COOKIES_FILE
    print(f"Loaded YouTube cookies from {COOKIES_FILE}")


def sanitize_filename(name: str) -> str:
    """Sanitize filename to prevent directory traversal and remove illegal chars."""
    if not name:
        return "download"
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return clean[:120] if clean else "download"


def format_duration(seconds: Optional[int]) -> str:
    """Format duration in seconds to mm:ss or hh:mm:ss."""
    if not seconds or seconds <= 0:
        return "Live / Unknown"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_bytes(bytes_count: Optional[float]) -> str:
    """Format bytes into human-readable string (KB, MB, GB)."""
    if not bytes_count or bytes_count <= 0:
        return "0 KB"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_count < 1024.0:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.1f} PB"


class DownloadTask:
    def __init__(self, download_id: str, url: str, media_type: str, quality: str, is_playlist: bool):
        self.download_id = download_id
        self.url = url
        self.media_type = media_type  # 'video' or 'audio'
        self.quality = quality
        self.is_playlist = is_playlist
        
        self.status = "starting"  # starting, downloading, processing, completed, error, cancelled
        self.progress = 0.0  # 0 to 100
        self.speed_str = ""
        self.eta_str = ""
        self.filename = ""
        self.file_path = ""
        self.error_msg = ""
        
        self.total_files = 1
        self.downloaded_files = 0
        self.title = ""
        self.created_at = time.time()
        self.cancelled = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "download_id": self.download_id,
            "status": self.status,
            "progress": round(self.progress, 1),
            "speed": self.speed_str,
            "eta": self.eta_str,
            "filename": self.filename,
            "error": self.error_msg,
            "total_files": self.total_files,
            "downloaded_files": self.downloaded_files,
            "download_url": f"/api/file/{self.download_id}" if self.status == "completed" else None,
        }


def ytdl_progress_hook(d: Dict[str, Any], task: DownloadTask):
    """Callback hook invoked by yt-dlp during download."""
    if task.cancelled:
        raise Exception("Download cancelled by user")

    status = d.get("status")
    if status == "downloading":
        task.status = "downloading"
        # Downloaded bytes & total bytes
        downloaded = d.get("downloaded_bytes", 0)
        total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)

        if total and total > 0:
            file_percent = (downloaded / total) * 100
            if task.total_files > 1:
                # Weighted progress across multiple playlist items
                completed_portion = (task.downloaded_files / task.total_files) * 100
                current_portion = (1.0 / task.total_files) * file_percent
                task.progress = min(99.0, completed_portion + current_portion)
            else:
                task.progress = min(99.0, file_percent)

        # Speed formatting
        speed = d.get("speed")
        if speed:
            task.speed_str = f"{format_bytes(speed)}/s"

        # ETA formatting
        eta = d.get("eta")
        if eta is not None:
            task.eta_str = format_duration(int(eta))

        fname = d.get("filename")
        if fname:
            task.filename = os.path.basename(fname)

    elif status == "finished":
        task.status = "processing"
        task.downloaded_files += 1
        if task.total_files > 0:
            task.progress = min(99.0, (task.downloaded_files / task.total_files) * 100)
        fname = d.get("filename")
        if fname:
            task.filename = os.path.basename(fname)


def ytdl_postprocessor_hook(d: Dict[str, Any], task: DownloadTask):
    """Callback hook for ffmpeg merging and audio conversion."""
    if task.cancelled:
        raise Exception("Download cancelled by user")

    if d.get("status") == "started":
        task.status = "processing"


def get_video_format_string(quality: str) -> str:
    """Map user-selected quality to a robust yt-dlp format string with universal fallback."""
    q_lower = quality.lower()
    if "1080" in q_lower:
        return "bestvideo[height<=1080]+bestaudio/best[height<=1080]/bestvideo+bestaudio/best/all"
    elif "720" in q_lower:
        return "bestvideo[height<=720]+bestaudio/best[height<=720]/bestvideo+bestaudio/best/all"
    elif "480" in q_lower:
        return "bestvideo[height<=480]+bestaudio/best[height<=480]/bestvideo+bestaudio/best/all"
    else:  # Best available or default
        return "bestvideo+bestaudio/best/all"


def get_audio_bitrate(quality: str) -> str:
    """Map user-selected audio quality to bitrate string."""
    q_lower = quality.lower()
    if "320" in q_lower:
        return "320"
    elif "128" in q_lower:
        return "128"
    return "192"  # Standard default


def run_download_thread(task: DownloadTask):
    """Background worker executing the download using yt-dlp."""
    session_dir = os.path.join(DOWNLOAD_DIR, task.download_id)
    os.makedirs(session_dir, exist_ok=True)

    try:
        ydl_opts = dict(BASE_YTDL_OPTS)

        # Explicitly re-check and force cookiefile in worker scope
        env_cookie_path = os.path.join(DOWNLOAD_DIR, "yt_cookies.txt")
        local_cookie_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")

        if os.path.exists(env_cookie_path) and os.path.getsize(env_cookie_path) > 0:
            ydl_opts["cookiefile"] = env_cookie_path
        elif os.path.exists(local_cookie_path) and os.path.getsize(local_cookie_path) > 0:
            ydl_opts["cookiefile"] = local_cookie_path

        ydl_opts["progress_hooks"] = [lambda d: ytdl_progress_hook(d, task)]
        ydl_opts["postprocessor_hooks"] = [lambda d: ytdl_postprocessor_hook(d, task)]

        # (Rest of your download logic remains the same...)

        if task.is_playlist:
            # Playlist settings
            ydl_opts["noplaylist"] = False
            ydl_opts["yes_playlist"] = True
            ydl_opts["ignoreerrors"] = True

            target_files_dir = os.path.join(session_dir, "files")
            os.makedirs(target_files_dir, exist_ok=True)
            ydl_opts["outtmpl"] = os.path.join(
                target_files_dir, "%(playlist_index|01)02d - %(title)s.%(ext)s"
            )

            if task.media_type == "audio":
                bitrate = get_audio_bitrate(task.quality)
                ydl_opts["format"] = "bestaudio/best/all"
                ydl_opts["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": bitrate,
                    }
                ]
            else:
                ydl_opts["format"] = get_video_format_string(task.quality)
                ydl_opts["merge_output_format"] = "mp4"

            # Execute playlist download
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([task.url])

            if task.cancelled:
                return

            task.status = "processing"
            task.speed_str = "Creating ZIP archive..."

            # Find all files in target_files_dir and zip them
            collected_files = []
            for root, _, files in os.walk(target_files_dir):
                for f in files:
                    if not f.startswith("."):
                        collected_files.append(os.path.join(root, f))

            if not collected_files:
                raise Exception("No playlist files could be downloaded. The playlist might be private or empty.")

            playlist_name = sanitize_filename(task.title or "playlist")
            zip_filename = f"{playlist_name}_{task.media_type}.zip"
            zip_path = os.path.join(session_dir, zip_filename)

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file_path in collected_files:
                    arcname = os.path.basename(file_path)
                    zipf.write(file_path, arcname)

            task.file_path = zip_path
            task.filename = zip_filename
            task.progress = 100.0
            task.status = "completed"

        else:
            # Single video/audio settings
            task.total_files = 1
            ydl_opts["noplaylist"] = True

            if task.media_type == "audio":
                bitrate = get_audio_bitrate(task.quality)
                ydl_opts["format"] = "bestaudio/best/all"
                ydl_opts["outtmpl"] = os.path.join(session_dir, "%(title)s.%(ext)s")
                ydl_opts["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": bitrate,
                    }
                ]
            else:
                ydl_opts["format"] = get_video_format_string(task.quality)
                ydl_opts["outtmpl"] = os.path.join(session_dir, "%(title)s.%(ext)s")
                ydl_opts["merge_output_format"] = "mp4"

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([task.url])

            if task.cancelled:
                return

            # Find downloaded output file
            found_files = [
                f for f in os.listdir(session_dir)
                if os.path.isfile(os.path.join(session_dir, f)) and not f.startswith(".")
            ]

            if not found_files:
                raise Exception("File conversion or download failed. Please verify the link.")

            # Pick the primary file (preferred mp4 or mp3, or largest file)
            chosen_file = found_files[0]
            if len(found_files) > 1:
                # Prefer mp4/mp3
                preferred = [f for f in found_files if f.endswith(".mp4") or f.endswith(".mp3")]
                if preferred:
                    chosen_file = preferred[0]
                else:
                    chosen_file = max(
                        found_files,
                        key=lambda f: os.path.getsize(os.path.join(session_dir, f)),
                    )

            task.file_path = os.path.join(session_dir, chosen_file)
            task.filename = chosen_file
            task.progress = 100.0
            task.status = "completed"

    except Exception as e:
        if task.cancelled:
            task.status = "cancelled"
            task.error_msg = "Download was cancelled."
        else:
            task.status = "error"
            err = str(e)
            # Make errors user-friendly
            if "Private video" in err:
                task.error_msg = "This video is private or unavailable."
            elif "Sign in to confirm you’re not a bot" in err:
                task.error_msg = "Platform requested bot verification. Please try again shortly or use another link."
            elif "not a valid URL" in err:
                task.error_msg = "The provided URL is not valid."
            else:
                task.error_msg = err


def cleanup_old_sessions():
    """Background worker periodically clearing sessions older than 30 minutes."""
    while True:
        try:
            time.sleep(300)  # Check every 5 minutes
            now = time.time()
            cutoff = now - (30 * 60)  # 30 minutes

            with downloads_lock:
                expired_ids = [
                    d_id for d_id, t in download_tasks.items()
                    if t.created_at < cutoff
                ]

                for d_id in expired_ids:
                    del download_tasks[d_id]
                    s_dir = os.path.join(DOWNLOAD_DIR, d_id)
                    if os.path.exists(s_dir):
                        try:
                            shutil.rmtree(s_dir)
                        except Exception:
                            pass
        except Exception:
            pass


# Launch background cleaner daemon
cleaner_thread = threading.Thread(target=cleanup_old_sessions, daemon=True)
cleaner_thread.start()


# -------------------------------------------------------------
# Routes
# -------------------------------------------------------------

@app.route("/")
def index():
    """Render the main application page."""
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze_url():
    """Extract metadata (title, thumbnail, duration, playlist status) from URL without downloading."""
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"success": False, "error": "Please provide a valid URL"}), 400

    info = None
    last_error = None

    # Progressive client fallback to bypass cloud IP bot checks
    fallback_clients = [
        ["android", "ios", "mweb", "web"],
        ["ios", "mweb"],
        ["android"],
        ["tv_embedded"],
    ]

    for client_list in fallback_clients:
        try:
            ydl_opts = dict(BASE_YTDL_OPTS)
            ydl_opts["extract_flat"] = "in_playlist"
            ydl_opts["skip_download"] = True
            ydl_opts["check_formats"] = False
            ydl_opts["format"] = "bestvideo+bestaudio/best/all"

            if "extractor_args" in ydl_opts and "youtube" in ydl_opts["extractor_args"]:
                ydl_opts["extractor_args"] = {
                    "youtube": {
                        "player_client": client_list,
                    }
                }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception as inner_e:
                if "format is not available" in str(inner_e).lower():
                    # Fallback to pure flat extraction without checking formats
                    ydl_opts["extract_flat"] = True
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                else:
                    raise inner_e

            if info:
                break
        except Exception as e:
            last_error = e
            # Only retry alternative clients if challenged by bot detection
            if "Sign in to confirm" not in str(e) and "bot" not in str(e).lower():
                break

    if not info and last_error:
        err_msg = str(last_error)
        if "Sign in to confirm you’re not a bot" in err_msg or "cookies" in err_msg.lower():
            friendly_err = (
                "YouTube requires authentication for this link from cloud hosting IPs. "
                "You can export your YouTube cookies and set the YOUTUBE_COOKIES environment variable in Render."
            )
        elif "is not a valid URL" in err_msg:
            friendly_err = "The link entered is not valid. Please check and try again."
        elif "Private video" in err_msg:
            friendly_err = "This video is private or restricted."
        elif "Unsupported URL" in err_msg:
            friendly_err = "This website is not currently supported or the link format is invalid."
        else:
            friendly_err = f"Could not analyze video: {err_msg.split(';')[-1].strip()}"
        return jsonify({"success": False, "error": friendly_err}), 400

    if not info:
        return jsonify({"success": False, "error": "Could not retrieve media details."}), 400

    try:
        is_playlist = info.get("_type") == "playlist" or "entries" in info
        title = info.get("title") or "Unknown Title"
        thumbnail = info.get("thumbnail") or ""
        duration = info.get("duration") or 0
        extractor = info.get("extractor_key") or info.get("extractor") or "Web"
        uploader = info.get("uploader") or info.get("channel") or ""

        item_count = 1
        if is_playlist:
            entries = list(info.get("entries") or [])
            item_count = len(entries)
            # Try to grab thumbnail from the first item if playlist doesn't have one
            if not thumbnail and entries and entries[0]:
                thumbnail = entries[0].get("thumbnail", "")

        return jsonify({
            "success": True,
            "title": title,
            "thumbnail": thumbnail,
            "duration": duration,
            "duration_formatted": format_duration(duration),
            "is_playlist": is_playlist,
            "item_count": item_count,
            "extractor": extractor,
            "uploader": uploader,
        })

    except Exception as e:
        return jsonify({"success": False, "error": f"Error parsing media details: {str(e)}"}), 400


@app.route("/api/download", methods=["POST"])
def start_download():
    """Initiate a download in the background."""
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    media_type = data.get("media_type", "video")  # 'video' or 'audio'
    quality = data.get("quality", "1080p Full HD")
    is_playlist = bool(data.get("is_playlist", False))
    title = data.get("title", "")

    if not url:
        return jsonify({"success": False, "error": "URL is required"}), 400

    download_id = str(uuid.uuid4())
    task = DownloadTask(
        download_id=download_id,
        url=url,
        media_type=media_type,
        quality=quality,
        is_playlist=is_playlist,
    )
    task.title = title

    with downloads_lock:
        download_tasks[download_id] = task

    # Launch download thread
    worker = threading.Thread(target=run_download_thread, args=(task,), daemon=True)
    worker.start()

    return jsonify({"success": True, "download_id": download_id})


@app.route("/api/status/<download_id>", methods=["GET"])
def get_status(download_id: str):
    """Query progress and status for an ongoing or completed download."""
    with downloads_lock:
        task = download_tasks.get(download_id)

    if not task:
        return jsonify({"error": "Download task not found or expired"}), 404

    return jsonify(task.to_dict())


@app.route("/api/file/<download_id>", methods=["GET"])
def serve_download_file(download_id: str):
    """Serve the downloaded file (video, audio, or zip archive) to the user's browser."""
    with downloads_lock:
        task = download_tasks.get(download_id)

    if not task:
        return jsonify({"error": "Download task not found or expired"}), 404

    if task.status != "completed" or not task.file_path or not os.path.exists(task.file_path):
        return jsonify({"error": "File is not ready for download yet."}), 400

    # Determine mimetype
    filename = task.filename or os.path.basename(task.file_path)
    if filename.endswith(".mp4"):
        mimetype = "video/mp4"
    elif filename.endswith(".mp3"):
        mimetype = "audio/mpeg"
    elif filename.endswith(".zip"):
        mimetype = "application/zip"
    else:
        mimetype = "application/octet-stream"

    return send_file(
        task.file_path,
        as_attachment=True,
        download_name=filename,
        mimetype=mimetype,
    )


@app.route("/api/cancel/<download_id>", methods=["POST"])
def cancel_download(download_id: str):
    """Cancel an ongoing download and clean up its temporary files."""
    with downloads_lock:
        task = download_tasks.get(download_id)
        if task:
            task.cancelled = True
            task.status = "cancelled"

    session_dir = os.path.join(DOWNLOAD_DIR, download_id)
    if os.path.exists(session_dir):
        try:
            shutil.rmtree(session_dir)
        except Exception:
            pass

    return jsonify({"success": True})


@app.route("/api/supported-sites", methods=["GET"])
def get_supported_sites():
    """Return an extensive list of popular supported platforms."""
    sites = [
        {"name": "YouTube", "category": "Video & Music", "badge": "4K / 1080p / MP3", "popular": True},
        {"name": "TikTok", "category": "Shorts & Social", "badge": "No Watermark / Audio", "popular": True},
        {"name": "Instagram", "category": "Reels & Stories", "badge": "High Quality", "popular": True},
        {"name": "Facebook", "category": "Social & Watch", "badge": "HD Video", "popular": True},
        {"name": "X (Twitter)", "category": "Social & Clips", "badge": "MP4 / Audio", "popular": True},
        {"name": "Vimeo", "category": "Creative & Film", "badge": "Original / HD", "popular": True},
        {"name": "SoundCloud", "category": "Music & Audio", "badge": "320kbps MP3", "popular": True},
        {"name": "Reddit", "category": "Clips & Media", "badge": "Audio + Video merged", "popular": True},
        {"name": "Twitch", "category": "Streams & Clips", "badge": "VODs & Clips", "popular": True},
        {"name": "Dailymotion", "category": "Video Hub", "badge": "1080p / 720p", "popular": False},
        {"name": "Bilibili", "category": "Anime & Video", "badge": "HD Formats", "popular": False},
        {"name": "Pinterest", "category": "Social Media", "badge": "Video Pins", "popular": False},
        {"name": "LinkedIn", "category": "Professional", "badge": "Video Posts", "popular": False},
        {"name": "Threads", "category": "Social Media", "badge": "Video & Clips", "popular": False},
    ]
    return jsonify({"sites": sites, "total_supported": "1,000+"})


# Healthcheck endpoint for Render
@app.route("/healthz")
def healthcheck():
    return jsonify({"status": "ok", "timestamp": time.time()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(debug=True, host="0.0.0.0", port=port)
