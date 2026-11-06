import base64
import os
import stat
import tempfile
import unittest
from unittest.mock import patch

import app


COOKIE_TEXT = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tTEST_COOKIE\tfake-value\n"
BOT_ERROR = "ERROR: [youtube] Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies"
PLAYER_RESPONSE_ERROR = (
    "ERROR: [youtube] Failed to extract any player response; please report this issue"
)


class YoutubeCookieOptionsTests(unittest.TestCase):
    def setUp(self):
        self.local_cookie_patch = patch.object(app, "LOCAL_COOKIE_FILES", ())
        self.local_cookie_patch.start()
        self.addCleanup(self.local_cookie_patch.stop)

    def test_environment_cookies_take_precedence_and_use_private_temporary_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "local-cookies.txt")
            with open(source, "w", encoding="utf-8") as cookie_file:
                cookie_file.write("local-cookie-data")

            environment = {
                "YOUTUBE_COOKIES": COOKIE_TEXT,
                "YOUTUBE_COOKIES_FILE": source,
            }
            with patch.dict(os.environ, environment, clear=True):
                with app.youtube_ydl_options() as options:
                    temporary_cookie_file = options["cookiefile"]
                    self.assertNotEqual(temporary_cookie_file, source)
                    self.assertTrue(os.path.isfile(temporary_cookie_file))
                    with open(temporary_cookie_file, encoding="utf-8") as cookie_file:
                        self.assertEqual(cookie_file.read(), COOKIE_TEXT)
                    self.assertEqual(stat.S_IMODE(os.stat(temporary_cookie_file).st_mode), 0o600)

                self.assertFalse(os.path.exists(temporary_cookie_file))
                with open(source, encoding="utf-8") as cookie_file:
                    self.assertEqual(cookie_file.read(), "local-cookie-data")

    def test_yt_dlp_uses_default_clients_and_javascript_runtimes(self):
        self.assertNotIn("extractor_args", app.BASE_YTDL_OPTS)
        self.assertNotIn("http_headers", app.BASE_YTDL_OPTS)
        with app.yt_dlp.YoutubeDL(dict(app.BASE_YTDL_OPTS)) as ydl:
            self.assertEqual(ydl.params.get("js_runtimes"), {"deno": {}, "node": {}})

    def test_configured_browser_is_used_when_no_cookie_file_is_configured(self):
        with tempfile.TemporaryDirectory() as directory:
            local_cookie_file = os.path.join(directory, "cookies.txt")
            with open(local_cookie_file, "w", encoding="utf-8") as cookie_file:
                cookie_file.write(COOKIE_TEXT)

            with patch.object(app, "LOCAL_COOKIE_FILES", (local_cookie_file,)):
                with patch.dict(
                    os.environ, {"YOUTUBE_COOKIES_FROM_BROWSER": "firefox:default"}, clear=True
                ):
                    with app.youtube_ydl_options() as options:
                        self.assertEqual(options["cookiesfrombrowser"], ("firefox", "default"))
                        self.assertNotIn("cookiefile", options)

    def test_no_cookie_configuration_does_not_add_auth_options(self):
        with patch.dict(os.environ, {}, clear=True):
            with app.youtube_ydl_options() as options:
                self.assertNotIn("cookiefile", options)
                self.assertNotIn("cookiesfrombrowser", options)

    def test_legacy_cookie_file_is_used_as_a_private_fallback_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "yt_session_config.dat")
            with open(source, "w", encoding="utf-8") as cookie_file:
                cookie_file.write(COOKIE_TEXT)

            with patch.object(app, "LOCAL_COOKIE_FILES", (source,)):
                with patch.dict(os.environ, {}, clear=True):
                    with app.youtube_ydl_options() as options:
                        temporary_cookie_file = options["cookiefile"]
                        self.assertNotEqual(temporary_cookie_file, source)
                        with open(temporary_cookie_file, encoding="utf-8") as cookie_file:
                            self.assertEqual(cookie_file.read(), COOKIE_TEXT)

                    self.assertFalse(os.path.exists(temporary_cookie_file))

    def test_base64_environment_cookie_is_decoded(self):
        encoded_cookie_text = base64.b64encode(COOKIE_TEXT.encode("utf-8")).decode("ascii")
        with patch.dict(os.environ, {"YOUTUBE_COOKIES": encoded_cookie_text}, clear=True):
            with app.youtube_ydl_options() as options:
                with open(options["cookiefile"], encoding="utf-8") as cookie_file:
                    self.assertEqual(cookie_file.read(), COOKIE_TEXT)

    def test_overlapping_operations_get_distinct_temporary_cookie_files(self):
        with patch.dict(os.environ, {"YOUTUBE_COOKIES": COOKIE_TEXT}, clear=True):
            with app.youtube_ydl_options() as first_options:
                first_cookie_file = first_options["cookiefile"]
                with app.youtube_ydl_options() as second_options:
                    second_cookie_file = second_options["cookiefile"]
                    self.assertNotEqual(first_cookie_file, second_cookie_file)
                    self.assertTrue(os.path.exists(first_cookie_file))
                    self.assertTrue(os.path.exists(second_cookie_file))
                self.assertTrue(os.path.exists(first_cookie_file))
                self.assertFalse(os.path.exists(second_cookie_file))
            self.assertFalse(os.path.exists(first_cookie_file))


