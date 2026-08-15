#!/usr/bin/env python3
"""Fetch job postings from configured companies' ATS APIs and email new ones.

Usage:
    ./fetch-postings.py

Reads companies.local.yaml for the list of companies to check, fetches current
postings from each company's ATS (Greenhouse or Lever), merges them into
postings.local.yaml, and emails a summary of anything new. Designed to run
once a day via launchd (see launchd/com.cvapplicate.fetch-postings.plist.example).

Exit codes: 0 = ran (with or without new postings), 2 = config/usage error.
"""

from __future__ import annotations

import datetime
import sys
import time

from job_fetcher.ats import fetch_postings_for_company
from job_fetcher.config import ConfigError, load_companies
from job_fetcher.env import load_dotenv
from job_fetcher.notify import build_summary_email, send_email, smtp_config_from_env
from job_fetcher.store import load_postings, mark_notified, merge_new_postings, save_postings

COMPANIES_PATH = "companies.local.yaml"
POSTINGS_PATH = "postings.local.yaml"
DELAY_BETWEEN_COMPANIES_SECONDS = 1


def main() -> int:
    load_dotenv()

    try:
        companies = load_companies(COMPANIES_PATH)
    except ConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    fetched = []
    for company in companies:
        try:
            fetched.extend(fetch_postings_for_company(company))
        except Exception as error:
            print(f"warning: failed to fetch {company['name']}: {error}", file=sys.stderr)
        time.sleep(DELAY_BETWEEN_COMPANIES_SECONDS)

    existing = load_postings(POSTINGS_PATH)
    today = datetime.date.today().isoformat()
    merged, _ = merge_new_postings(existing, fetched, today)
    save_postings(POSTINGS_PATH, merged)

    to_notify = [posting for posting in merged if not posting["notified"]]
    if to_notify:
        subject, body = build_summary_email(to_notify)
        try:
            config = smtp_config_from_env()
            send_email(subject, body, config)
        except Exception as error:
            print(f"warning: failed to send notification email: {error}", file=sys.stderr)
        else:
            mark_notified(merged, {posting["id"] for posting in to_notify})
            save_postings(POSTINGS_PATH, merged)

    return 0


if __name__ == "__main__":
    sys.exit(main())
