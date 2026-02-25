"""
Browser session helpers for login state and persistent context management.

Design note:
- Use one reusable class to manage browser state and context creation.
- Explicitly save and restore ALL cookies (including session-only cookies)
  via a JSON snapshot file, because Chromium's persistent context does NOT
  restore session cookies (cookies without an expiry) across launches.
- Keep function wrappers for backward compatibility with existing imports.
"""

import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_ROOT = PROJECT_ROOT / ".state" / "zoom"
DEFAULT_USER_DATA_DIR = STATE_ROOT / "userdata"
DEFAULT_COOKIE_SNAPSHOT_PATH = STATE_ROOT / "cookies.json"


class BrowserSessionManager:
    """
    Handle persistent browser profile state for Zoom authentication.

    Variables:
    - user_data_dir
      usage: Chromium profile directory used for cookie/localStorage persistence.
    - cookie_snapshot_path
      usage: JSON file storing all cookies (including session cookies) explicitly.
    - channel
      usage: browser channel name passed to Playwright launch settings.
    """

    def __init__(
        self,
        user_data_dir: Path | None = None,
        cookie_snapshot_path: Path | None = None,
        channel: str = "chrome",
    ):
        """
        Variables:
            • user_data_dir
                usage: optional profile directory path where Chromium user data is persisted between sessions.
            • cookie_snapshot_path
                usage: optional JSON snapshot file path used to explicitly store and reload cookies.
            • channel
                usage: browser channel label passed to Playwright when launching Chromium.

        Initializes browser-session storage paths and launch channel settings used by the authentication workflow.
        """
        self.user_data_dir = user_data_dir or DEFAULT_USER_DATA_DIR
        self.cookie_snapshot_path = (
            cookie_snapshot_path
            if cookie_snapshot_path is not None
            else (self.user_data_dir.parent / DEFAULT_COOKIE_SNAPSHOT_PATH.name)
        )
        self.channel = channel

    def is_logged_in(self) -> bool:
        """
        Variables:
            • data
                usage: parsed cookie snapshot content loaded from disk for authentication checks.
            • cookies
                usage: cookie records read from the snapshot and filtered for Zoom authentication validity.
            • c
                usage: iterated cookie record evaluated against Zoom domain and authentication heuristics.
            • zoom_auth
                usage: subset of cookies matching Zoom domains and HTTP-only markers to confirm a real login session.

        Checks whether a stored cookie snapshot exists and contains authenticated Zoom cookies that indicate a usable login state.
        """
        if not self.cookie_snapshot_path.exists():
            return False
        try:
            data = json.loads(self.cookie_snapshot_path.read_text())
            cookies = data.get("cookies", [])
            zoom_auth = [
                c for c in cookies
                if "zoom" in c.get("domain", "")
                and c.get("httpOnly", False)
            ]
            return len(zoom_auth) > 0
        except Exception:
            return False

    def save_cookies(self, context) -> None:
        """
        Variables:
            • context
                usage: active browser context whose complete storage state is serialized to disk.
            • storage
                usage: storage-state payload containing cookies and origin data written to the snapshot file.

        Captures the current browser storage state and writes it to the cookie snapshot file for later session restoration.
        """
        self.cookie_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            storage = context.storage_state()
            self.cookie_snapshot_path.write_text(json.dumps(storage, indent=2))
        except Exception:
            pass

    def restore_cookies(self, context) -> None:
        """
        Variables:
            • context
                usage: fresh browser context that receives previously persisted authentication cookies.
            • data
                usage: parsed cookie snapshot content used to rebuild Playwright-compatible cookie entries.
            • cookies
                usage: raw cookie records loaded from snapshot storage.
            • cleaned
                usage: sanitized cookie entries with only Playwright-supported fields.
            • c
                usage: individual raw cookie record iterated while constructing sanitized entries.
            • entry
                usage: per-cookie structure appended to the restored cookie list.

        Rebuilds and injects persisted cookies into a new browser context so authenticated sessions survive browser restarts.
        """
        if not self.cookie_snapshot_path.exists():
            return
        try:
            data = json.loads(self.cookie_snapshot_path.read_text())
            cookies = data.get("cookies", [])
            if cookies:
                cleaned = []
                for c in cookies:
                    entry = {
                        "name": c["name"],
                        "value": c["value"],
                        "domain": c["domain"],
                        "path": c.get("path", "/"),
                        "secure": c.get("secure", False),
                        "httpOnly": c.get("httpOnly", False),
                        "sameSite": c.get("sameSite", "Lax"),
                    }
                    if c.get("expires", -1) > 0:
                        entry["expires"] = c["expires"]
                    cleaned.append(entry)
                context.add_cookies(cleaned)
        except Exception:
            pass

    def get_browser_context(self, playwright, headless: bool = False):
        """
        Variables:
            • playwright
                usage: browser-launch factory used to create a persistent Chromium context.
            • headless
                usage: flag that controls whether the browser runs headlessly or with a visible UI.
            • context
                usage: launched persistent browser context used for authenticated Zoom navigation.
        Functions:
            self.restore_cookies - injects persisted cookies into the newly launched browser context.

        Creates a persistent Chromium browser context with project defaults and restores saved cookies before returning it.
        """
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            headless=headless,
            channel=self.channel,
            args=[
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self.restore_cookies(context)
        return context


DEFAULT_BROWSER_SESSION = BrowserSessionManager()


def is_logged_in() -> bool:
    """
    Functions:
        DEFAULT_BROWSER_SESSION.is_logged_in - delegates login-state validation to the shared browser-session manager.

    Provides a backward-compatible helper that checks whether authenticated Zoom cookies are currently available.
    """
    return DEFAULT_BROWSER_SESSION.is_logged_in()


def get_browser_context(playwright, headless: bool = False):
    """
    Variables:
        • playwright
            usage: browser-launch factory forwarded to the shared browser-session manager.
        • headless
            usage: visibility flag forwarded when creating the browser context.
    Functions:
        DEFAULT_BROWSER_SESSION.get_browser_context - delegates persistent-context creation to the shared browser-session manager.

    Provides a backward-compatible helper that creates and returns a configured persistent browser context.
    """
    return DEFAULT_BROWSER_SESSION.get_browser_context(playwright, headless=headless)
