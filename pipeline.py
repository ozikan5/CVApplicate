#!/usr/bin/env python3
"""Small helper subcommands for the unattended tailor-packets/score-postings runners.

Usage:
    ./pipeline.py queue
    ./pipeline.py gate <posting-id>
    ./pipeline.py packet-path <posting-id>
    ./pipeline.py mail

This exists so the unattended skill runners never need a
`Bash(python3 -c:*)` grant (arbitrary code execution, and a hole in the
"cannot write git history" guarantee those runners rely on). Each subcommand
is a narrow, committed, testable helper instead.

queue        Reads queue.local.txt via job_fetcher.tailor.parse_queue and
             prints {"urls": [...], "skipped": [...]}.
gate         Loads profile.local.yaml and the named posting from
             postings.local.yaml and prints the eligibility-gate JSON:
             location, location_reason, authorization, authorization_reason,
             seeking, max_years_experience_required. If profile.local.yaml
             does not exist, prints {"profile": null} and exits 0.
packet-path  Computes the packet directory for the named posting via
             job_fetcher.tailor.packet_slug against outbox/'s current
             entries and prints {"slug": ..., "path": ..., "exists": bool}.
mail         Reads recruiting mail since the earliest logged application,
             read-only (EXAMINE, BODY.PEEK), and prints the candidates that
             pass the prefilter as JSON: folder, since, warnings, applications,
             candidates, remaining. Credentials come from .env and are never
             printed.

<posting-id> is validated against [A-Za-z0-9._-]+ before it touches
anything else — ATS-supplied ids are not guaranteed to be shell-safe, so
this is enforced rather than assumed.

Human-readable messages go to stderr; stdout is always machine-readable
JSON (and only JSON — nothing is printed on a usage or validation failure).

Exit codes: 0 = success, 2 = usage, invalid posting id, missing credentials or
an unreadable log, 4 = posting id not found, or the mail server unreachable.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys

import yaml

from job_fetcher import mailbox, outcomes
from job_fetcher.env import load_dotenv
from job_fetcher.profile import load_profile, authorization_verdict, location_verdict
from job_fetcher.store import load_postings
from job_fetcher.tailor import packet_slug, parse_queue

USAGE = (
    "usage: pipeline.py queue\n"
    "       pipeline.py gate <posting-id>\n"
    "       pipeline.py packet-path <posting-id>\n"
    "       pipeline.py mail\n"
)

QUEUE_PATH = "queue.local.txt"
POSTINGS_PATH = "postings.local.yaml"
PROFILE_PATH = "profile.local.yaml"
OUTBOX_PATH = "outbox"

LOG_REF = "main:applications/log.yaml"
PENDING_PATH = "outcomes.pending.yaml"
ENV_PATH = ".env"
MAIL_CANDIDATE_LIMIT = 200
DEFAULT_IMAP_HOST = "imap.gmail.com"

_connect = mailbox.connect

_POSTING_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_posting_id(posting_id: str) -> bool:
    return bool(_POSTING_ID_RE.match(posting_id))


def _load_posting(posting_id: str):
    postings = load_postings(POSTINGS_PATH)
    for posting in postings:
        if posting.get("id") == posting_id:
            return posting
    return None


def queue_mode() -> int:
    urls, skipped = parse_queue(QUEUE_PATH)
    print(json.dumps({"urls": urls, "skipped": skipped}))
    return 0


def gate_mode(posting_id: str) -> int:
    if not _validate_posting_id(posting_id):
        print(
            f"error: {posting_id!r} is not a valid posting id "
            "(expected only letters, digits, '.', '_', '-')",
            file=sys.stderr,
        )
        return 2

    if not os.path.exists(PROFILE_PATH):
        print(json.dumps({"profile": None}))
        return 0

    profile = load_profile(PROFILE_PATH)

    posting = _load_posting(posting_id)
    if posting is None:
        print(f"error: no posting {posting_id!r} in {POSTINGS_PATH}", file=sys.stderr)
        return 4

    auth_verdict, auth_reason = authorization_verdict(
        posting.get("description") or "", profile.get("work_authorization")
    )
    loc_verdict, loc_reason = location_verdict(
        posting.get("location"), profile.get("locations") or []
    )
    print(json.dumps({
        "location": loc_verdict,
        "location_reason": loc_reason,
        "authorization": auth_verdict,
        "authorization_reason": auth_reason,
        "seeking": profile.get("seeking"),
        "max_years_experience_required": profile.get("max_years_experience_required"),
    }))
    return 0


def _existing_outbox_slugs():
    if not os.path.isdir(OUTBOX_PATH):
        return set()
    return {
        entry for entry in os.listdir(OUTBOX_PATH)
        if os.path.isdir(os.path.join(OUTBOX_PATH, entry))
    }


def _find_existing_packet(posting_id: str, existing):
    """Scan outbox/*/packet.yaml for the one whose posting_id matches."""
    for slug in existing:
        packet_yaml = os.path.join(OUTBOX_PATH, slug, "packet.yaml")
        if not os.path.isfile(packet_yaml):
            continue
        with open(packet_yaml, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        if isinstance(data, dict) and data.get("posting_id") == posting_id:
            return slug
    return None


def packet_path_mode(posting_id: str) -> int:
    if not _validate_posting_id(posting_id):
        print(
            f"error: {posting_id!r} is not a valid posting id "
            "(expected only letters, digits, '.', '_', '-')",
            file=sys.stderr,
        )
        return 2

    posting = _load_posting(posting_id)
    if posting is None:
        print(f"error: no posting {posting_id!r} in {POSTINGS_PATH}", file=sys.stderr)
        return 4

    existing = _existing_outbox_slugs()

    found = _find_existing_packet(posting_id, existing)
    if found is not None:
        print(json.dumps({
            "slug": found,
            "path": os.path.join(OUTBOX_PATH, found),
            "exists": True,
        }))
        return 0

    slug = packet_slug(
        posting.get("company") or "",
        posting.get("title") or "",
        posting_id,
        existing,
    )
    path = os.path.join(OUTBOX_PATH, slug)
    print(json.dumps({"slug": slug, "path": path, "exists": False}))
    return 0


def _read_log_text() -> str:
    """Read the application log from main.

    applications/log.yaml is tracked on main only and deliberately absent from
    industry branches, so reading it as a path would fail whenever an industry
    branch is checked out.
    """
    result = subprocess.run(["git", "show", LOG_REF], capture_output=True, text=True)
    if result.returncode != 0:
        raise FileNotFoundError(f"{LOG_REF} not found: {result.stderr.strip()}")
    return result.stdout


def _load_applications() -> list:
    entries = yaml.safe_load(_read_log_text()) or []
    if not isinstance(entries, list):
        raise ValueError("applications/log.yaml must be a list of applications")
    applications = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id"):
            applications.append({
                "id": entry["id"],
                "company": entry.get("company", ""),
                "role": entry.get("role", ""),
                "outcome": entry.get("outcome") or "pending",
                "date_applied": entry.get("date_applied"),
            })
    return applications


def _as_date(value):
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value))


def mail_mode() -> int:
    load_dotenv(ENV_PATH)
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_APP_PASSWORD")
    if not user or not password:
        print("error: SMTP_USER and SMTP_APP_PASSWORD must be set in .env", file=sys.stderr)
        return 2
    host = os.environ.get("IMAP_HOST") or DEFAULT_IMAP_HOST

    try:
        applications = _load_applications()
        pending = outcomes.load_pending(PENDING_PATH)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    date_warnings = []
    parsed_dates = []
    for application in applications:
        raw_date = application.get("date_applied")
        if not raw_date:
            continue
        try:
            parsed_dates.append(_as_date(raw_date))
        except ValueError:
            date_warnings.append(
                f"application {application['id']} has an unreadable date_applied "
                f"{raw_date!r}; it was left out of the search start date"
            )

    if not parsed_dates:
        print(json.dumps({"folder": None, "since": None, "warnings": date_warnings,
                          "applications": [], "candidates": [], "remaining": 0}))
        return 0
    since = min(parsed_dates)
    seen = outcomes.seen_ids(pending)

    conn = None
    try:
        conn = _connect(host, user, password)
        folder, warnings = mailbox.open_folder(conn)
        warnings = date_warnings + warnings
        seqs = mailbox.search_since(conn, since)
        headers = mailbox.fetch_parsed(conn, seqs, mailbox.HEADERS_SPEC)
        headers = [h for h in headers if h.get("message_id")]
        own = user.lower()
        fresh = [h for h in headers
                 if h.get("from_address") != own and h.get("message_id") not in seen]
        matched = [h for h in fresh if outcomes.is_candidate(h, applications)]
        selected = matched[:MAIL_CANDIDATE_LIMIT]
        bodies = {}
        if selected:
            for full in mailbox.fetch_parsed(conn, [h["seq"] for h in selected],
                                             mailbox.FULL_SPEC):
                bodies[full["seq"]] = full
    except mailbox.MailboxError as error:
        print(f"error: {error}", file=sys.stderr)
        return error.exit_code
    except mailbox.MailboxUnavailable as error:
        print(f"error: {error}", file=sys.stderr)
        return error.exit_code
    finally:
        if conn is not None:
            try:
                conn.logout()
            except Exception:
                pass

    candidates = []
    for header in selected:
        full = bodies.get(header["seq"], header)
        candidates.append({
            "message_id": header["message_id"],
            "from": header["from"],
            "received": header["received"],
            "subject": header["subject"],
            "body": full.get("body", ""),
            "candidate_ids": outcomes.candidate_applications(header, applications),
        })

    print(json.dumps({
        "folder": folder,
        "since": since.isoformat(),
        "warnings": warnings,
        "applications": [{k: a[k] for k in ("id", "company", "role", "outcome")}
                         for a in applications],
        "candidates": candidates,
        "remaining": len(matched) - len(selected),
    }, default=str))
    return 0


def main(argv: list[str]) -> int:
    arguments = argv[1:]

    if len(arguments) == 1 and arguments[0] == "queue":
        return queue_mode()
    if len(arguments) == 2 and arguments[0] == "gate":
        return gate_mode(arguments[1])
    if len(arguments) == 2 and arguments[0] == "packet-path":
        return packet_path_mode(arguments[1])
    if len(arguments) == 1 and arguments[0] == "mail":
        return mail_mode()

    print(USAGE, file=sys.stderr, end="")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
