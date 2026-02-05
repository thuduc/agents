"""Confluence Data Center publisher for the CA Ticket Agent.

Updates a Confluence page with HTML content using the REST API.
Requires a Personal Access Token (PAT) for authentication.

To create a PAT in Confluence Data Center:
  1. Go to your profile (top-right avatar) > Settings
  2. Click "Personal Access Tokens"
  3. Click "Create token"
  4. Give it a name, set expiry, and copy the token
"""

import json
import logging

import requests

logger = logging.getLogger(__name__)


class ConfluencePublishError(Exception):
    """Raised when publishing to Confluence fails."""

    pass


class ConfluencePublisher:
    """Publishes HTML content to a Confluence Data Center page."""

    def __init__(self, config: dict):
        self.base_url: str = config["confluence"]["base_url"].rstrip("/")
        self.page_id: str = config["confluence"]["page_id"]
        self.token: str = config["confluence"]["token"]

        self.api_url = f"{self.base_url}/rest/api/content/{self.page_id}"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_current_page(self) -> dict:
        """Fetch the current page data including version number."""
        logger.info("Fetching current page %s...", self.page_id)

        response = requests.get(
            self.api_url,
            headers=self.headers,
            params={"expand": "version,body.storage"},
            timeout=30,
        )

        if response.status_code != 200:
            raise ConfluencePublishError(
                f"Failed to fetch page {self.page_id}: "
                f"HTTP {response.status_code} - {response.text}"
            )

        return response.json()

    def update_page(self, html_content: str) -> dict:
        """Update the Confluence page with new HTML content.

        This does a full replacement of the page body.
        The version number is auto-incremented.
        """
        # Get current page to read version number and title
        current = self.get_current_page()
        current_version = current["version"]["number"]
        title = current["title"]

        logger.info(
            "Updating page '%s' (id=%s, version %d -> %d)...",
            title,
            self.page_id,
            current_version,
            current_version + 1,
        )

        payload = {
            "id": self.page_id,
            "type": "page",
            "title": title,
            "version": {"number": current_version + 1},
            "body": {
                "storage": {
                    "value": html_content,
                    "representation": "storage",
                }
            },
        }

        response = requests.put(
            self.api_url,
            headers=self.headers,
            data=json.dumps(payload),
            timeout=60,
        )

        if response.status_code != 200:
            raise ConfluencePublishError(
                f"Failed to update page {self.page_id}: "
                f"HTTP {response.status_code} - {response.text}"
            )

        result = response.json()
        new_version = result["version"]["number"]
        page_url = f"{self.base_url}{result.get('_links', {}).get('webui', '')}"

        logger.info("Page updated to version %d: %s", new_version, page_url)
        return {
            "page_id": self.page_id,
            "title": title,
            "version": new_version,
            "url": page_url,
        }

    def test_connection(self) -> bool:
        """Test the Confluence connection and token validity."""
        try:
            page = self.get_current_page()
            logger.info(
                "Confluence connection OK. Page: '%s' (version %d)",
                page["title"],
                page["version"]["number"],
            )
            return True
        except Exception as e:
            logger.error("Confluence connection failed: %s", str(e))
            return False
