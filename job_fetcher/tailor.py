from __future__ import annotations

import os
import re
import unicodedata

MAX_SLUG_LENGTH = 80

_COMMENT = re.compile(r"\s+#.*$")


def parse_queue(path: str):
    """Read the URL queue. Returns (urls, skipped_lines).

    The queue is owned by the user and never rewritten: comments, blank lines and
    duplicates are all tolerated, and anything that is not an http(s) URL is
    reported rather than guessed at.
    """
    if not os.path.exists(path):
        return [], []

    urls = []
    skipped = []
    seen = set()
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            line = _COMMENT.sub("", line).strip()
            if not line:
                continue
            if not line.startswith(("http://", "https://")):
                skipped.append(line)
                continue
            if line in seen:
                continue
            seen.add(line)
            urls.append(line)
    return urls, skipped


def _slugify(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text or "")
    folded = folded.encode("ascii", "ignore").decode("ascii")
    folded = re.sub(r"[^A-Za-z0-9]+", "-", folded).strip("-").lower()
    return re.sub(r"-{2,}", "-", folded)


def packet_slug(company: str, role: str, posting_id: str, existing) -> str:
    base = f"{_slugify(company)}-{_slugify(role)}".strip("-")
    base = re.sub(r"-{2,}", "-", base)
    if len(base) > MAX_SLUG_LENGTH:
        base = base[:MAX_SLUG_LENGTH].rstrip("-")
    if base not in existing:
        return base

    suffix = _slugify(posting_id).split("-")[-1]
    room = MAX_SLUG_LENGTH - len(suffix) - 1
    return f"{base[:room].rstrip('-')}-{suffix}"
