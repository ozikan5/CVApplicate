from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_fetcher import ats

FIXTURES = Path(__file__).parent / "fixtures"


def test_normalize_greenhouse_produces_expected_shape():
    raw = json.loads((FIXTURES / "greenhouse_sample.json").read_text())

    result = ats.normalize_greenhouse("Example Corp", "examplecorp", raw)

    assert result == [
        {
            "id": "examplecorp-4567890",
            "company": "Example Corp",
            "title": "Software Engineer Intern",
            "url": "https://boards.greenhouse.io/examplecorp/jobs/4567890",
            "location": "Remote",
            "posted_date": "2026-08-10",
        },
        {
            "id": "examplecorp-4567891",
            "company": "Example Corp",
            "title": "Data Scientist",
            "url": "https://boards.greenhouse.io/examplecorp/jobs/4567891",
            "location": "Chicago, IL",
            "posted_date": "2026-08-11",
        },
    ]


def test_normalize_greenhouse_skips_jobs_missing_required_fields():
    raw = {"jobs": [{"id": 1, "title": "Incomplete"}]}  # missing absolute_url

    result = ats.normalize_greenhouse("Example Corp", "examplecorp", raw)

    assert result == []


def test_normalize_lever_produces_expected_shape():
    raw = json.loads((FIXTURES / "lever_sample.json").read_text())

    result = ats.normalize_lever("Example Corp", "examplecorp", raw)

    assert result == [
        {
            "id": "examplecorp-a1b2c3d4-0000-1111-2222-333344445555",
            "company": "Example Corp",
            "title": "Backend Engineer",
            "url": "https://jobs.lever.co/examplecorp/a1b2c3d4-0000-1111-2222-333344445555",
            "location": "New York, NY",
            "posted_date": "2026-08-10",
        }
    ]


def test_normalize_lever_skips_jobs_missing_required_fields():
    raw = [{"id": "abc"}]  # missing text and hostedUrl

    result = ats.normalize_lever("Example Corp", "examplecorp", raw)

    assert result == []


def test_fetch_greenhouse_calls_correct_url_and_normalizes(monkeypatch):
    calls = {}

    def fake_fetch_json(url):
        calls["url"] = url
        return {
            "jobs": [
                {
                    "id": 1,
                    "title": "Engineer",
                    "updated_at": "2026-08-10T00:00:00-05:00",
                    "location": {"name": "Remote"},
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                }
            ]
        }

    monkeypatch.setattr(ats, "_fetch_json", fake_fetch_json)

    result = ats.fetch_greenhouse("Acme", "acme")

    assert calls["url"] == "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
    assert result == [
        {
            "id": "acme-1",
            "company": "Acme",
            "title": "Engineer",
            "url": "https://boards.greenhouse.io/acme/jobs/1",
            "location": "Remote",
            "posted_date": "2026-08-10",
        }
    ]


def test_fetch_lever_calls_correct_url(monkeypatch):
    calls = {}

    def fake_fetch_json(url):
        calls["url"] = url
        return []

    monkeypatch.setattr(ats, "_fetch_json", fake_fetch_json)

    result = ats.fetch_lever("Acme", "acme")

    assert calls["url"] == "https://api.lever.co/v0/postings/acme?mode=json"
    assert result == []


def test_fetch_postings_for_company_dispatches_by_ats(monkeypatch):
    monkeypatch.setattr(ats, "fetch_greenhouse", lambda name, slug: ["greenhouse-result"])
    monkeypatch.setattr(ats, "fetch_lever", lambda name, slug: ["lever-result"])

    greenhouse_company = {"name": "Acme", "slug": "acme", "ats": "greenhouse"}
    lever_company = {"name": "Acme", "slug": "acme", "ats": "lever"}

    assert ats.fetch_postings_for_company(greenhouse_company) == ["greenhouse-result"]
    assert ats.fetch_postings_for_company(lever_company) == ["lever-result"]


def test_fetch_postings_for_company_rejects_unknown_ats():
    with pytest.raises(ValueError):
        ats.fetch_postings_for_company({"name": "Acme", "slug": "acme", "ats": "workday"})
