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

import json
import sys

from job_fetcher.fetching import NeedsBrowser, ResolveError
from job_fetcher.resolve import resolve

USAGE = (
    "usage: resolve-posting.py <url>\n"
    "       resolve-posting.py --store -\n"
)


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


def main(argv: list[str]) -> int:
    arguments = argv[1:]
    if len(arguments) == 1 and not arguments[0].startswith("-"):
        return _resolve_mode(arguments[0])
    print(USAGE, file=sys.stderr, end="")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
