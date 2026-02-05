"""Portal scraper for the Vulnerability Remediation Management Workflow.

Navigates the portal, exports the ticket list, downloads CSVs
from individual ticket detail pages, and scrapes descriptions
for non-CVE tickets.
"""

import logging
import os
import time
from pathlib import Path

from playwright.sync_api import Page, Download

from models import Ticket, TicketDetail, ScrapeResult
from session_manager import SessionManager, SessionExpiredError

logger = logging.getLogger(__name__)


class PortalScraper:
    """Scrapes CA tickets from the vulnerability remediation portal."""

    def __init__(self, config: dict, session_manager: SessionManager):
        self.config = config
        self.session = session_manager
        self.portal_url: str = config["portal"]["url"]
        self.group_link_text: str = config["portal"]["group_tickets_link_text"]
        self.rows_per_page: int = config["portal"].get("rows_per_page", 100)
        self.download_dir: str = os.path.abspath(config["paths"]["download_dir"])

        os.makedirs(self.download_dir, exist_ok=True)

    def _ensure_session(self):
        """Start browser and verify session is valid."""
        page = self.session.start()

        if not self.session.is_session_valid():
            self.session.stop()
            raise SessionExpiredError(
                "Session has expired. Run 'python agent.py login' to re-authenticate."
            )

        return page

    def navigate_to_group_tickets(self, page: Page):
        """Click 'Assigned to My Group' in the left navigation menu."""
        logger.info("Navigating to '%s'...", self.group_link_text)

        # Click the link in the left menu
        link = page.get_by_text(self.group_link_text, exact=False).first
        link.click()
        page.wait_for_load_state("networkidle")

        logger.info("Landed on group tickets page.")

    def set_rows_per_page(self, page: Page):
        """Change the rows per page dropdown to show maximum rows."""
        logger.info("Setting rows per page to %d...", self.rows_per_page)

        # Look for a rows-per-page dropdown/select. Common patterns:
        # - <select> element near the bottom of the page
        # - A dropdown button with page size options
        try:
            # Try standard select element first
            select = page.locator("select").filter(
                has_text=str(self.rows_per_page)
            ).first
            if select.is_visible(timeout=3000):
                select.select_option(str(self.rows_per_page))
                page.wait_for_load_state("networkidle")
                logger.info("Set rows per page via select element.")
                return
        except Exception:
            pass

        try:
            # Try clicking a dropdown button then selecting the value
            # Look for common pagination controls
            pager = page.locator("[class*='pagination'], [class*='paging'], [class*='rows-per-page']").first
            if pager.is_visible(timeout=3000):
                pager.click()
                page.get_by_text(str(self.rows_per_page), exact=True).first.click()
                page.wait_for_load_state("networkidle")
                logger.info("Set rows per page via dropdown button.")
                return
        except Exception:
            pass

        logger.warning(
            "Could not find rows-per-page control. "
            "The page may already show all rows or use a different pagination pattern. "
            "You may need to update the selectors for your portal."
        )

    def export_ticket_list(self, page: Page) -> str:
        """Click the Export button and download the .xlsx file.

        Returns the path to the downloaded file.
        """
        logger.info("Exporting ticket list...")

        # Set up download handler before clicking
        with page.expect_download(timeout=30000) as download_info:
            # Click the Export button/link
            export_btn = page.get_by_text("Export", exact=False).first
            export_btn.click()

        download: Download = download_info.value
        dest_path = os.path.join(self.download_dir, "ticket_list.xlsx")
        download.save_as(dest_path)

        logger.info("Ticket list exported to %s", dest_path)
        return dest_path

    def get_ticket_detail_csv(self, page: Page, ticket: Ticket) -> str | None:
        """Navigate into a ticket and download the CSV attachment.

        The CSV is found in the Activity section on the right pane.
        The filename follows the pattern [AssetID].csv.

        Returns the path to the downloaded CSV, or None if not found.
        """
        logger.info(
            "Downloading CSV for ticket %s...", ticket.number
        )

        try:
            # Look for .csv attachment link in the Activity/right pane
            csv_link = page.locator("a[href*='.csv'], a:has-text('.csv')").first

            if not csv_link.is_visible(timeout=5000):
                logger.warning(
                    "No CSV attachment found for ticket %s", ticket.number
                )
                return None

            # Download the CSV
            with page.expect_download(timeout=15000) as download_info:
                csv_link.click()

            download: Download = download_info.value
            filename = download.suggested_filename or f"{ticket.number}.csv"
            dest_path = os.path.join(self.download_dir, filename)
            download.save_as(dest_path)

            logger.info("CSV downloaded: %s", dest_path)
            return dest_path

        except Exception as e:
            logger.error(
                "Failed to download CSV for ticket %s: %s",
                ticket.number,
                str(e),
            )
            return None

    def get_ticket_description(self, page: Page, ticket: Ticket) -> str | None:
        """Scrape the Description field from a ticket detail page.

        Used for non-CVE tickets that don't have a CSV attachment.
        """
        logger.info(
            "Scraping description for ticket %s...", ticket.number
        )

        try:
            # Look for the Description section on the ticket page
            # The description typically follows a "Description" label
            desc_element = page.locator(
                "[id*='description'], "
                "[class*='description'], "
                "label:has-text('Description') + *, "
                "th:has-text('Description') + td"
            ).first

            if desc_element.is_visible(timeout=5000):
                text = desc_element.inner_text().strip()
                logger.info(
                    "Description found for %s (%d chars)",
                    ticket.number,
                    len(text),
                )
                return text

            # Fallback: look for description text after the "Description" heading
            desc_heading = page.get_by_text("Description", exact=True).first
            if desc_heading.is_visible(timeout=3000):
                # Get the next sibling or parent container
                parent = desc_heading.locator("..").first
                text = parent.inner_text().strip()
                # Remove the "Description" label itself
                if text.startswith("Description"):
                    text = text[len("Description"):].strip()
                return text

        except Exception as e:
            logger.error(
                "Failed to scrape description for %s: %s",
                ticket.number,
                str(e),
            )

        return None

    def scrape_ticket_details(
        self, page: Page, tickets: list[Ticket]
    ) -> list[Ticket]:
        """For each ticket, navigate to its detail page and extract data.

        - CVE tickets: download the CSV attachment
        - Non-CVE tickets: scrape the Description field
        """
        for i, ticket in enumerate(tickets):
            logger.info(
                "Processing ticket %d/%d: %s (%s)",
                i + 1,
                len(tickets),
                ticket.number,
                "CVE" if ticket.has_cve else "No-CVE",
            )

            try:
                # Navigate to the ticket detail page
                # Click the ticket number link in the list
                ticket_link = page.get_by_text(ticket.number, exact=True).first
                ticket_link.click()
                page.wait_for_load_state("networkidle")

                detail = TicketDetail()

                if ticket.has_cve:
                    csv_path = self.get_ticket_detail_csv(page, ticket)
                    if csv_path:
                        detail.csv_filename = csv_path
                else:
                    desc = self.get_ticket_description(page, ticket)
                    if desc:
                        detail.description = desc

                ticket.detail = detail

                # Navigate back to the ticket list
                page.go_back()
                page.wait_for_load_state("networkidle")

            except Exception as e:
                logger.error(
                    "Error processing ticket %s: %s", ticket.number, str(e)
                )

        return tickets

    def run(self) -> tuple[str, list[Ticket]]:
        """Execute the full scraping flow.

        Returns:
            Tuple of (path to exported xlsx, list of tickets with details)
        """
        page = self._ensure_session()

        try:
            # Step 1: Navigate to group tickets
            self.navigate_to_group_tickets(page)

            # Step 2: Set rows per page to max
            self.set_rows_per_page(page)

            # Step 3: Export the ticket list
            xlsx_path = self.export_ticket_list(page)

            # Return xlsx_path - tickets will be parsed by data_processor
            # then we come back for details
            return xlsx_path

        except Exception as e:
            logger.error("Scrape failed: %s", str(e))
            raise

    def fetch_details(self, page: Page, tickets: list[Ticket]) -> list[Ticket]:
        """After parsing the xlsx, go back and fetch details for each ticket.

        This is called separately so data_processor can parse the xlsx first.
        """
        # Make sure we're on the group tickets page
        self.navigate_to_group_tickets(page)
        self.set_rows_per_page(page)

        return self.scrape_ticket_details(page, tickets)
