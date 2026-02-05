#!/usr/bin/env python3
"""CA Ticket Agent - CLI entry point.

Automates scraping of vulnerability tickets from the corporate portal
and publishes them to a Confluence page.

Usage:
    python agent.py login           # Interactive login (SSO + DUO)
    python agent.py run             # Full scrape + publish
    python agent.py run --no-details  # Export list only, skip per-ticket details
    python agent.py status          # Check session and Confluence connectivity
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml

from session_manager import SessionManager, SessionExpiredError
from portal_scraper import PortalScraper
from data_processor import (
    parse_ticket_list_xlsx,
    load_ticket_details,
    build_scrape_result,
    build_confluence_html,
)
from confluence_publisher import ConfluencePublisher, ConfluencePublishError


def load_config(config_path: str = None) -> dict:
    """Load configuration from YAML file.

    Looks for config.local.yaml first (user overrides),
    falls back to config.yaml.
    """
    if config_path:
        paths = [config_path]
    else:
        base_dir = Path(__file__).parent
        paths = [
            base_dir / "config.local.yaml",
            base_dir / "config.yaml",
        ]

    for p in paths:
        if Path(p).exists():
            with open(p, "r") as f:
                config = yaml.safe_load(f)
            logging.info("Loaded config from %s", p)
            return config

    print("ERROR: No config file found. Create config.local.yaml from config.yaml.")
    sys.exit(1)


def setup_logging(config: dict):
    """Configure logging based on config."""
    level = getattr(logging, config["logging"]["level"].upper(), logging.INFO)
    log_file = config["logging"].get("file")

    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def cmd_login(config: dict):
    """Interactive login command - opens browser for SSO + DUO."""
    session = SessionManager(config)

    print("Starting interactive login...")
    session.interactive_login()
    session.stop()

    print("\nYou can now run: python agent.py run")


def cmd_run(config: dict, no_details: bool = False):
    """Full scrape and publish command."""
    session = SessionManager(config)
    scraper = PortalScraper(config, session)
    publisher = ConfluencePublisher(config)

    try:
        # Step 1: Start browser and validate session
        print("Starting browser and checking session...")
        page = session.start()

        if not session.is_session_valid():
            print(
                "\nSession has expired. Please run 'python agent.py login' "
                "to re-authenticate."
            )
            session.stop()
            sys.exit(1)

        print("Session is valid.")

        # Step 2: Navigate and export ticket list
        print("Navigating to group tickets...")
        scraper.navigate_to_group_tickets(page)

        print("Setting rows per page...")
        scraper.set_rows_per_page(page)

        print("Exporting ticket list...")
        xlsx_path = scraper.export_ticket_list(page)
        print(f"Exported to: {xlsx_path}")

        # Step 3: Parse the exported xlsx
        print("Parsing ticket list...")
        tickets = parse_ticket_list_xlsx(xlsx_path)
        print(f"Found {len(tickets)} tickets.")

        # Step 4: Fetch per-ticket details (unless --no-details)
        if not no_details and tickets:
            print("Fetching individual ticket details...")
            print("(This may take a while for many tickets)")

            tickets = scraper.fetch_details(page, tickets)
            tickets = load_ticket_details(tickets)

            detail_count = sum(1 for t in tickets if t.detail is not None)
            print(f"Fetched details for {detail_count}/{len(tickets)} tickets.")
        elif no_details:
            print("Skipping per-ticket details (--no-details flag).")

        # Step 5: Build result and HTML
        print("Building Confluence page content...")
        result = build_scrape_result(tickets)
        html_content = build_confluence_html(result)

        # Step 6: Publish to Confluence
        print("Publishing to Confluence...")
        pub_result = publisher.update_page(html_content)
        print(f"Published! Page: {pub_result['url']}")
        print(f"Version: {pub_result['version']}")

        # Step 7: Summary
        summary = result.summarize()
        print("\n" + "=" * 50)
        print("RUN COMPLETE")
        print("=" * 50)
        print(f"  Total tickets:  {summary['total']}")
        print(f"  Open:           {summary['open']}")
        print(f"  Resolved:       {summary['resolved']}")
        print(f"  With CVE:       {summary['with_cve']}")
        print(f"  Without CVE:    {summary['without_cve']}")
        if summary["errors"] > 0:
            print(f"  Errors:         {summary['errors']}")
        print("=" * 50)

        # Save session (may have been refreshed during navigation)
        session.save_session()

    except SessionExpiredError as e:
        print(f"\nSession expired: {e}")
        print("Run 'python agent.py login' to re-authenticate.")
        sys.exit(1)

    except ConfluencePublishError as e:
        print(f"\nConfluence publish failed: {e}")
        sys.exit(1)

    except Exception as e:
        logging.exception("Unexpected error during run")
        print(f"\nError: {e}")
        sys.exit(1)

    finally:
        session.stop()


def cmd_status(config: dict):
    """Check session validity and Confluence connectivity."""
    print("Checking status...\n")

    # Check session file
    session = SessionManager(config)
    session_file = config["paths"]["session_file"]

    if session.has_saved_session():
        print(f"Session file: {session_file} (exists)")

        # Try to validate it
        try:
            session.start()
            if session.is_session_valid():
                print("Session:      VALID")
            else:
                print("Session:      EXPIRED - run 'python agent.py login'")
        except Exception as e:
            print(f"Session:      ERROR - {e}")
        finally:
            session.stop()
    else:
        print(f"Session file: NOT FOUND - run 'python agent.py login'")

    # Check Confluence
    print()
    publisher = ConfluencePublisher(config)
    if publisher.test_connection():
        print("Confluence:   CONNECTED")
    else:
        print("Confluence:   FAILED - check config and token")


def main():
    parser = argparse.ArgumentParser(
        description="CA Ticket Agent - Vulnerability ticket scraper and publisher",
    )
    parser.add_argument(
        "--config",
        help="Path to config YAML file (default: config.local.yaml or config.yaml)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # login command
    subparsers.add_parser("login", help="Interactive login (SSO + DUO)")

    # run command
    run_parser = subparsers.add_parser("run", help="Scrape and publish tickets")
    run_parser.add_argument(
        "--no-details",
        action="store_true",
        help="Skip fetching individual ticket details (faster, list only)",
    )

    # status command
    subparsers.add_parser("status", help="Check session and Confluence connectivity")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    config = load_config(args.config)
    setup_logging(config)

    if args.command == "login":
        cmd_login(config)
    elif args.command == "run":
        cmd_run(config, no_details=args.no_details)
    elif args.command == "status":
        cmd_status(config)


if __name__ == "__main__":
    main()
