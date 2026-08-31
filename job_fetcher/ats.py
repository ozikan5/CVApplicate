from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser


_BLOCK_TAGS = {"p", "li", "ul", "ol", "div", "br", "tr", "td", "h1", "h2", "h3", "h4", "h5", "h6"}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data):
        self._chunks.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self._chunks.append(" ")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self._chunks.append(" ")

    def text(self) -> str:
        return " ".join("".join(self._chunks).split())


def _strip_html(html_text: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html_text)
    return parser.text()


MAX_DESCRIPTION_LENGTH = 6000


def _description_from_html(html_text: str | None) -> str | None:
    if not html_text:
        return None
    stripped = _strip_html(html_text)
    if not stripped:
        return None
    return stripped[:MAX_DESCRIPTION_LENGTH]


def _description_from_plain(plain_text: str | None) -> str | None:
    if not plain_text:
        return None
    collapsed = " ".join(plain_text.split())
    if not collapsed:
        return None
    return collapsed[:MAX_DESCRIPTION_LENGTH]


def normalize_greenhouse(company_name: str, slug: str, raw: dict) -> list[dict]:
    postings = []
    for job in raw.get("jobs", []):
        if "id" not in job or "title" not in job or "absolute_url" not in job:
            print(
                f"warning: skipping malformed Greenhouse job (missing required fields): {job!r}",
                file=sys.stderr,
            )
            continue
        postings.append(
            {
                "id": f"{slug}-{job['id']}",
                "company": company_name,
                "title": job["title"],
                "url": job["absolute_url"],
                "location": (job.get("location") or {}).get("name", "Unknown"),
                "posted_date": job.get("updated_at", "")[:10],
                "description": _description_from_html(job.get("content")),
            }
        )
    return postings


def normalize_lever(company_name: str, slug: str, raw: list) -> list[dict]:
    postings = []
    for job in raw:
        if "id" not in job or "text" not in job or "hostedUrl" not in job:
            print(
                f"warning: skipping malformed Lever job (missing required fields): {job!r}",
                file=sys.stderr,
            )
            continue
        created_at = job.get("createdAt")
        if created_at is not None:
            posted_date = datetime.fromtimestamp(created_at / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        else:
            posted_date = ""
        postings.append(
            {
                "id": f"{slug}-{job['id']}",
                "company": company_name,
                "title": job["text"],
                "url": job["hostedUrl"],
                "location": (job.get("categories") or {}).get("location", "Unknown"),
                "posted_date": posted_date,
                "description": _description_from_plain(job.get("descriptionPlain"))
                or _description_from_html(job.get("description")),
            }
        )
    return postings


USER_AGENT = "CVApplicate-JobFetcher/1.0 (personal job search tool)"


def _fetch_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_greenhouse(company_name: str, slug: str) -> list[dict]:
    raw = _fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    return normalize_greenhouse(company_name, slug, raw)


def fetch_lever(company_name: str, slug: str) -> list[dict]:
    raw = _fetch_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    return normalize_lever(company_name, slug, raw)


def fetch_postings_for_company(company: dict) -> list[dict]:
    ats_type = company["ats"]
    if ats_type == "greenhouse":
        return fetch_greenhouse(company["name"], company["slug"])
    if ats_type == "lever":
        return fetch_lever(company["name"], company["slug"])
    raise ValueError(f"unknown ats type: {ats_type!r}")