class FakeYoutubeDL:
    instances = []
    extracted_info = {
        "title": "Test video",
        "duration": 12,
        "thumbnail": "",
        "extractor_key": "Youtube",
        "uploader": "Test uploader",
    }
    extract_error = None
    download_error = None

    def __init__(self, options):
        self.options = options
        self.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def extract_info(self, url, download=False):
        if self.extract_error:
            raise self.extract_error
        return dict(self.extracted_info)

    def download(self, urls):
        if self.download_error:
            raise self.download_error
        output_template = self.options["outtmpl"]
        output_directory = os.path.dirname(output_template)
        with open(os.path.join(output_directory, "test-video.mp4"), "wb") as video_file:
            video_file.write(b"test video")


class YoutubeAuthIntegrationTests(unittest.TestCase):
    def setUp(self):
        FakeYoutubeDL.instances = []
        FakeYoutubeDL.extract_error = None
        FakeYoutubeDL.download_error = None
        self.youtube_dl_patch = patch.object(app.yt_dlp, "YoutubeDL", FakeYoutubeDL)
        self.youtube_dl_patch.start()
        self.addCleanup(self.youtube_dl_patch.stop)
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.download_directory_patch = patch.object(
            app, "DOWNLOAD_DIR", self.temp_directory.name
        )
        self.download_directory_patch.start()
        self.addCleanup(self.download_directory_patch.stop)
        self.local_cookie_patch = patch.object(app, "LOCAL_COOKIE_FILES", ())
        self.local_cookie_patch.start()
        self.addCleanup(self.local_cookie_patch.stop)

    def test_analysis_uses_and_cleans_up_the_configured_cookie_copy(self):
        with patch.dict(os.environ, {"YOUTUBE_COOKIES": COOKIE_TEXT}, clear=True):
            response = app.app.test_client().post(
                "/api/analyze", json={"url": "https://www.youtube.com/watch?v=example"}
            )

        self.assertEqual(response.status_code, 200)
        options = FakeYoutubeDL.instances[0].options
        self.assertTrue(options["cookiefile"])
        self.assertFalse(os.path.exists(options["cookiefile"]))
        self.assertEqual(options["js_runtimes"], {"deno": {}, "node": {}})
        self.assertNotIn("extractor_args", options)
        self.assertNotIn("http_headers", options)

    def test_download_uses_configured_cookie_copy_and_reports_bot_challenge(self):
        FakeYoutubeDL.download_error = RuntimeError(BOT_ERROR)
        task = app.DownloadTask(
            "test-download", "https://www.youtube.com/watch?v=example", "video", "720p", False
        )

        with patch.dict(os.environ, {"YOUTUBE_COOKIES": COOKIE_TEXT}, clear=True):
            app.run_download_thread(task)

        options = FakeYoutubeDL.instances[0].options
        self.assertFalse(os.path.exists(options["cookiefile"]))
        self.assertEqual(options["js_runtimes"], {"deno": {}, "node": {}})
        self.assertEqual(task.status, "error")
        self.assertIn("YOUTUBE_COOKIES", task.error_msg)

    def test_download_reports_player_response_failure_with_recovery_guidance(self):
        FakeYoutubeDL.download_error = RuntimeError(PLAYER_RESPONSE_ERROR)
        task = app.DownloadTask(
            "player-error-download", "https://www.youtube.com/watch?v=example", "video", "720p", False
        )

        with patch.dict(os.environ, {}, clear=True):
            app.run_download_thread(task)

        self.assertEqual(task.status, "error")
        self.assertIn("yt-dlp", task.error_msg)
        self.assertIn("JavaScript", task.error_msg)

    def test_playlist_bot_challenge_is_not_silently_ignored(self):
        FakeYoutubeDL.download_error = RuntimeError(BOT_ERROR)
        task = app.DownloadTask(
            "test-playlist", "https://www.youtube.com/playlist?list=example", "video", "720p", True
        )

        with patch.dict(os.environ, {}, clear=True):
            app.run_download_thread(task)

        options = FakeYoutubeDL.instances[0].options
        self.assertFalse(options.get("ignoreerrors", False))
        self.assertEqual(task.status, "error")
        self.assertIn("YOUTUBE_COOKIES", task.error_msg)

    def test_analysis_returns_actionable_message_for_bot_challenge(self):
        FakeYoutubeDL.extract_error = RuntimeError(BOT_ERROR)
        with patch.dict(os.environ, {}, clear=True):
            response = app.app.test_client().post(
                "/api/analyze", json={"url": "https://www.youtube.com/watch?v=example"}
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("YOUTUBE_COOKIES", response.get_json()["error"])

    def test_analysis_reports_player_response_failure_with_recovery_guidance(self):
        FakeYoutubeDL.extract_error = RuntimeError(PLAYER_RESPONSE_ERROR)
        with patch.dict(os.environ, {}, clear=True):
            response = app.app.test_client().post(
                "/api/analyze", json={"url": "https://www.youtube.com/watch?v=example"}
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("yt-dlp", response.get_json()["error"])
        self.assertIn("JavaScript", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()