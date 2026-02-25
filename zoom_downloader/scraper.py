"""
Zoom page scraping helpers used to capture media URLs and metadata.

Design note:
- Keep extraction procedural and event-driven.
- Use one scraper class and a simple data model for reusability.
- Keep function wrappers for backward compatibility with existing imports.
"""

import json
import re
import time
from dataclasses import dataclass

from rich.console import Console


@dataclass
class MediaInfo:
    """
    Aggregated recording metadata and asset URLs.

    Variables:
    - video_url
      usage: direct URL for downloadable MP4 content.
    - transcript_url
      usage: URL for transcript/caption payload (typically VTT).
    - title
      usage: sanitized filename base for output files.
    - topic
      usage: meeting topic extracted from Zoom metadata.
    - start_time
      usage: meeting start time label from Zoom metadata.
    """

    video_url: str | None = None
    transcript_url: str | None = None
    title: str = "Zoom_Recording"
    topic: str | None = None
    start_time: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """
        Returns the media-info data model as a plain mapping for compatibility with callers expecting dictionaries.
        """
        return {
            "video_url": self.video_url,
            "transcript_url": self.transcript_url,
            "title": self.title,
            "topic": self.topic,
            "start_time": self.start_time,
        }


class ZoomMediaScraper:
    """
    Scrape Zoom recording pages and capture media URLs via network interception.

    Variables:
    - console
      usage: terminal logger for progress and extraction summary.
    - poll_interval
      usage: delay (seconds) between polling iterations while waiting for media data.
    - max_wait_seconds
      usage: upper bound for polling while user completes login/2FA.
    """

    def __init__(
        self,
        console_instance: Console | None = None,
        poll_interval: int = 3,
        max_wait_seconds: int = 300,
    ):
        """
        Variables:
            • console_instance
                usage: optional terminal renderer dependency used for scraper progress and status output.
            • poll_interval
                usage: number of seconds between polling checks while waiting for recording assets.
            • max_wait_seconds
                usage: maximum number of seconds to wait for media URLs before fallback extraction is attempted.

        Initializes scraper runtime dependencies and timing controls for polling-based extraction.
        """
        self.console = console_instance or Console()
        self.poll_interval = poll_interval
        self.max_wait_seconds = max_wait_seconds

    @staticmethod
    def _find_urls_in_text(text: str) -> list[str]:
        """
        Variables:
            • text
                usage: raw payload text scanned for URL-like substrings.

        Extracts all HTTP and HTTPS URL candidates from arbitrary text content.
        """
        return re.findall(r'https?://[^\s"\'<>\\]+', text)

    @staticmethod
    def _normalize_url(url: str | None) -> str | None:
        """
        Variables:
            • url
                usage: raw URL value that may be relative and needs normalization.

        Converts relative Zoom paths into absolute URLs while preserving existing absolute URLs.
        """
        if not url:
            return url
        if url.startswith("/"):
            return "https://www.zoom.us" + url
        return url

    @staticmethod
    def _sanitize_title(raw: str) -> str:
        """
        Variables:
            • raw
                usage: unsanitized title text derived from meeting metadata or page title.

        Normalizes title text so it can be safely used as a filesystem-friendly output name.
        """
        return raw.replace("/", "-").replace(":", "-").replace(" ", "_").strip()

    def _capture_from_recording_api(self, body: str, media_info: MediaInfo) -> None:
        """
        Variables:
            • body
                usage: raw JSON payload captured from Zoom recording API responses.
            • media_info
                usage: mutable result container updated with discovered media URLs and metadata fields.
            • data
                usage: parsed JSON content used to inspect recording fields.
            • result
                usage: normalized payload section containing recording links and metadata.
            • key
                usage: candidate field name iterated while searching for known video and transcript keys.
            • val
                usage: URL value retrieved from candidate payload keys before normalization.
            • rec_file
                usage: individual recording-file object iterated for file-type-based URL extraction.
            • ftype
                usage: normalized recording file type used to classify media file entries.
            • dl
                usage: download or play URL candidate extracted from each recording file entry.
            • meet
                usage: nested meeting metadata object used to read topic and start-time fields.
            • topic
                usage: meeting topic text used to populate metadata and output title.
            • start_str
                usage: meeting start-time label used to enrich extracted metadata.
        Functions:
            self._normalize_url - converts extracted URLs into absolute URLs before storing them.
            self._sanitize_title - turns meeting topic text into a filesystem-safe title value.

        Parses Zoom recording API payloads to capture preferred media links and meeting metadata into the shared result object.
        """
        try:
            data = json.loads(body)
            result = data.get("result", data)
        except (json.JSONDecodeError, AttributeError):
            return

        for key in ("viewMp4Url", "mp4Url", "downloadUrl", "play_url", "fileUrl"):
            val = result.get(key)
            if val and not media_info.video_url:
                media_info.video_url = self._normalize_url(val)
                break

        for key in (
            "viewVttUrl",
            "vttUrl",
            "closedCaptionUrl",
            "transcriptUrl",
            "subtitleUrl",
            "chatFileUrl",
        ):
            val = result.get(key)
            if val and not media_info.transcript_url:
                media_info.transcript_url = self._normalize_url(val)
                break

        for rec_file in result.get("recording_files", []):
            ftype = rec_file.get("file_type", "").upper()
            dl = rec_file.get("download_url") or rec_file.get("play_url")
            if ftype == "MP4" and dl and not media_info.video_url:
                media_info.video_url = self._normalize_url(dl)
            if ftype in ("TRANSCRIPT", "VTT", "CC") and dl and not media_info.transcript_url:
                media_info.transcript_url = self._normalize_url(dl)

        meet = result.get("meet", {})
        topic = meet.get("topic") or result.get("topic")
        if topic:
            media_info.topic = topic
            media_info.title = self._sanitize_title(topic)

        start_str = meet.get("meetingStartTimeStr") or result.get("meetingStartTimeStr")
        if start_str:
            media_info.start_time = start_str

    def _capture_from_json_fallback(self, body: str, media_info: MediaInfo) -> None:
        """
        Variables:
            • body
                usage: JSON or text response body searched for URL patterns when structured extraction is insufficient.
            • media_info
                usage: mutable result container updated with fallback-discovered video and transcript URLs.
            • found_url
                usage: URL candidate extracted from body text and evaluated against media heuristics.
            • low
                usage: lowercase URL form used for case-insensitive matching against media indicators.
        Functions:
            self._find_urls_in_text - scans payload text and returns URL candidates for fallback filtering.

        Applies heuristic URL matching on generic payload text to fill missing media links when API-specific keys are unavailable.
        """
        if not media_info.video_url:
            for found_url in self._find_urls_in_text(body):
                low = found_url.lower()
                if (
                    (".mp4" in low or "ssrweb" in low)
                    and "thumbnail" not in low
                    and "avatar" not in low
                ):
                    media_info.video_url = found_url
                    break

        if not media_info.transcript_url:
            for found_url in self._find_urls_in_text(body):
                low = found_url.lower()
                if ".vtt" in low or "closedcaption" in low:
                    media_info.transcript_url = found_url
                    break

    def extract_media_info(self, context, url: str) -> dict[str, str | None]:
        """
        Variables:
            • context
                usage: authenticated browser context used to open the Zoom recording page and intercept responses.
            • url
                usage: recording-page URL navigated to for media extraction.
            • page
                usage: browser tab used for response interception, fallback DOM probing, and title collection.
            • media_info
                usage: mutable extraction result object that accumulates URLs and metadata through all strategies.
            • elapsed
                usage: elapsed polling time counter used to enforce maximum wait duration.
            • selector
                usage: fallback CSS selector iterated while probing for direct video source elements.
            • element
                usage: first matched element handle used to inspect source attributes during fallback extraction.
            • src
                usage: source URL candidate extracted from video or track elements.
            • track
                usage: fallback track-element handle used to extract transcript source URLs.
            • raw_title
                usage: page title used as a fallback naming source when topic metadata is unavailable.
            • clean
                usage: sanitized title candidate used to replace the default output title when valid.
            • title
                usage: periodic page-title snapshot printed while waiting for recording data.
            • error
                usage: captured navigation error details reported as non-fatal status output.
        Functions:
            handle_response - processes each network response and captures media URLs from payloads and headers.
            self._capture_from_recording_api - extracts canonical URLs and metadata from recording API responses.
            self._capture_from_json_fallback - applies heuristic extraction for generic JSON payloads.
            self._sanitize_title - normalizes page titles when used as fallback output names.
            media_info.to_dict - converts the populated media result object into a plain dictionary for callers.

        Opens the recording page, captures media URLs via network interception, applies DOM and title fallbacks, and returns normalized recording metadata.
        """
        page = context.new_page()
        media_info = MediaInfo()

        def handle_response(response):
            """
            Variables:
                • response
                    usage: network response inspected for direct media links and JSON payload data.
                • resp_url
                    usage: lowercase response URL used for endpoint and file-extension checks.
                • content_type
                    usage: response content-type header used to decide JSON parsing versus direct media handling.
                • body
                    usage: response body text parsed when JSON-based extraction logic is needed.
            Functions:
                self._capture_from_recording_api - extracts media URLs and metadata from known recording API payloads.
                self._capture_from_json_fallback - attempts heuristic URL extraction from generic JSON payloads.

            Inspects each intercepted response and updates the shared media result object as soon as relevant media URLs are discovered.
            """
            try:
                resp_url = response.url.lower()
                content_type = response.headers.get("content-type", "")

                if ".mp4" in resp_url and not media_info.video_url:
                    if "thumbnail" not in resp_url and "avatar" not in resp_url:
                        media_info.video_url = response.url

                if ".vtt" in resp_url and not media_info.transcript_url:
                    media_info.transcript_url = response.url

                if "json" not in content_type:
                    if "video/" in content_type and not media_info.video_url:
                        media_info.video_url = response.url
                    return

                try:
                    body = response.text()
                except Exception:
                    return

                if "nws/recording" in resp_url or "play/info" in resp_url:
                    self.console.print("[cyan]Intercepted Zoom recording API response.[/cyan]")
                    self._capture_from_recording_api(body, media_info)

                self._capture_from_json_fallback(body, media_info)

                if "video/" in content_type and not media_info.video_url:
                    media_info.video_url = response.url

            except Exception:
                return

        page.on("response", handle_response)

        self.console.print("[cyan]Opening recording page...[/cyan]")
        self.console.print(
            "[yellow]If a login / SSO / 2FA page appears, "
            "please complete the authentication in the browser window.[/yellow]"
        )

        try:
            page.goto(url, timeout=60000)
        except Exception as error:
            self.console.print(f"[yellow]Navigation note: {error}[/yellow]")

        elapsed = 0
        while elapsed < self.max_wait_seconds:
            time.sleep(self.poll_interval)
            elapsed += self.poll_interval

            if media_info.video_url:
                time.sleep(2)
                break

            if elapsed % 15 == 0:
                try:
                    title = page.title()
                    self.console.print(
                        f"[dim][{elapsed}s] Waiting for recording to load... "
                        f"(page: {title[:50]})[/dim]"
                    )
                except Exception:
                    self.console.print(f"[dim][{elapsed}s] Waiting (page navigating)...[/dim]")

        if not media_info.video_url:
            for selector in ["video source", "video"]:
                try:
                    element = page.locator(selector).first
                    if element.count() > 0:
                        src = element.get_attribute("src")
                        if src and "blob:" not in src:
                            media_info.video_url = src
                            break
                except Exception:
                    continue

        if not media_info.transcript_url:
            try:
                track = page.locator("track").first
                if track.count() > 0:
                    src = track.get_attribute("src")
                    if src:
                        media_info.transcript_url = src
            except Exception:
                pass

        if media_info.title == "Zoom_Recording":
            try:
                raw_title = page.title()
                if raw_title:
                    clean = self._sanitize_title(raw_title)
                    clean = re.sub(r"_*-_*Zoom$", "", clean, flags=re.IGNORECASE).strip("_- ")
                    if clean and "sign" not in clean.lower():
                        media_info.title = clean
            except Exception:
                pass

        page.close()

        if media_info.video_url:
            self.console.print("[green]✓ Video URL found[/green]")
        else:
            self.console.print("[red]✗ Video URL not found[/red]")

        if media_info.transcript_url:
            self.console.print("[green]✓ Transcript URL found[/green]")
        else:
            self.console.print("[yellow]✗ Transcript URL not found[/yellow]")

        if media_info.topic:
            self.console.print(f"[green]✓ Topic: {media_info.topic}[/green]")

        if media_info.start_time:
            self.console.print(f"[green]✓ Start time: {media_info.start_time}[/green]")

        return media_info.to_dict()


