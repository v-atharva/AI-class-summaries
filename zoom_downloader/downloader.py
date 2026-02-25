"""
HTTP download helpers for binary files and transcript text payloads.

Design note:
- Keep requests logic centralized in a reusable service class.
- Keep function wrappers for compatibility with existing call sites.
"""

import requests
from rich.console import Console
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TransferSpeedColumn


class DownloadService:
    """
    Perform authenticated HTTP downloads and text fetches.

    Variables:
    - console
      usage: Rich console instance for progress and status messages.
    - timeout
      usage: network timeout in seconds for all requests.
    """

    def __init__(self, console_instance: Console | None = None, timeout: int = 120):
        """
        Variables:
            • console_instance
                usage: optional terminal renderer injected so callers can control output behavior.
            • timeout
                usage: request timeout value in seconds applied to all network operations.

        Configures the download service with a console for status output and a shared request timeout setting.
        """
        self.console = console_instance or Console()
        self.timeout = timeout

    @staticmethod
    def request_headers() -> dict[str, str]:
        """
        Returns the standard HTTP headers used for authenticated Zoom media and transcript requests.
        """
        return {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://zoom.us/",
        }

    def download_file(
        self,
        url: str,
        dest_path: str,
        description: str = "Downloading",
        cookies: dict | None = None,
    ) -> bool:
        """
        Variables:
            • url
                usage: direct media endpoint used as the source for file download.
            • dest_path
                usage: local destination file path where downloaded bytes are written.
            • description
                usage: progress-task label shown in the terminal while downloading.
            • cookies
                usage: authenticated cookie jar forwarded with the request for protected resources.
            • response
                usage: streamed network response used to read file bytes and metadata.
            • total_size
                usage: content-length value used to configure total progress for the download task.
            • progress
                usage: context manager that renders download progress columns in the terminal.
            • task
                usage: progress task handle updated as each data chunk is written.
            • file
                usage: output stream that persists downloaded chunks to local storage.
            • chunk
                usage: iterated response fragment written incrementally and used to advance progress.
            • error
                usage: captured failure details displayed when download attempts do not succeed.
        Functions:
            self.request_headers - supplies consistent request headers for authenticated download requests.

        Streams a remote file to disk with progress reporting and returns whether the operation completed successfully.
        """
        try:
            response = requests.get(
                url,
                stream=True,
                headers=self.request_headers(),
                cookies=cookies,
                timeout=self.timeout,
            )
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))

            with Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
            ) as progress:
                task = progress.add_task(description, total=total_size)

                with open(dest_path, "wb") as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            file.write(chunk)
                            progress.update(task, advance=len(chunk))

            self.console.print(f"[green]✓ Successfully downloaded: {dest_path}[/green]")
            return True

        except Exception as error:
            self.console.print(f"[red]Failed to download: {error}[/red]")
            return False

    def fetch_text(
        self,
        url: str,
        cookies: dict | None = None,
        description: str = "Fetching text",
    ) -> str | None:
        """
        Variables:
            • url
                usage: transcript endpoint address expected to return text content.
            • cookies
                usage: authenticated cookie jar forwarded with transcript fetch requests.
            • description
                usage: status label displayed while the text request is in progress.
            • response
                usage: network response containing transcript payload and encoding metadata.
            • error
                usage: captured failure details displayed when text retrieval fails.
        Functions:
            self.request_headers - supplies consistent request headers for authenticated transcript requests.

        Fetches text payloads such as transcripts with status feedback and returns the response text when successful.
        """
        try:
            with self.console.status(f"[cyan]{description}...[/cyan]", spinner="dots"):
                response = requests.get(
                    url,
                    headers=self.request_headers(),
                    cookies=cookies,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                response.encoding = response.encoding or "utf-8"
                return response.text
        except Exception as error:
            self.console.print(f"[red]Failed to fetch text: {error}[/red]")
            return None


DEFAULT_DOWNLOAD_SERVICE = DownloadService()


def download_file(url, dest_path, description="Downloading", cookies=None):
    """
    Variables:
        • url
            usage: media endpoint forwarded to the shared download service.
        • dest_path
            usage: destination file path forwarded to the shared download service.
        • description
            usage: progress label forwarded to the shared download service.
        • cookies
            usage: authenticated cookie jar forwarded to the shared download service.
    Functions:
        DEFAULT_DOWNLOAD_SERVICE.download_file - delegates file download execution to the shared service instance.

    Provides a backward-compatible wrapper that routes file-download requests through the shared download service.
    """
    return DEFAULT_DOWNLOAD_SERVICE.download_file(
        url=url,
        dest_path=dest_path,
        description=description,
        cookies=cookies,
    )


def fetch_text(url, cookies=None, description="Fetching text"):
    """
    Variables:
        • url
            usage: text endpoint forwarded to the shared download service.
        • cookies
            usage: authenticated cookie jar forwarded to the shared download service.
        • description
            usage: status label forwarded to the shared download service.
    Functions:
        DEFAULT_DOWNLOAD_SERVICE.fetch_text - delegates text retrieval execution to the shared service instance.

    Provides a backward-compatible wrapper that routes text-fetch requests through the shared download service.
    """
    return DEFAULT_DOWNLOAD_SERVICE.fetch_text(
        url=url,
        cookies=cookies,
        description=description,
    )
