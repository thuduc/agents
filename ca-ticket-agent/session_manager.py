"""Browser session management for the CA Ticket Agent.

Handles Playwright browser lifecycle, session persistence,
and session validity detection.
"""

import json
import logging
import os
from pathlib import Path

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)

logger = logging.getLogger(__name__)


class SessionExpiredError(Exception):
    """Raised when the saved session is no longer valid."""

    pass


class SessionManager:
    """Manages Playwright browser session with persistent auth state."""

    def __init__(self, config: dict):
        self.portal_url: str = config["portal"]["url"]
        self.session_file: str = config["paths"]["session_file"]
        self.headless: bool = config["browser"]["headless"]
        self.slow_mo: int = config["browser"].get("slow_mo", 500)
        self.timeout: int = config["browser"].get("timeout", 60000)

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    def has_saved_session(self) -> bool:
        """Check if a saved session file exists."""
        return os.path.exists(self.session_file)

    def start(self, force_new_session: bool = False) -> Page:
        """Start the browser and return a page.

        If a saved session exists and force_new_session is False,
        it will be loaded to restore auth state.
        """
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
        )

        if self.has_saved_session() and not force_new_session:
            logger.info("Loading saved session from %s", self.session_file)
            self._context = self._browser.new_context(
                storage_state=self.session_file,
            )
        else:
            logger.info("Starting fresh browser context (no saved session)")
            self._context = self._browser.new_context()

        self._context.set_default_timeout(self.timeout)
        self._page = self._context.new_page()
        return self._page

    def save_session(self):
        """Save the current browser session state to disk."""
        if self._context is None:
            raise RuntimeError("No browser context to save.")
        self._context.storage_state(path=self.session_file)
        logger.info("Session saved to %s", self.session_file)

    def is_session_valid(self) -> bool:
        """Navigate to the portal and check if we land on the portal
        (valid session) or get redirected to SSO login (expired session).

        Returns True if session is valid, False otherwise.
        """
        if self._page is None:
            raise RuntimeError("Browser not started. Call start() first.")

        logger.info("Checking session validity...")
        self._page.goto(self.portal_url, wait_until="domcontentloaded")

        # Wait a moment for any redirects to settle
        self._page.wait_for_timeout(3000)

        current_url = self._page.url.lower()
        # Common SSO/login indicators in the URL
        login_indicators = ["login", "sso", "auth", "signin", "saml", "duo"]

        if any(indicator in current_url for indicator in login_indicators):
            logger.warning("Session expired - redirected to login page: %s", current_url)
            return False

        logger.info("Session is valid - landed on portal: %s", current_url)
        return True

    def interactive_login(self):
        """Launch a headed browser for the user to manually log in.

        The user completes SSO + DUO authentication manually,
        then presses Enter in the terminal to save the session.
        """
        if self.headless:
            logger.warning(
                "Switching to headed mode for interactive login"
            )

        # Always use headed mode for login
        if self._browser:
            self.stop()

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=False,
            slow_mo=self.slow_mo,
        )
        self._context = self._browser.new_context()
        self._context.set_default_timeout(self.timeout)
        self._page = self._context.new_page()

        logger.info("Navigating to portal for manual login...")
        self._page.goto(self.portal_url, wait_until="domcontentloaded")

        print("\n" + "=" * 60)
        print("MANUAL LOGIN REQUIRED")
        print("=" * 60)
        print(f"Portal URL: {self.portal_url}")
        print()
        print("1. Complete SSO login in the browser window")
        print("2. Approve the DUO MFA push notification")
        print("3. Wait until you see the portal dashboard")
        print("4. Come back here and press ENTER to save session")
        print("=" * 60)

        input("\nPress ENTER after you have logged in successfully...")

        # Verify we're actually on the portal
        current_url = self._page.url.lower()
        login_indicators = ["login", "sso", "auth", "signin", "saml", "duo"]

        if any(indicator in current_url for indicator in login_indicators):
            print("WARNING: It looks like you're still on a login page.")
            print(f"Current URL: {self._page.url}")
            proceed = input("Save session anyway? (y/n): ").strip().lower()
            if proceed != "y":
                print("Session NOT saved. Try logging in again.")
                return

        self.save_session()
        print("Session saved successfully!")

    def stop(self):
        """Close the browser and clean up resources."""
        if self._page:
            self._page.close()
            self._page = None
        if self._context:
            self._context.close()
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        logger.info("Browser stopped and resources cleaned up.")
