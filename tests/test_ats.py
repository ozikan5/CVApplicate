from __future__ import annotations

import json
from pathlib import Path

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
