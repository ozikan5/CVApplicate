from __future__ import annotations

import json
import re

from job_fetcher.ats import normalize_greenhouse, normalize_lever
from job_fetcher.fetching import AdapterParseError, http_get
from job_fetcher.htmltext import description_from_html, description_from_plain


def _company_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _fetch_json(display_name: str, url: str):
    """Fetch and parse JSON, converting a parse failure into AdapterParseError."""
    try:
        return json.loads(http_get(url))
    except ValueError as error:
        raise AdapterParseError(f"{display_name} response was not JSON: {error}")


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
        raw = _fetch_json("Greenhouse", endpoint)

        company = raw.get("company_name") or _company_from_slug(board)
        postings = normalize_greenhouse(company, board, {"jobs": [raw]})
        if not postings:
            raise AdapterParseError("Greenhouse response missing required fields")
        posting = postings[0]
        posting["resolution"] = "api"
        return posting


_LEVER_RE = re.compile(
    r"^https?://jobs\.(?:eu\.)?lever\.co/([^/?#]+)/([0-9a-fA-F-]{36})"
)


class LeverAdapter(Adapter):
    name = "lever"

    def matches(self, url: str) -> bool:
        return _LEVER_RE.match(url) is not None

    def fetch(self, url: str) -> dict:
        match = _LEVER_RE.match(url)
        if match is None:
            raise AdapterParseError(f"not a Lever posting URL: {url}")
        slug, posting_id = match.group(1), match.group(2)
        endpoint = f"https://api.lever.co/v0/postings/{slug}/{posting_id}"
        raw = _fetch_json("Lever", endpoint)
        if not isinstance(raw, dict):
            raise AdapterParseError("Lever returned a board, not a single posting")

        postings = normalize_lever(_company_from_slug(slug), slug, [raw])
        if not postings:
            raise AdapterParseError("Lever response missing required fields")
        posting = postings[0]
        posting["resolution"] = "api"
        return posting


_WORKDAY_RE = re.compile(
    r"^https?://([^./]+)\.([a-z0-9]+)\.myworkdayjobs\.com(/[^?#]*)"
)
_LOCALE_RE = re.compile(r"^[a-z]{2}(?:-[A-Za-z]{2})?$")


class WorkdayAdapter(Adapter):
    name = "workday"

    def matches(self, url: str) -> bool:
        match = _WORKDAY_RE.match(url)
        return match is not None and "/job/" in match.group(3)

    def fetch(self, url: str) -> dict:
        match = _WORKDAY_RE.match(url)
        if match is None:
            raise AdapterParseError(f"not a Workday URL: {url}")
        tenant, datacenter, path = match.group(1), match.group(2), match.group(3)

        segments = [segment for segment in path.split("/") if segment]
        if segments and _LOCALE_RE.match(segments[0]):
            segments = segments[1:]
        if len(segments) < 3 or segments[1] != "job":
            raise AdapterParseError(f"unrecognised Workday path: {path}")
        site = segments[0]
        job_path = "/".join(segments[1:])

        endpoint = (
            f"https://{tenant}.{datacenter}.myworkdayjobs.com"
            f"/wday/cxs/{tenant}/{site}/{job_path}"
        )
        raw = _fetch_json("Workday", endpoint)

        info = raw.get("jobPostingInfo") or {}
        requisition_id = info.get("jobReqId")
        title = info.get("title")
        if not requisition_id or not title:
            raise AdapterParseError(
                "Workday response missing jobPostingInfo.jobReqId or .title"
            )

        return {
            "id": f"workday-{tenant}-{requisition_id}",
            "company": _company_from_slug(tenant),
            "title": title,
            "url": info.get("externalUrl") or url,
            "location": info.get("location") or "Unknown",
            "posted_date": (info.get("startDate") or "")[:10],
            "description": description_from_html(info.get("jobDescription")),
            "resolution": "api",
        }


_ASHBY_RE = re.compile(
    r"^https?://jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-fA-F-]{36})"
)


class AshbyAdapter(Adapter):
    name = "ashby"

    def matches(self, url: str) -> bool:
        return _ASHBY_RE.match(url) is not None

    def fetch(self, url: str) -> dict:
        match = _ASHBY_RE.match(url)
        if match is None:
            raise AdapterParseError(f"not an Ashby posting URL: {url}")
        org, posting_id = match.group(1), match.group(2)
        endpoint = f"https://api.ashbyhq.com/posting-api/job-board/{org}"
        raw = _fetch_json("Ashby", endpoint)

        job = None
        for candidate in raw.get("jobs") or []:
            if candidate.get("id") == posting_id:
                job = candidate
                break
        if job is None:
            raise AdapterParseError(
                f"posting {posting_id} is not on the {org} Ashby board"
            )
        if not job.get("title"):
            raise AdapterParseError("Ashby posting missing title")

        return {
            "id": f"ashby-{org}-{posting_id}",
            "company": _company_from_slug(org),
            "title": job["title"],
            "url": job.get("jobUrl") or url,
            "location": job.get("location") or "Unknown",
            "posted_date": (job.get("publishedAt") or "")[:10],
            "description": (
                description_from_plain(job.get("descriptionPlain"))
                or description_from_html(job.get("descriptionHtml"))
            ),
            "resolution": "api",
        }


_SMARTRECRUITERS_RE = re.compile(
    r"^https?://jobs\.smartrecruiters\.com/([^/?#]+)/(\d+)"
)
_SMARTRECRUITERS_SECTIONS = (
    "jobDescription",
    "qualifications",
    "additionalInformation",
)


class SmartRecruitersAdapter(Adapter):
    name = "smartrecruiters"

    def matches(self, url: str) -> bool:
        return _SMARTRECRUITERS_RE.match(url) is not None

    def fetch(self, url: str) -> dict:
        match = _SMARTRECRUITERS_RE.match(url)
        if match is None:
            raise AdapterParseError(f"not a SmartRecruiters posting URL: {url}")
        company_id, posting_id = match.group(1), match.group(2)
        endpoint = (
            f"https://api.smartrecruiters.com/v1/companies/{company_id}"
            f"/postings/{posting_id}"
        )
        raw = _fetch_json("SmartRecruiters", endpoint)

        title = raw.get("name")
        if not title:
            raise AdapterParseError("SmartRecruiters response missing name")

        sections = (raw.get("jobAd") or {}).get("sections") or {}
        section_html = " ".join(
            (sections.get(key) or {}).get("text") or ""
            for key in _SMARTRECRUITERS_SECTIONS
        )

        return {
            "id": f"smartrecruiters-{company_id}-{posting_id}",
            "company": (raw.get("company") or {}).get("name") or company_id,
            "title": title,
            "url": raw.get("postingUrl") or url,
            "location": (raw.get("location") or {}).get("fullLocation") or "Unknown",
            "posted_date": (raw.get("releasedDate") or "")[:10],
            "description": description_from_html(section_html),
            "resolution": "api",
        }


ADAPTERS = [
    GreenhouseAdapter(),
    LeverAdapter(),
    WorkdayAdapter(),
    AshbyAdapter(),
    SmartRecruitersAdapter(),
]


def find_adapter(url: str):
    for adapter in ADAPTERS:
        if adapter.matches(url):
            return adapter
    return None
