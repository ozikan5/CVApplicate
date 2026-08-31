from __future__ import annotations

import os
import re

import yaml

_INTERN_RE = re.compile(r"\bintern(s|ship)?\b", re.IGNORECASE)


def load_filters(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def matches_filters(posting: dict, filters: dict) -> bool:
    title = (posting.get("title") or "").lower()
    location = (posting.get("location") or "").lower()

    location_keywords = [k.lower() for k in filters.get("location_keywords") or []]
    if location_keywords and not any(k in location for k in location_keywords):
        return False

    if filters.get("require_internship") and not _INTERN_RE.search(title):
        return False

    title_keywords = [k.lower() for k in filters.get("title_keywords") or []]
    if title_keywords and not any(k in title for k in title_keywords):
        return False

    return True
