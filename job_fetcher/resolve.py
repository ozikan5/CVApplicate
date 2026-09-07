from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlparse

from job_fetcher.fetching import NeedsBrowser
from job_fetcher.htmltext import MAX_DESCRIPTION_LENGTH, description_from_html, strip_html

_JSONLD_RE = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.DOTALL | re.IGNORECASE,
)


def url_id(url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return f"url-{digest[:12]}"


def _iter_nodes(data):
    if isinstance(data, list):
        for item in data:
            for node in _iter_nodes(item):
                yield node
    elif isinstance(data, dict):
        yield data
        for key in ("@graph", "itemListElement"):
            if key in data:
                for node in _iter_nodes(data[key]):
                    yield node


def _is_job_posting(node: dict) -> bool:
    node_type = node.get("@type")
    if isinstance(node_type, str):
        return node_type == "JobPosting"
    if isinstance(node_type, list):
        return "JobPosting" in node_type
    return False


def _jsonld_company(node: dict):
    organization = node.get("hiringOrganization")
    if isinstance(organization, dict):
        return organization.get("name")
    if isinstance(organization, str):
        return organization
    return None


def _jsonld_location(node: dict) -> str:
    location = node.get("jobLocation")
    if isinstance(location, list):
        location = location[0] if location else None
    if not isinstance(location, dict):
        return "Unknown"
    address = location.get("address")
    if not isinstance(address, dict):
        return "Unknown"
    parts = [
        address.get("addressLocality"),
        address.get("addressRegion"),
    ]
    joined = ", ".join(part for part in parts if part)
    return joined or address.get("addressCountry") or "Unknown"


def _posting_from_jsonld(node: dict, url: str):
    title = node.get("title")
    company = _jsonld_company(node)
    if not title or not company:
        return None
    return {
        "id": url_id(url),
        "company": company,
        "title": title,
        "url": url,
        "location": _jsonld_location(node),
        "posted_date": (node.get("datePosted") or "")[:10],
        "description": description_from_html(node.get("description")),
        "resolution": "jsonld",
    }


def extract_jsonld_posting(html_text: str, url: str):
    for block in _JSONLD_RE.findall(html_text):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for node in _iter_nodes(data):
            if _is_job_posting(node):
                posting = _posting_from_jsonld(node, url)
                if posting is not None:
                    return posting
    return None


RAW_TEXT_MAX_LENGTH = 20000
JS_SHELL_TEXT_THRESHOLD = 400

_OG_TITLE_RE = re.compile(
    r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']*)[\"']",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)


def extract_hints(html_text: str, url: str) -> dict:
    og_match = _OG_TITLE_RE.search(html_text)
    title_match = _TITLE_RE.search(html_text)
    return {
        "og_title": og_match.group(1).strip() if og_match else None,
        "document_title": (
            " ".join(title_match.group(1).split()) if title_match else None
        ),
        "domain": urlparse(url).netloc,
    }


def resolve_generic(html_text: str, url: str) -> dict:
    text = strip_html(html_text)
    if len(text) < JS_SHELL_TEXT_THRESHOLD:
        raise NeedsBrowser(
            f"page rendered no job description without a browser: {url}"
        )
    return {
        "id": url_id(url),
        "company": None,
        "title": None,
        "url": url,
        "location": None,
        "posted_date": "",
        "description": text[:MAX_DESCRIPTION_LENGTH],
        "resolution": "html",
        "needs_extraction": True,
        "raw_text": text[:RAW_TEXT_MAX_LENGTH],
        "hints": extract_hints(html_text, url),
    }
