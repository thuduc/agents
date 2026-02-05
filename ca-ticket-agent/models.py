"""Data models for the CA Ticket Agent."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TicketDetail:
    """Detail data for a single CA ticket.

    For CVE tickets: csv_data contains parsed rows from the downloaded Wiz CSV.
    For non-CVE tickets: description contains the text scraped from the portal.
    """

    csv_data: list[dict] = field(default_factory=list)
    description: Optional[str] = None
    csv_filename: Optional[str] = None


@dataclass
class Ticket:
    """A single CA ticket from the portal list view."""

    number: str  # e.g. CA0123996
    remediation_asset_id: str  # e.g. SingleFamily Forecast Model - SFM AWS
    contextual_risk_level: str  # e.g. Medium, High
    vulnerability_source: str  # e.g. Infra
    email_escalation_date: str
    state: str  # e.g. Open, Resolved
    short_description: str  # e.g. CVE-2025-9230 or No-CVE
    update_date: str
    detail: Optional[TicketDetail] = None

    @property
    def has_cve(self) -> bool:
        """Check if this ticket has a CVE identifier."""
        desc = self.short_description.upper()
        return desc.startswith("CVE-") or desc.startswith("GHSA-")

    @property
    def ticket_url(self) -> Optional[str]:
        """Placeholder for the full URL to this ticket (set during scraping)."""
        return getattr(self, "_ticket_url", None)

    @ticket_url.setter
    def ticket_url(self, value: str):
        self._ticket_url = value


@dataclass
class ScrapeResult:
    """Result of a full scrape run."""

    tickets: list[Ticket] = field(default_factory=list)
    timestamp: str = ""
    total_count: int = 0
    open_count: int = 0
    resolved_count: int = 0
    errors: list[str] = field(default_factory=list)

    def summarize(self) -> dict:
        """Return summary stats."""
        return {
            "timestamp": self.timestamp,
            "total": self.total_count,
            "open": self.open_count,
            "resolved": self.resolved_count,
            "with_cve": sum(1 for t in self.tickets if t.has_cve),
            "without_cve": sum(1 for t in self.tickets if not t.has_cve),
            "errors": len(self.errors),
        }
