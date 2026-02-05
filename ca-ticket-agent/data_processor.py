"""Data processing for the CA Ticket Agent.

Parses exported .xlsx ticket list and downloaded CSV files,
normalizes data into the unified Ticket model, and builds
HTML for the Confluence page.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path

import openpyxl
import pandas as pd

from models import Ticket, TicketDetail, ScrapeResult

logger = logging.getLogger(__name__)

# Expected columns in the exported xlsx (based on portal screenshot).
# These map the portal column headers to our Ticket field names.
# Adjust these if the portal uses slightly different header text.
XLSX_COLUMN_MAP = {
    "Number": "number",
    "Remediation Asset ID": "remediation_asset_id",
    "Contextual risk level": "contextual_risk_level",
    "Vulnerability Source": "vulnerability_source",
    "Email Escalation Date": "email_escalation_date",
    "State": "state",
    "Short description": "short_description",
    "Update": "update_date",
}

# Key columns from the Wiz CSV to display in Confluence detail view.
# Full CSV has many columns; we surface the most relevant ones.
CSV_KEY_COLUMNS = [
    "Name",
    "Severity",
    "CVSSSeverity",
    "Score",
    "HasExploit",
    "HasCisaKevExploit",
    "FindingStatus",
    "AssetName",
    "AssetType",
    "Version",
    "FixedVersion",
    "IPAddresses",
    "OperatingSystem",
    "FirstDetected",
    "LastDetected",
    "ResolvedAt",
    "CloudPlatform",
    "Projects",
    "DetectionMethod",
    "ResolutionReason",
]


def parse_ticket_list_xlsx(xlsx_path: str) -> list[Ticket]:
    """Parse the exported .xlsx file into a list of Ticket objects."""
    logger.info("Parsing ticket list from %s", xlsx_path)

    df = pd.read_excel(xlsx_path, engine="openpyxl")

    # Normalize column names (strip whitespace)
    df.columns = [col.strip() for col in df.columns]

    tickets = []
    for _, row in df.iterrows():
        try:
            ticket_data = {}
            for xlsx_col, field_name in XLSX_COLUMN_MAP.items():
                value = row.get(xlsx_col, "")
                # Convert to string, handle NaN
                if pd.isna(value):
                    value = ""
                else:
                    value = str(value).strip()
                ticket_data[field_name] = value

            ticket = Ticket(**ticket_data)
            tickets.append(ticket)

        except Exception as e:
            logger.error("Failed to parse row: %s - %s", dict(row), str(e))

    logger.info("Parsed %d tickets from xlsx", len(tickets))
    return tickets


def parse_ticket_csv(csv_path: str) -> list[dict]:
    """Parse a downloaded Wiz vulnerability CSV file.

    Returns a list of dicts (one per row in the CSV).
    """
    logger.info("Parsing CSV: %s", csv_path)

    rows = []
    try:
        df = pd.read_csv(csv_path)
        for _, row in df.iterrows():
            row_dict = {}
            for col in df.columns:
                value = row[col]
                if pd.isna(value):
                    value = ""
                else:
                    value = str(value).strip()
                row_dict[col] = value
            rows.append(row_dict)

        logger.info("Parsed %d rows from CSV", len(rows))

    except Exception as e:
        logger.error("Failed to parse CSV %s: %s", csv_path, str(e))

    return rows


def load_ticket_details(tickets: list[Ticket]) -> list[Ticket]:
    """Load CSV data into ticket details for tickets that have CSV files."""
    for ticket in tickets:
        if ticket.detail and ticket.detail.csv_filename:
            csv_path = ticket.detail.csv_filename
            if Path(csv_path).exists():
                ticket.detail.csv_data = parse_ticket_csv(csv_path)

    return tickets


def build_scrape_result(tickets: list[Ticket]) -> ScrapeResult:
    """Build a ScrapeResult summary from the list of tickets."""
    result = ScrapeResult(
        tickets=tickets,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_count=len(tickets),
        open_count=sum(1 for t in tickets if t.state.lower() == "open"),
        resolved_count=sum(1 for t in tickets if t.state.lower() == "resolved"),
    )
    return result


def build_confluence_html(result: ScrapeResult) -> str:
    """Build the full HTML content for the Confluence page.

    Generates:
    1. A summary banner with counts
    2. A main table with all tickets
    3. Expandable detail sections per ticket
    """
    summary = result.summarize()

    html_parts = []

    # --- Header ---
    html_parts.append(
        f'<h1>Vulnerability Tickets - {result.timestamp}</h1>'
    )

    # --- Summary Banner ---
    html_parts.append('<ac:structured-macro ac:name="info">')
    html_parts.append("<ac:rich-text-body>")
    html_parts.append(
        f"<p><strong>Total:</strong> {summary['total']} | "
        f"<strong>Open:</strong> {summary['open']} | "
        f"<strong>Resolved:</strong> {summary['resolved']} | "
        f"<strong>With CVE:</strong> {summary['with_cve']} | "
        f"<strong>Without CVE:</strong> {summary['without_cve']}"
    )
    if summary["errors"] > 0:
        html_parts.append(
            f" | <strong>Errors:</strong> {summary['errors']}"
        )
    html_parts.append("</p>")
    html_parts.append("</ac:rich-text-body>")
    html_parts.append("</ac:structured-macro>")

    # --- Main Summary Table ---
    html_parts.append("<h2>Ticket Summary</h2>")
    html_parts.append(
        '<table>'
        "<tr>"
        "<th>Number</th>"
        "<th>Remediation Asset ID</th>"
        "<th>Risk Level</th>"
        "<th>Source</th>"
        "<th>Escalation Date</th>"
        "<th>State</th>"
        "<th>Short Description</th>"
        "<th>Updated</th>"
        "</tr>"
    )

    for ticket in result.tickets:
        # Color-code risk level
        risk = ticket.contextual_risk_level.lower()
        if risk == "high":
            risk_style = 'style="color: #d04437; font-weight: bold;"'
        elif risk == "medium":
            risk_style = 'style="color: #f6c342; font-weight: bold;"'
        else:
            risk_style = ""

        # Color-code state
        state = ticket.state.lower()
        if state == "open":
            state_style = 'style="color: #d04437;"'
        elif state == "resolved":
            state_style = 'style="color: #14892c;"'
        else:
            state_style = ""

        html_parts.append(
            f"<tr>"
            f"<td><strong>{_esc(ticket.number)}</strong></td>"
            f"<td>{_esc(ticket.remediation_asset_id)}</td>"
            f"<td {risk_style}>{_esc(ticket.contextual_risk_level)}</td>"
            f"<td>{_esc(ticket.vulnerability_source)}</td>"
            f"<td>{_esc(ticket.email_escalation_date)}</td>"
            f"<td {state_style}>{_esc(ticket.state)}</td>"
            f"<td>{_esc(ticket.short_description)}</td>"
            f"<td>{_esc(ticket.update_date)}</td>"
            f"</tr>"
        )

    html_parts.append("</table>")

    # --- Detail Sections (expandable) ---
    html_parts.append("<h2>Ticket Details</h2>")

    for ticket in result.tickets:
        if ticket.detail is None:
            continue

        html_parts.append(
            f'<ac:structured-macro ac:name="expand">'
            f'<ac:parameter ac:name="title">'
            f"{_esc(ticket.number)} - {_esc(ticket.short_description)}"
            f"</ac:parameter>"
            f"<ac:rich-text-body>"
        )

        if ticket.detail.csv_data:
            # Render key fields from CSV as a table
            html_parts.append(
                f"<p><strong>Vulnerability Details</strong> "
                f"({len(ticket.detail.csv_data)} finding(s))</p>"
            )
            html_parts.append("<table><tr>")
            for col in CSV_KEY_COLUMNS:
                html_parts.append(f"<th>{_esc(col)}</th>")
            html_parts.append("</tr>")

            for row in ticket.detail.csv_data:
                html_parts.append("<tr>")
                for col in CSV_KEY_COLUMNS:
                    value = row.get(col, "")
                    html_parts.append(f"<td>{_esc(value)}</td>")
                html_parts.append("</tr>")

            html_parts.append("</table>")

        elif ticket.detail.description:
            html_parts.append(
                f"<p><strong>Description:</strong></p>"
                f"<p>{_esc(ticket.detail.description)}</p>"
            )

        else:
            html_parts.append("<p><em>No detail data available.</em></p>")

        html_parts.append("</ac:rich-text-body>")
        html_parts.append("</ac:structured-macro>")

    # --- Footer ---
    html_parts.append("<hr/>")
    html_parts.append(
        f'<p><em>Generated by ca-ticket-agent at {result.timestamp}</em></p>'
    )

    return "\n".join(html_parts)


def _esc(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
