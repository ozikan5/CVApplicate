#!/usr/bin/env python3
"""Resolve a job posting URL into the pipeline's posting format.

Usage:
    ./resolve-posting.py <url>
    ./resolve-posting.py --store -

Resolve mode prints one JSON object on stdout: the standard posting dict plus
a `resolution` field saying how it was obtained. Tier 3 results additionally
carry `needs_extraction`, `raw_text`, and `hints`, with company/title/location
left null for a model to fill in.

Store mode reads a completed posting dict on stdin and merges it into
postings.local.yaml with notified=True and scored=False.

Human-readable messages go to stderr; stdout is always machine-readable.

Exit codes: 0 = resolved (including already tracked), 2 = usage or incomplete
posting, 3 = needs a browser, 4 = fetch failed, 5 = unresolvable.
"""

from __future__ import annotations

import datetime
import json
import sys

from job_fetcher.fetching import NeedsBrowser, ResolveError
from job_fetcher.resolve import resolve
from job_fetcher.store import load_postings, merge_new_postings, save_postings

USAGE = (
    "usage: resolve-posting.py <url>\n"
    "       resolve-posting.py --store -\n"
)

POSTINGS_PATH = "postings.local.yaml"
REQUIRED_FIELDS = ("company", "title", "url")
TRANSPORT_FIELDS = ("resolution", "needs_extraction", "raw_text", "hints")


def _resolve_mode(url: str) -> int:
    try:
        posting = resolve(url)
    except NeedsBrowser as error:
        print(f"error: {error}", file=sys.stderr)
        print(
            "hint: this page needs a browser. Until that is supported, run "
            "cv-review with the job description pasted in.",
            file=sys.stderr,
        )
        return error.exit_code
    except ResolveError as error:
        print(f"error: {error}", file=sys.stderr)
        return error.exit_code

    print(json.dumps(posting))
    print(
        f"info: resolved via {posting['resolution']}: "
        f"{posting.get('company') or '?'} — {posting.get('title') or '?'}",
        file=sys.stderr,
    )
    return 0


def store_mode(stream) -> int:
    try:
        posting = json.load(stream)
    except ValueError as error:
        print(f"error: stdin was not valid JSON: {error}", file=sys.stderr)
        return 2
    if not isinstance(posting, dict):
        print("error: expected a single JSON object on stdin", file=sys.stderr)
        return 2

    missing = [field for field in REQUIRED_FIELDS if not posting.get(field)]
    if missing:
        print(
            f"error: posting is incomplete, refusing to store it: "
            f"{', '.join(missing)} must not be null",
            file=sys.stderr,
        )
        return 2
    if not posting.get("id"):
        print("error: posting is missing an id", file=sys.stderr)
        return 2

    entry = {key: value for key, value in posting.items() if key not in TRANSPORT_FIELDS}

    existing = load_postings(POSTINGS_PATH)
    today = datetime.date.today().isoformat()
    merged, new_postings = merge_new_postings(existing, [entry], today, notified=True)

    if not new_postings:
        tracked = next(item for item in merged if item["id"] == entry["id"])
        print(json.dumps({
            "stored": False,
            "already_tracked": True,
            "id": entry["id"],
            "scored": bool(tracked.get("scored")),
        }))
        print(
            f"info: already tracked as {entry['id']} "
            f"(scored: {bool(tracked.get('scored'))})",
            file=sys.stderr,
        )
        return 0

    save_postings(POSTINGS_PATH, merged)
    print(json.dumps({
        "stored": True,
        "already_tracked": False,
        "id": entry["id"],
        "scored": False,
    }))
    print(f"info: stored {entry['id']}", file=sys.stderr)
    return 0


def main(argv: list[str]) -> int:
    arguments = argv[1:]
    if len(arguments) == 2 and arguments[0] == "--store" and arguments[1] == "-":
        return store_mode(sys.stdin)
    if len(arguments) == 1 and not arguments[0].startswith("-"):
        return _resolve_mode(arguments[0])
    print(USAGE, file=sys.stderr, end="")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
