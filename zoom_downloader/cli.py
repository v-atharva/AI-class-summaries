"""
CLI entrypoints for Zoom recording downloads.
"""

import re
import warnings
from pathlib import Path

import click
from playwright.sync_api import sync_playwright
from rich.console import Console
from rich.panel import Panel

from zoom_downloader.browser import BrowserSessionManager
from zoom_downloader.downloader import DownloadService
from zoom_downloader.scraper import ZoomMediaScraper
from zoom_downloader.transcript import TranscriptConverter

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")


class ZoomDownloaderCLI:
    """
    Coordinate login, scraping, and download workflow for CLI commands.

    Variables:
    - console
      usage: terminal renderer for prompts, status, and result messages.
    - browser_session
      usage: persistent browser profile manager for login/session state.
    - download_service
      usage: service for authenticated file and text downloads.
    - media_scraper
      usage: service that extracts media URLs and metadata from Zoom pages.
    - transcript_converter
      usage: converter for VTT transcripts into requested output styles.
    """

    def __init__(
        self,
        console_instance: Console | None = None,
        browser_session: BrowserSessionManager | None = None,
        download_service: DownloadService | None = None,
        media_scraper: ZoomMediaScraper | None = None,
        transcript_converter: TranscriptConverter | None = None,
    ):
        """
        Variables:
            • console_instance
                usage: optional terminal renderer dependency injected for prompts, status updates, and result messages.
            • browser_session
                usage: optional browser-session manager used to persist and reuse authenticated Zoom state.
            • download_service
                usage: optional HTTP download service used for media and transcript retrieval.
            • media_scraper
                usage: optional scraper used to extract recording metadata and media URLs from Zoom pages.
            • transcript_converter
                usage: optional converter used to transform VTT transcripts into requested output formats.
        Functions:
            BrowserSessionManager - creates the default browser-session manager when one is not supplied.
            DownloadService - creates the default download service wired to the active console.
            ZoomMediaScraper - creates the default scraper wired to the active console.
            TranscriptConverter - creates the default transcript conversion helper.

        Initializes the CLI coordinator with either injected collaborators or default service instances for the full download workflow.
        """
        self.console = console_instance or Console()
        self.browser_session = browser_session or BrowserSessionManager()
        self.download_service = download_service or DownloadService(console_instance=self.console)
        self.media_scraper = media_scraper or ZoomMediaScraper(console_instance=self.console)
        self.transcript_converter = transcript_converter or TranscriptConverter()

    def _print_banner(self) -> None:
        """
        Displays the command-line banner that introduces the downloader before interactive prompts begin.
        """
        self.console.print("")
        self.console.print(
            Panel.fit(
                "[bold cyan]Zoom Downloader[/bold cyan]\n"
                "[dim]Download Zoom videos and transcripts[/dim]",
                border_style="blue",
            )
        )
        self.console.print("")

    def _run_login_flow(self, target_url: str | None = None) -> None:
        """
        Variables:
            • target_url
                usage: optional page address used to trigger institution-specific SSO redirects when provided.
            • login_url
                usage: resolved navigation target that defaults to the Zoom profile page when no custom URL is supplied.
            • playwright
                usage: context manager object used to launch and manage a persistent browser context.
            • context
                usage: persistent Chromium context where authenticated cookies and profile state are captured.
            • page
                usage: browser tab used for user login and completion detection via window close.
        Functions:
            self.browser_session.get_browser_context - creates the persistent browser context used for manual login.
            self.browser_session.save_cookies - snapshots authenticated cookies before the browser context closes.

        Opens an interactive browser session so the user can complete Zoom login and SSO/2FA, then persists the resulting session cookies for future commands.
        """
        login_url = target_url or "https://zoom.us/profile"

        self.console.print(
            "\n[yellow]Opening browser for login. "
            "Please log in to your Zoom account (including SSO / 2FA).[/yellow]"
        )
        self.console.print("[yellow]Close the browser window when you are done.[/yellow]\n")

        with sync_playwright() as playwright:
            context = self.browser_session.get_browser_context(playwright, headless=False)
            try:
                page = context.new_page()
                page.goto(login_url)

                try:
                    page.wait_for_event("close", timeout=0)
                except Exception:
                    pass
            finally:
                self.browser_session.save_cookies(context)
                context.close()

        self.console.print("[green]✓ Login session saved![/green]\n")

    def _prompt_menu_choice(self, prompt_text: str, valid_choices: set[str]) -> str:
        """
        Variables:
            • prompt_text
                usage: prompt shown to the user each time input is requested.
            • valid_choices
                usage: set of accepted option values used to validate user input.
            • choice
                usage: normalized user response that is checked against the accepted choices.

        Repeatedly asks for user input until a valid menu value is entered, then returns the accepted choice.
        """
        while True:
            choice = click.prompt(prompt_text, type=str).strip()
            if choice in valid_choices:
                return choice
            self.console.print("[red]Invalid choice. Please select one of the shown options.[/red]")

    def _prompt_download_target(self) -> str:
        """
        Functions:
            self._prompt_menu_choice - validates the selected download mode against supported options.

        Presents the download-target menu and returns the selected option for video, transcript, or both.
        """
        self.console.print(
            Panel.fit(
                "[bold]Choose what to download[/bold]\n\n"
                "[cyan]1.[/cyan] Video\n"
                "[cyan]2.[/cyan] Transcript\n"
                "[cyan]3.[/cyan] Video + Transcript",
                border_style="magenta",
            )
        )
        self.console.print("")
        return self._prompt_menu_choice("Enter your choice", {"1", "2", "3"})

    def _prompt_transcript_preferences(self) -> dict[str, str]:
        """
        Variables:
            • style_choice
                usage: initial transcript-style selection that determines whether timestamps are included.
            • format_choice
                usage: timestamped-format selection used to choose between plain text and VTT output.
        Functions:
            self._prompt_menu_choice - captures and validates transcript style and output format menu choices.

        Collects transcript formatting preferences and returns a style/format configuration dictionary for downstream processing.
        """
        self.console.print(
            Panel.fit(
                "[bold]Transcript Options[/bold]\n\n"
                "[cyan]1.[/cyan] Paragraph (no timestamps, saved as .txt)\n"
                "[cyan]2.[/cyan] With timestamps (like .vtt)",
                border_style="green",
            )
        )
        self.console.print("")
        style_choice = self._prompt_menu_choice("Choose transcript style", {"1", "2"})

        if style_choice == "1":
            return {"style": "paragraph", "format": "txt"}

        self.console.print("")
        self.console.print(
            Panel.fit(
                "[bold]Timestamped Transcript Format[/bold]\n\n"
                "[cyan]1.[/cyan] TXT\n"
                "[cyan]2.[/cyan] VTT",
                border_style="cyan",
            )
        )
        self.console.print("")
        format_choice = self._prompt_menu_choice("Choose format", {"1", "2"})
        return {"style": "timestamped", "format": "txt" if format_choice == "1" else "vtt"}

    @staticmethod
    def _sanitize_folder_name(name: str) -> str:
        """
        Variables:
            • name
                usage: raw folder label provided by the user or derived from recording metadata.
            • clean
                usage: sanitized folder label with filesystem-invalid characters replaced and trailing dots removed.

        Normalizes a folder name so it is safe to create on disk and falls back to a default label when empty.
        """
        clean = re.sub(r'[\\/:*?"<>|]+', "_", name).strip().strip(".")
        return clean or "Zoom_Recording"

    def _choose_output_directory(self, default_folder_name: str) -> Path:
        """
        Variables:
            • default_folder_name
                usage: suggested folder label that is shown when prompting for an output location.
            • folder_name
                usage: user-entered folder label that can override the default output folder name.
            • chosen_name
                usage: sanitized final folder name used to construct the output directory path.
            • output_dir
                usage: directory path created to store all downloaded assets for the current recording.
        Functions:
            self._sanitize_folder_name - converts the chosen folder label into a filesystem-safe directory name.

        Prompts for an output folder, sanitizes the chosen name, creates the directory, and returns the final path.
        """
        self.console.print(
            Panel.fit(
                "[bold]Output Folder[/bold]\n\n"
                f"Default: [cyan]{default_folder_name}[/cyan]\n"
                "Enter a custom folder name, or press Enter to use the default.",
                border_style="yellow",
            )
        )
        self.console.print("")
        folder_name = click.prompt(
            "Folder name",
            type=str,
            default="",
            show_default=False,
        ).strip()
        chosen_name = self._sanitize_folder_name(folder_name or default_folder_name)
        output_dir = Path.cwd() / chosen_name
        output_dir.mkdir(parents=True, exist_ok=True)
        self.console.print(f"[green]Saving downloads to:[/green] {output_dir}")
        return output_dir

    def _save_text_file(self, dest_path: Path, text: str) -> None:
        """
        Variables:
            • dest_path
                usage: destination file path where transcript text is written.
            • text
                usage: transcript content that is persisted to the output file.
            • file
                usage: open file handle used to write UTF-8 transcript content to disk.

        Writes transcript text to the target file path and reports the saved file location to the user.
        """
        with open(dest_path, "w", encoding="utf-8") as file:
            file.write(text)
        self.console.print(f"[green]✓ Successfully saved: {dest_path}[/green]")

    def _ensure_logged_in(self) -> bool:
        """
        Functions:
            self.browser_session.is_logged_in - checks whether a reusable authenticated Zoom session is already available.
            self._run_login_flow - launches the manual login process when no valid session exists.

        Verifies that an authenticated Zoom session is available and triggers the login flow when needed before scraping.
        """
        if self.browser_session.is_logged_in():
            return True

        self.console.print(
            "[red]⚠  You are not logged in.[/red]  "
            "A browser will open so you can sign in first."
        )
        self._run_login_flow()

        if self.browser_session.is_logged_in():
            return True

        self.console.print(
            "[red]Login was not completed. "
            "Please run 'zoom login' and try again.[/red]"
        )
        return False

    def login(self) -> None:
        """
        Functions:
            self._run_login_flow - executes the interactive browser login workflow for session setup.

        Runs the login command workflow to capture and persist a valid Zoom authentication session.
        """
        self._run_login_flow()

    def download(self, url: str | None) -> None:
        """
        Variables:
            • url
                usage: recording page address provided via CLI argument or interactive prompt input.
            • choice
                usage: menu selection that determines whether video, transcript, or both should be downloaded.
            • download_video_opt
                usage: flag indicating whether the video asset should be downloaded for this run.
            • download_transcript_opt
                usage: flag indicating whether transcript assets should be downloaded for this run.
            • transcript_prefs
                usage: transcript style and output format preferences selected by the user when transcript download is enabled.
            • playwright
                usage: context manager handle used to open the browser context for scraping recording metadata.
            • media_info
                usage: scraped metadata container holding the recording title and discovered media URLs.
            • title
                usage: recording title used as the base filename for saved media assets.
            • video_url
                usage: direct URL used to download the recording video when available.
            • transcript_url
                usage: transcript endpoint URL used for VTT download or text conversion.
            • browser_cookies
                usage: raw cookie objects extracted from the authenticated browser context.
            • cookie
                usage: iterated browser-cookie object transformed into a name-to-value cookie mapping for HTTP requests.
            • cookies_dict
                usage: simplified cookie jar passed to HTTP requests for authenticated media access.
            • output_dir
                usage: directory path where all selected output files for the recording are saved.
            • video_dest
                usage: destination path for the downloaded MP4 file when video download is selected.
            • transcript_dest
                usage: destination path for either VTT transcript download or converted TXT output.
            • vtt_text
                usage: raw transcript payload fetched for conversion when plain-text output is requested.
            • text_content
                usage: final transcript text produced from conversion and written to disk.
        Functions:
            self._print_banner - renders the CLI header before interactive prompts.
            self._ensure_logged_in - verifies authentication and triggers login flow if required.
            self._prompt_download_target - captures which recording assets should be downloaded.
            self._prompt_transcript_preferences - captures transcript style and format options.
            self.browser_session.get_browser_context - creates the authenticated browser context for scraping.
            self.media_scraper.extract_media_info - extracts title and media URLs from the recording page.
            self.browser_session.save_cookies - persists current browser cookies before closing the context.
            self._choose_output_directory - creates and returns the destination directory for downloaded files.
            self.download_service.download_file - downloads video or transcript files to local storage.
            self.download_service.fetch_text - retrieves transcript text for conversion when needed.
            self.transcript_converter.vtt_to_paragraph - converts VTT cues into paragraph-form plain text.
            self.transcript_converter.vtt_to_timestamped_txt - converts VTT cues into timestamped plain text.
            self._save_text_file - writes converted transcript text to disk.

        Orchestrates the full recording download flow from URL validation and authentication through media scraping, file download, transcript conversion, and final output persistence.
        """
        self._print_banner()
        if not url:
            url = click.prompt("Paste Zoom recording URL", type=str).strip()

        if not url.startswith(("http://", "https://")):
            self.console.print(
                "[red]Invalid URL. Please provide a full http(s) Zoom recording URL.[/red]"
            )
            return

        if not self._ensure_logged_in():
            return

        choice = self._prompt_download_target()
        download_video_opt = choice in ("1", "3")
        download_transcript_opt = choice in ("2", "3")

        transcript_prefs = None
        if download_transcript_opt:
            self.console.print("")
            transcript_prefs = self._prompt_transcript_preferences()

        with sync_playwright() as playwright:
            self.console.print(
                "[cyan]Opening browser to extract recording data...[/cyan]\n"
                "[yellow]A browser window will open. If prompted, "
                "complete SSO / 2FA login.[/yellow]\n"
                "[yellow]The window will close automatically once "
                "the recording info is captured.[/yellow]"
            )
            context = self.browser_session.get_browser_context(playwright, headless=False)
            try:
                media_info = self.media_scraper.extract_media_info(context, url)
                title = media_info.get("title", "Zoom_Recording")
                video_url = media_info.get("video_url")
                transcript_url = media_info.get("transcript_url")

                browser_cookies = context.cookies()
                cookies_dict = {cookie["name"]: cookie["value"] for cookie in browser_cookies}
            finally:
                self.browser_session.save_cookies(context)
                context.close()

        output_dir = self._choose_output_directory(title)

        if not video_url and download_video_opt:
            self.console.print(
                "[red]Could not find the Video URL. "
                "The recording format may be unsupported.[/red]"
            )

        if not transcript_url and download_transcript_opt:
            self.console.print(
                "[yellow]Could not find Transcript/Subtitle URL. "
                "It might not exist for this recording.[/yellow]"
            )

        if download_video_opt and video_url:
            video_dest = output_dir / f"{title}.mp4"
            self.console.print(f"\n[cyan]Downloading Video -> {video_dest}[/cyan]")
            self.download_service.download_file(
                video_url,
                str(video_dest),
                description="Downloading Video",
                cookies=cookies_dict,
            )

        if download_transcript_opt and transcript_url:
            if transcript_prefs and transcript_prefs["format"] == "vtt":
                transcript_dest = output_dir / f"{title}.vtt"
                self.console.print(
                    f"\n[cyan]Downloading Transcript (VTT) -> {transcript_dest}[/cyan]"
                )
                self.download_service.download_file(
                    transcript_url,
                    str(transcript_dest),
                    description="Downloading Transcript",
                    cookies=cookies_dict,
                )
                return

            vtt_text = self.download_service.fetch_text(
                transcript_url,
                cookies=cookies_dict,
                description="Fetching transcript",
            )
            if not vtt_text:
                self.console.print("[red]Transcript fetch failed. Nothing was saved.[/red]")
                return

            transcript_dest = output_dir / f"{title}.txt"
            if transcript_prefs and transcript_prefs["style"] == "paragraph":
                text_content = self.transcript_converter.vtt_to_paragraph(vtt_text)
                self.console.print(
                    f"\n[cyan]Saving Transcript Paragraph -> {transcript_dest}[/cyan]"
                )
            else:
                text_content = self.transcript_converter.vtt_to_timestamped_txt(vtt_text)
                self.console.print(
                    f"\n[cyan]Saving Timestamped Transcript (TXT) -> {transcript_dest}[/cyan]"
                )

            self._save_text_file(transcript_dest, text_content)


app = ZoomDownloaderCLI()


@click.group()
# Acts as the program entry-point command group for all Zoom downloader subcommands.
def cli():
    pass


@cli.command()
def login():
    """
    Functions:
        app.login - runs the main login workflow that opens a browser and persists session state.

    Invokes the login subcommand to capture and store an authenticated Zoom session for later downloads.
    """
    app.login()


@cli.command()
@click.argument("url", required=False)
def download(url):
    """
    Variables:
        • url
            usage: optional recording URL argument forwarded into the main download workflow.
    Functions:
        app.download - executes the interactive download workflow for recording assets.

    Invokes the download subcommand and forwards the optional URL into the main downloader workflow.
    """
    app.download(url)


if __name__ == "__main__":
    cli()
