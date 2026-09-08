#!/usr/bin/env python3
"""Small helper subcommands for the unattended tailor-packets/score-postings runners.

Usage:
    ./pipeline.py queue
    ./pipeline.py gate <posting-id>
    ./pipeline.py packet-path <posting-id>

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

<posting-id> is validated against [A-Za-z0-9._-]+ before it touches
anything else — ATS-supplied ids are not guaranteed to be shell-safe, so
this is enforced rather than assumed.

Human-readable messages go to stderr; stdout is always machine-readable
JSON (and only JSON — nothing is printed on a usage or validation failure).

Exit codes: 0 = success, 2 = usage or invalid posting id, 4 = posting id not
found in postings.local.yaml.
"""

from __future__ import annotations

import json
import os
import re
import sys

import yaml

from job_fetcher.profile import load_profile, authorization_verdict, location_verdict
from job_fetcher.store import load_postings
from job_fetcher.tailor import packet_slug, parse_queue

USAGE = (
    "usage: pipeline.py queue\n"
    "       pipeline.py gate <posting-id>\n"
    "       pipeline.py packet-path <posting-id>\n"
)

QUEUE_PATH = "queue.local.txt"
POSTINGS_PATH = "postings.local.yaml"
PROFILE_PATH = "profile.local.yaml"
OUTBOX_PATH = "outbox"

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


def main(argv: list[str]) -> int:
    arguments = argv[1:]

    if len(arguments) == 1 and arguments[0] == "queue":
        return queue_mode()
    if len(arguments) == 2 and arguments[0] == "gate":
        return gate_mode(arguments[1])
    if len(arguments) == 2 and arguments[0] == "packet-path":
        return packet_path_mode(arguments[1])

    print(USAGE, file=sys.stderr, end="")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
