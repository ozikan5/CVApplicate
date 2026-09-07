from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_fetcher import adapters
from job_fetcher.fetching import AdapterParseError

FIXTURES = Path(__file__).parent / "fixtures"


def _stub_http_get(monkeypatch, body, expected_url=None):
    calls = []

    def fake_http_get(url, accept="application/json"):
        calls.append(url)
        if expected_url is not None:
            assert url == expected_url
        return body

    monkeypatch.setattr(adapters, "http_get", fake_http_get)
    return calls


def test_find_adapter_matches_greenhouse_job_urls():
    adapter = adapters.find_adapter(
        "https://job-boards.greenhouse.io/stripe/jobs/8172508"
    )
    assert adapter is not None
    assert adapter.name == "greenhouse"


def test_find_adapter_ignores_greenhouse_marketing_pages():
    assert adapters.find_adapter("https://www.greenhouse.io/pricing") is None
    assert adapters.find_adapter("https://job-boards.greenhouse.io/stripe") is None


def test_find_adapter_returns_none_for_an_unknown_host():
    assert adapters.find_adapter("https://careers.example.com/jobs/42") is None


def test_greenhouse_adapter_produces_the_expected_posting(monkeypatch):
    body = (FIXTURES / "greenhouse_job.json").read_text()
    _stub_http_get(
        monkeypatch,
        body,
        expected_url="https://boards-api.greenhouse.io/v1/boards/stripe/jobs/8172508?content=true",
    )

    posting = adapters.GreenhouseAdapter().fetch(
        "https://job-boards.greenhouse.io/stripe/jobs/8172508"
    )

    assert posting == {
        "id": "stripe-8172508",
        "company": "Stripe",
        "title": "Abuse Investigator",
        "url": "https://stripe.com/jobs/search?gh_jid=8172508",
        "location": "Dublin",
        "posted_date": "2026-09-04",
        "description": "Investigate abuse. Python and SQL required.",
        "resolution": "api",
    }


def test_greenhouse_adapter_id_matches_the_nightly_fetch_id(monkeypatch):
    """The dedup property: a pasted link must produce the id the fetcher produces."""
    from job_fetcher import ats

    raw = json.loads((FIXTURES / "greenhouse_job.json").read_text())
    nightly = ats.normalize_greenhouse("Stripe", "stripe", {"jobs": [raw]})

    _stub_http_get(monkeypatch, json.dumps(raw))
    resolved = adapters.GreenhouseAdapter().fetch(
        "https://job-boards.greenhouse.io/stripe/jobs/8172508"
    )

    assert resolved["id"] == nightly[0]["id"]


def test_greenhouse_adapter_raises_when_required_fields_are_missing(monkeypatch):
    _stub_http_get(monkeypatch, json.dumps({"id": 1}))

    with pytest.raises(AdapterParseError):
        adapters.GreenhouseAdapter().fetch(
            "https://job-boards.greenhouse.io/stripe/jobs/1"
        )


def test_find_adapter_matches_lever_job_urls():
    adapter = adapters.find_adapter(
        "https://jobs.lever.co/palantir/ac978161-6f46-4f6b-ad9e-a258e642751c"
    )
    assert adapter is not None
    assert adapter.name == "lever"


def test_find_adapter_ignores_a_lever_board_root():
    assert adapters.find_adapter("https://jobs.lever.co/palantir") is None


def test_lever_adapter_produces_the_expected_posting(monkeypatch):
    body = (FIXTURES / "lever_job.json").read_text()
    _stub_http_get(
        monkeypatch,
        body,
        expected_url=(
            "https://api.lever.co/v0/postings/palantir"
            "/ac978161-6f46-4f6b-ad9e-a258e642751c"
        ),
    )

    posting = adapters.LeverAdapter().fetch(
        "https://jobs.lever.co/palantir/ac978161-6f46-4f6b-ad9e-a258e642751c"
    )

    assert posting == {
        "id": "palantir-ac978161-6f46-4f6b-ad9e-a258e642751c",
        "company": "Palantir",
        "title": "Administrative Business Partner",
        "url": "https://jobs.lever.co/palantir/ac978161-6f46-4f6b-ad9e-a258e642751c",
        "location": "London, United Kingdom",
        "posted_date": "2024-03-25",
        "description": "Support the team. Calendar management required.",
        "resolution": "api",
    }


