from __future__ import annotations

import json
import re

from job_fetcher.ats import normalize_greenhouse
from job_fetcher.fetching import AdapterParseError, http_get


def _company_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


class Adapter:
    name = ""

    def matches(self, url: str) -> bool:
        raise NotImplementedError

    def fetch(self, url: str) -> dict:
        raise NotImplementedError


_GREENHOUSE_RE = re.compile(
    r"^https?://(?:job-boards|boards)\.greenhouse\.io/([^/?#]+)/jobs/(\d+)"
)


class GreenhouseAdapter(Adapter):
    name = "greenhouse"

    def matches(self, url: str) -> bool:
        return _GREENHOUSE_RE.match(url) is not None

    def fetch(self, url: str) -> dict:
        match = _GREENHOUSE_RE.match(url)
        if match is None:
            raise AdapterParseError(f"not a Greenhouse job URL: {url}")
        board, job_id = match.group(1), match.group(2)
        endpoint = (
            f"https://boards-api.greenhouse.io/v1/boards/{board}"
            f"/jobs/{job_id}?content=true"
        )
        try:
            raw = json.loads(http_get(endpoint))
        except ValueError as error:
            raise AdapterParseError(f"Greenhouse response was not JSON: {error}")

        company = raw.get("company_name") or _company_from_slug(board)
        postings = normalize_greenhouse(company, board, {"jobs": [raw]})
        if not postings:
            raise AdapterParseError("Greenhouse response missing required fields")
        posting = postings[0]
        posting["resolution"] = "api"
        return posting


ADAPTERS = [GreenhouseAdapter()]


def find_adapter(url: str):
    for adapter in ADAPTERS:
        if adapter.matches(url):
            return adapter
    return None