DEFAULT_MEDIA_SCRAPER = ZoomMediaScraper()


def _find_urls_in_text(text):
    """
    Variables:
        • text
            usage: payload text forwarded to the shared scraper URL-extraction helper.
    Functions:
        DEFAULT_MEDIA_SCRAPER._find_urls_in_text - delegates URL pattern extraction to the shared scraper instance.

    Provides a backward-compatible wrapper that extracts URL candidates from text using the shared scraper helper.
    """
    return DEFAULT_MEDIA_SCRAPER._find_urls_in_text(text)


def _normalize_url(url):
    """
    Variables:
        • url
            usage: URL value forwarded to the shared scraper normalization helper.
    Functions:
        DEFAULT_MEDIA_SCRAPER._normalize_url - delegates URL normalization to the shared scraper instance.

    Provides a backward-compatible wrapper that normalizes relative or absolute media URLs.
    """
    return DEFAULT_MEDIA_SCRAPER._normalize_url(url)


def extract_media_info(context, url):
    """
    Variables:
        • context
            usage: authenticated browser context forwarded to the shared scraper.
        • url
            usage: recording-page URL forwarded to the shared scraper.
    Functions:
        DEFAULT_MEDIA_SCRAPER.extract_media_info - delegates the full media extraction workflow to the shared scraper instance.

    Provides a backward-compatible wrapper that runs the shared scraper media-extraction workflow.
    """
    return DEFAULT_MEDIA_SCRAPER.extract_media_info(context, url)