def test_lever_adapter_raises_when_required_fields_are_missing(monkeypatch):
    _stub_http_get(monkeypatch, json.dumps({"id": "x"}))

    with pytest.raises(AdapterParseError):
        adapters.LeverAdapter().fetch(
            "https://jobs.lever.co/palantir/ac978161-6f46-4f6b-ad9e-a258e642751c"
        )


WORKDAY_PAGE_URL = (
    "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite"
    "/job/Israel-Yokneam/Senior-Software-Engineer--NVLINK_JR2004601"
)
WORKDAY_ENDPOINT = (
    "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite"
    "/job/Israel-Yokneam/Senior-Software-Engineer--NVLINK_JR2004601"
)


def test_find_adapter_matches_workday_job_urls():
    adapter = adapters.find_adapter(WORKDAY_PAGE_URL)
    assert adapter is not None
    assert adapter.name == "workday"


def test_find_adapter_ignores_a_workday_search_page():
    assert adapters.find_adapter(
        "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
    ) is None


def test_workday_adapter_strips_the_locale_segment(monkeypatch):
    body = (FIXTURES / "workday_job.json").read_text()
    calls = _stub_http_get(monkeypatch, body)

    adapters.WorkdayAdapter().fetch(WORKDAY_PAGE_URL)

    assert calls == [WORKDAY_ENDPOINT]


def test_workday_adapter_handles_a_url_without_a_locale(monkeypatch):
    body = (FIXTURES / "workday_job.json").read_text()
    calls = _stub_http_get(monkeypatch, body)

    adapters.WorkdayAdapter().fetch(WORKDAY_PAGE_URL.replace("/en-US", ""))

    assert calls == [WORKDAY_ENDPOINT]


def test_workday_adapter_produces_the_expected_posting(monkeypatch):
    body = (FIXTURES / "workday_job.json").read_text()
    _stub_http_get(monkeypatch, body)

    posting = adapters.WorkdayAdapter().fetch(WORKDAY_PAGE_URL)

    assert posting == {
        "id": "workday-nvidia-JR2004601",
        "company": "Nvidia",
        "title": "Senior Software Engineer, NVLINK",
        "url": (
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
            "/job/Israel-Yokneam/Senior-Software-Engineer--NVLINK_JR2004601"
        ),
        "location": "Israel, Yokneam",
        "posted_date": "2026-09-07",
        "description": "Work on NVLINK. C++ and CUDA required.",
        "resolution": "api",
    }


def test_workday_adapter_never_uses_the_legal_hiring_entity(monkeypatch):
    """hiringOrganization.name is a subsidiary; it must not reach the posting."""
    body = (FIXTURES / "workday_job.json").read_text()
    _stub_http_get(monkeypatch, body)

    posting = adapters.WorkdayAdapter().fetch(WORKDAY_PAGE_URL)

    assert "Mellanox" not in json.dumps(posting)


def test_workday_adapter_ignores_the_relative_postedon_string(monkeypatch):
    body = (FIXTURES / "workday_job.json").read_text()
    _stub_http_get(monkeypatch, body)

    posting = adapters.WorkdayAdapter().fetch(WORKDAY_PAGE_URL)

    assert posting["posted_date"] == "2026-09-07"
    assert "Posted" not in posting["posted_date"]


def test_workday_adapter_raises_when_jobpostinginfo_is_missing(monkeypatch):
    _stub_http_get(monkeypatch, json.dumps({"userAuthenticated": False}))

    with pytest.raises(AdapterParseError):
        adapters.WorkdayAdapter().fetch(WORKDAY_PAGE_URL)
