# Job Postings Fetcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone script that fetches job postings from companies' Greenhouse/Lever ATS APIs, stores them locally, detects new ones since the last run, and emails a summary — running daily via macOS `launchd`.

**Architecture:** A small `job_fetcher` package holds all testable logic (config loading, ATS adapters, local storage/dedup, email notification, `.env` loading), each in its own single-responsibility module. A thin top-level script, `fetch-postings.py`, wires them together and is the thing `launchd` actually runs. Personal data (real company list, fetched postings, SMTP credentials) lives in gitignored `.local.yaml`/`.env` files; the repo only ships generic `.example` templates.

**Tech Stack:** Python 3.10, stdlib `urllib`/`smtplib`/`email` (no `requests` dependency — keeps this close to `check-cv-text.py`'s zero-dependency style), `PyYAML` for the YAML config/storage files, `pytest` for tests.

---

## File Structure

```
CVApplicate/
├── fetch-postings.py                        # CLI entry point, run by launchd
├── job_fetcher/
│   ├── __init__.py
│   ├── env.py                                # .env loader
│   ├── config.py                             # companies.local.yaml loader
│   ├── ats.py                                # Greenhouse/Lever adapters + normalization
│   ├── store.py                              # postings.local.yaml load/save/dedup
│   └── notify.py                             # email summary builder + sender
├── tests/
│   ├── fixtures/
│   │   ├── greenhouse_sample.json
│   │   └── lever_sample.json
│   ├── test_env.py
│   ├── test_config.py
│   ├── test_ats.py
│   ├── test_store.py
│   ├── test_notify.py
│   └── test_fetch_postings.py
├── launchd/
│   └── com.cvapplicate.fetch-postings.plist.example
├── companies.example.yaml                    # ships generic
├── companies.local.yaml                      # gitignored, user's real list (not created here)
├── .env.example                               # ships generic
├── requirements.txt
└── conftest.py                                # empty; makes `job_fetcher` importable from tests/
```

---

## Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `companies.example.yaml`
- Create: `job_fetcher/__init__.py`
- Create: `conftest.py`
- Create: `tests/fixtures/greenhouse_sample.json`
- Create: `tests/fixtures/lever_sample.json`

- [x] **Step 1: Create `requirements.txt`**

```
PyYAML>=6.0

pytest>=7.0
```

- [x] **Step 2: Create `.env.example`**

```
# Copy this file to .env and fill in real values.
# .env is gitignored — never commit real credentials.

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_APP_PASSWORD=your-16-character-app-password
NOTIFY_TO=you@gmail.com
```

- [x] **Step 3: Create `companies.example.yaml`**

```yaml
# Copy this file to companies.local.yaml and fill in real companies you want to
# track. companies.local.yaml is gitignored — your real target list never gets
# committed to this template repo.
#
# ats: which Applicant Tracking System the company uses.
#   - greenhouse: find the slug in the company's careers URL, e.g.
#     https://job-boards.greenhouse.io/<slug> or https://boards.greenhouse.io/<slug>
#   - lever: find the slug in the company's careers URL, e.g.
#     https://jobs.lever.co/<slug>

- name: "Example Corp"
  slug: "examplecorp"
  ats: greenhouse
```

- [x] **Step 4: Create `job_fetcher/__init__.py`**

Empty file — just marks `job_fetcher` as a package.

- [x] **Step 5: Create `conftest.py`** (repo root)

```python
# Empty on purpose: its presence makes pytest add the repo root to sys.path,
# so tests can `import job_fetcher` regardless of where pytest is invoked from.
```

- [x] **Step 6: Create `tests/fixtures/greenhouse_sample.json`**

```json
{
  "jobs": [
    {
      "id": 4567890,
      "title": "Software Engineer Intern",
      "updated_at": "2026-08-10T09:15:00-05:00",
      "location": {"name": "Remote"},
      "absolute_url": "https://boards.greenhouse.io/examplecorp/jobs/4567890"
    },
    {
      "id": 4567891,
      "title": "Data Scientist",
      "updated_at": "2026-08-11T14:30:00-05:00",
      "location": {"name": "Chicago, IL"},
      "absolute_url": "https://boards.greenhouse.io/examplecorp/jobs/4567891"
    }
  ]
}
```

- [x] **Step 7: Create `tests/fixtures/lever_sample.json`**

```json
[
  {
    "id": "a1b2c3d4-0000-1111-2222-333344445555",
    "text": "Backend Engineer",
    "categories": {"location": "New York, NY", "team": "Engineering"},
    "hostedUrl": "https://jobs.lever.co/examplecorp/a1b2c3d4-0000-1111-2222-333344445555",
    "createdAt": 1786320000000
  }
]
```

- [x] **Step 8: Install dependencies**

Run: `pip install -r requirements.txt`

- [x] **Step 9: Verify pytest runs cleanly with no tests yet**

Run: `python3 -m pytest -v`
Expected: `no tests ran` (exit code 5) — confirms pytest + conftest.py setup works before any real code exists.

- [x] **Step 10: Commit**

```bash
git add requirements.txt .env.example companies.example.yaml job_fetcher/__init__.py conftest.py tests/fixtures/
git commit -m "Scaffold job postings fetcher project structure"
```

---

## Task 2: `.env` loader

**Files:**
- Create: `job_fetcher/env.py`
- Test: `tests/test_env.py`

- [x] **Step 1: Write the failing tests**

`tests/test_env.py`:
```python
from __future__ import annotations

import os

from job_fetcher import env


def test_load_dotenv_does_nothing_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("FETCHER_TEST_VAR", raising=False)

    env.load_dotenv(str(tmp_path / "missing.env"))

    assert "FETCHER_TEST_VAR" not in os.environ


def test_load_dotenv_sets_values_from_file(tmp_path, monkeypatch):
    monkeypatch.delenv("FETCHER_TEST_VAR", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\n\nFETCHER_TEST_VAR=hello\n")

    env.load_dotenv(str(env_file))

    assert os.environ["FETCHER_TEST_VAR"] == "hello"


def test_load_dotenv_does_not_override_existing_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("FETCHER_TEST_VAR", "original")
    env_file = tmp_path / ".env"
    env_file.write_text("FETCHER_TEST_VAR=from_file\n")

    env.load_dotenv(str(env_file))

    assert os.environ["FETCHER_TEST_VAR"] == "original"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_env.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_fetcher.env'`

- [x] **Step 3: Write the implementation**

`job_fetcher/env.py`:
```python
from __future__ import annotations

import os


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_env.py -v`
Expected: 3 passed

- [x] **Step 5: Commit**

```bash
git add job_fetcher/env.py tests/test_env.py
git commit -m "Add .env loader for job postings fetcher"
```

---

## Task 3: Company config loader

**Files:**
- Create: `job_fetcher/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:
```python
from __future__ import annotations

import pytest

from job_fetcher import config


def test_load_companies_happy_path(tmp_path):
    path = tmp_path / "companies.local.yaml"
    path.write_text(
        "- name: Acme\n  slug: acme\n  ats: greenhouse\n"
        "- name: Beta Inc\n  slug: beta\n  ats: lever\n"
    )

    result = config.load_companies(str(path))

    assert result == [
        {"name": "Acme", "slug": "acme", "ats": "greenhouse"},
        {"name": "Beta Inc", "slug": "beta", "ats": "lever"},
    ]


def test_load_companies_missing_file_raises_config_error(tmp_path):
    with pytest.raises(config.ConfigError):
        config.load_companies(str(tmp_path / "missing.yaml"))


def test_load_companies_empty_file_raises_config_error(tmp_path):
    path = tmp_path / "companies.local.yaml"
    path.write_text("")

    with pytest.raises(config.ConfigError):
        config.load_companies(str(path))


def test_load_companies_missing_required_key_raises_config_error(tmp_path):
    path = tmp_path / "companies.local.yaml"
    path.write_text("- name: Acme\n  slug: acme\n")  # missing ats

    with pytest.raises(config.ConfigError):
        config.load_companies(str(path))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_fetcher.config'`

- [ ] **Step 3: Write the implementation**

`job_fetcher/config.py`:
```python
from __future__ import annotations

import yaml

REQUIRED_KEYS = {"name", "slug", "ats"}


class ConfigError(Exception):
    pass


def load_companies(path: str) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigError(
            f"{path} not found. Copy companies.example.yaml to {path} and fill in "
            "the companies you want to track."
        )

    if not data:
        raise ConfigError(f"{path} is empty. Add at least one company entry.")

    for entry in data:
        missing = REQUIRED_KEYS - entry.keys()
        if missing:
            raise ConfigError(f"company entry {entry!r} is missing required keys: {missing}")

    return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add job_fetcher/config.py tests/test_config.py
git commit -m "Add company config loader for job postings fetcher"
```

---

## Task 4: ATS response normalization (Greenhouse + Lever)

**Files:**
- Create: `job_fetcher/ats.py`
- Test: `tests/test_ats.py` (normalization tests only — network fetch tests are Task 5)

- [ ] **Step 1: Write the failing tests**

`tests/test_ats.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_fetcher.ats'`

- [ ] **Step 3: Write the implementation (normalization only — fetch functions added in Task 5)**

`job_fetcher/ats.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone


def normalize_greenhouse(company_name: str, slug: str, raw: dict) -> list[dict]:
    postings = []
    for job in raw.get("jobs", []):
        if "id" not in job or "title" not in job or "absolute_url" not in job:
            continue
        postings.append(
            {
                "id": f"{slug}-{job['id']}",
                "company": company_name,
                "title": job["title"],
                "url": job["absolute_url"],
                "location": job.get("location", {}).get("name", "Unknown"),
                "posted_date": job.get("updated_at", "")[:10],
            }
        )
    return postings


def normalize_lever(company_name: str, slug: str, raw: list) -> list[dict]:
    postings = []
    for job in raw:
        if "id" not in job or "text" not in job or "hostedUrl" not in job:
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
                "location": job.get("categories", {}).get("location", "Unknown"),
                "posted_date": posted_date,
            }
        )
    return postings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ats.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add job_fetcher/ats.py tests/test_ats.py
git commit -m "Add Greenhouse/Lever response normalization"
```

---

## Task 5: ATS network fetch + dispatcher

**Files:**
- Modify: `job_fetcher/ats.py`
- Test: `tests/test_ats.py` (add fetch/dispatch tests)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_ats.py`)

```python
import pytest


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
```

Also add the import at the top of `tests/test_ats.py` (it already imports `ats` via `from job_fetcher import ats` — reuse that; just add `import pytest` near the other imports).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ats.py -v`
Expected: FAIL — `AttributeError: module 'job_fetcher.ats' has no attribute '_fetch_json'` (and similar for `fetch_greenhouse`, `fetch_lever`, `fetch_postings_for_company`)

- [ ] **Step 3: Add fetch/dispatch functions**

Append to `job_fetcher/ats.py` (keep the existing `normalize_greenhouse`/`normalize_lever` and add these, plus the `json`/`urllib.request` imports at the top):

```python
# add to the top imports:
# import json
# import urllib.request

USER_AGENT = "CVApplicate-JobFetcher/1.0 (personal job search tool)"


def _fetch_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_greenhouse(company_name: str, slug: str) -> list[dict]:
    raw = _fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
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
```

`fetch_postings_for_company` dispatches via plain `if`/`elif` (not a dict of function references built at import time) so that monkeypatching `ats.fetch_greenhouse`/`ats.fetch_lever` in tests actually takes effect — a dict built once at import time would keep stale references to the original functions.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ats.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add job_fetcher/ats.py tests/test_ats.py
git commit -m "Add Greenhouse/Lever network fetch and ATS dispatcher"
```

---

## Task 6: Local postings store (load/save/dedup)

**Files:**
- Create: `job_fetcher/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_store.py`:
```python
from __future__ import annotations

from job_fetcher import store


def test_load_postings_returns_empty_list_when_file_missing(tmp_path):
    result = store.load_postings(str(tmp_path / "missing.yaml"))
    assert result == []


def test_save_and_load_roundtrip(tmp_path):
    path = str(tmp_path / "postings.yaml")
    postings = [
        {
            "id": "acme-1",
            "company": "Acme",
            "title": "Engineer",
            "url": "https://example.com/1",
            "location": "Remote",
            "posted_date": "2026-08-10",
            "first_seen": "2026-08-10",
            "notified": False,
        }
    ]

    store.save_postings(path, postings)
    loaded = store.load_postings(path)

    assert loaded == postings


def test_merge_new_postings_marks_new_entries():
    existing = []
    fetched = [
        {
            "id": "acme-1",
            "company": "Acme",
            "title": "Engineer",
            "url": "https://example.com/1",
            "location": "Remote",
            "posted_date": "2026-08-10",
        }
    ]

    merged, new_postings = store.merge_new_postings(existing, fetched, "2026-08-14")

    assert len(merged) == 1
    assert merged[0]["first_seen"] == "2026-08-14"
    assert merged[0]["notified"] is False
    assert new_postings == merged


def test_merge_new_postings_preserves_existing_entries_untouched():
    existing = [
        {
            "id": "acme-1",
            "company": "Acme",
            "title": "Engineer",
            "url": "https://example.com/1",
            "location": "Remote",
            "posted_date": "2026-08-10",
            "first_seen": "2026-08-01",
            "notified": True,
        }
    ]
    fetched = [
        {
            "id": "acme-1",
            "company": "Acme",
            "title": "Engineer",
            "url": "https://example.com/1",
            "location": "Remote",
            "posted_date": "2026-08-10",
        }
    ]

    merged, new_postings = store.merge_new_postings(existing, fetched, "2026-08-14")

    assert merged == existing
    assert new_postings == []


def test_merge_new_postings_keeps_postings_that_disappeared_from_feed():
    existing = [
        {
            "id": "acme-1",
            "company": "Acme",
            "title": "Engineer",
            "url": "https://example.com/1",
            "location": "Remote",
            "posted_date": "2026-08-10",
            "first_seen": "2026-08-01",
            "notified": True,
        }
    ]
    fetched = []  # posting closed, no longer in the ATS feed

    merged, new_postings = store.merge_new_postings(existing, fetched, "2026-08-14")

    assert merged == existing
    assert new_postings == []


def test_mark_notified_sets_flag_only_for_given_ids():
    postings = [
        {"id": "acme-1", "notified": False},
        {"id": "acme-2", "notified": False},
    ]

    store.mark_notified(postings, {"acme-1"})

    assert postings[0]["notified"] is True
    assert postings[1]["notified"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_fetcher.store'`

- [ ] **Step 3: Write the implementation**

`job_fetcher/store.py`:
```python
from __future__ import annotations

import os

import yaml


def load_postings(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or []


def save_postings(path: str, postings: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "# Fetched job postings. Generated by fetch-postings.py — do not hand-edit\n"
            "# except to delete entries you're no longer interested in.\n"
        )
        yaml.safe_dump(postings, f, sort_keys=False)


def merge_new_postings(
    existing: list[dict], fetched: list[dict], today: str
) -> tuple[list[dict], list[dict]]:
    existing_ids = {p["id"] for p in existing}
    merged = list(existing)
    new_postings = []
    for posting in fetched:
        if posting["id"] in existing_ids:
            continue
        posting = dict(posting)
        posting["first_seen"] = today
        posting["notified"] = False
        merged.append(posting)
        new_postings.append(posting)
        existing_ids.add(posting["id"])
    return merged, new_postings


def mark_notified(postings: list[dict], ids: set[str]) -> None:
    for posting in postings:
        if posting["id"] in ids:
            posting["notified"] = True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add job_fetcher/store.py tests/test_store.py
git commit -m "Add local postings store with dedup/merge logic"
```

---

## Task 7: Email notifier

**Files:**
- Create: `job_fetcher/notify.py`
- Test: `tests/test_notify.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_notify.py`:
```python
from __future__ import annotations

import pytest

from job_fetcher import notify


def test_build_summary_email_formats_postings():
    postings = [
        {
            "company": "Acme",
            "title": "Engineer",
            "location": "Remote",
            "url": "https://example.com/1",
        }
    ]

    subject, body = notify.build_summary_email(postings)

    assert subject == "1 new job posting(s)"
    assert "Acme: Engineer (Remote) — https://example.com/1" in body


def test_smtp_config_from_env_reads_all_values(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "me@example.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "secret")
    monkeypatch.setenv("NOTIFY_TO", "me@example.com")

    config = notify.smtp_config_from_env()

    assert config == {
        "host": "smtp.example.com",
        "port": 587,
        "user": "me@example.com",
        "password": "secret",
        "to": "me@example.com",
    }


def test_smtp_config_from_env_raises_when_missing(monkeypatch):
    for key in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_APP_PASSWORD", "NOTIFY_TO"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(notify.NotifyConfigError):
        notify.smtp_config_from_env()


def test_send_email_uses_starttls_login_and_sends(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=10):
            calls.append(("init", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, message):
            calls.append(("send", message["Subject"], message["To"]))

    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)

    config = {
        "host": "smtp.example.com",
        "port": 587,
        "user": "me@example.com",
        "password": "secret",
        "to": "friend@example.com",
    }

    notify.send_email("Subject line", "Body text", config)

    assert ("init", "smtp.example.com", 587) in calls
    assert ("starttls",) in calls
    assert ("login", "me@example.com", "secret") in calls
    assert ("send", "Subject line", "friend@example.com") in calls
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_notify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_fetcher.notify'`

- [ ] **Step 3: Write the implementation**

`job_fetcher/notify.py`:
```python
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


class NotifyConfigError(Exception):
    pass


def build_summary_email(new_postings: list[dict]) -> tuple[str, str]:
    subject = f"{len(new_postings)} new job posting(s)"
    lines = [
        f"- {p['company']}: {p['title']} ({p['location']}) — {p['url']}"
        for p in new_postings
    ]
    body = "\n".join(lines)
    return subject, body


def smtp_config_from_env() -> dict:
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_APP_PASSWORD", "NOTIFY_TO"]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise NotifyConfigError(f"missing required .env values: {', '.join(missing)}")
    return {
        "host": os.environ["SMTP_HOST"],
        "port": int(os.environ["SMTP_PORT"]),
        "user": os.environ["SMTP_USER"],
        "password": os.environ["SMTP_APP_PASSWORD"],
        "to": os.environ["NOTIFY_TO"],
    }


def send_email(subject: str, body: str, config: dict) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["user"]
    message["To"] = config["to"]
    message.set_content(body)

    with smtplib.SMTP(config["host"], config["port"], timeout=10) as server:
        server.starttls()
        server.login(config["user"], config["password"])
        server.send_message(message)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_notify.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add job_fetcher/notify.py tests/test_notify.py
git commit -m "Add email notifier for new job postings"
```

---

## Task 8: CLI entry point (`fetch-postings.py`)

**Files:**
- Create: `fetch-postings.py`
- Test: `tests/test_fetch_postings.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_fetch_postings.py`:
```python
from __future__ import annotations

import importlib.util
import pathlib


def _load_fetch_postings_module():
    spec = importlib.util.spec_from_file_location(
        "fetch_postings_script",
        pathlib.Path(__file__).parent.parent / "fetch-postings.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FAKE_POSTING = {
    "id": "examplecorp-1",
    "company": "Example Corp",
    "title": "Software Engineer",
    "url": "https://boards.greenhouse.io/examplecorp/jobs/1",
    "location": "Remote",
    "posted_date": "2026-08-10",
}


def _write_companies_file(tmp_path):
    companies_file = tmp_path / "companies.local.yaml"
    companies_file.write_text(
        "- name: Example Corp\n  slug: examplecorp\n  ats: greenhouse\n"
    )
    return companies_file


def test_main_writes_new_postings_and_marks_notified(tmp_path, monkeypatch):
    module = _load_fetch_postings_module()

    companies_file = _write_companies_file(tmp_path)
    postings_file = tmp_path / "postings.local.yaml"

    monkeypatch.setattr(module, "COMPANIES_PATH", str(companies_file))
    monkeypatch.setattr(module, "POSTINGS_PATH", str(postings_file))
    monkeypatch.setattr(module, "DELAY_BETWEEN_COMPANIES_SECONDS", 0)
    monkeypatch.setattr(module, "fetch_postings_for_company", lambda company: [FAKE_POSTING])

    sent = {}

    def fake_send_email(subject, body, config):
        sent["subject"] = subject

    monkeypatch.setattr(module, "send_email", fake_send_email)
    monkeypatch.setattr(module, "smtp_config_from_env", lambda: {})

    exit_code = module.main()

    assert exit_code == 0
    assert "1 new job posting" in sent["subject"]

    saved = module.load_postings(str(postings_file))
    assert len(saved) == 1
    assert saved[0]["notified"] is True


def test_main_leaves_notified_false_when_email_fails(tmp_path, monkeypatch):
    module = _load_fetch_postings_module()

    companies_file = _write_companies_file(tmp_path)
    postings_file = tmp_path / "postings.local.yaml"

    monkeypatch.setattr(module, "COMPANIES_PATH", str(companies_file))
    monkeypatch.setattr(module, "POSTINGS_PATH", str(postings_file))
    monkeypatch.setattr(module, "DELAY_BETWEEN_COMPANIES_SECONDS", 0)
    monkeypatch.setattr(module, "fetch_postings_for_company", lambda company: [FAKE_POSTING])

    def failing_send_email(subject, body, config):
        raise RuntimeError("smtp unreachable")

    monkeypatch.setattr(module, "send_email", failing_send_email)
    monkeypatch.setattr(module, "smtp_config_from_env", lambda: {})

    exit_code = module.main()

    assert exit_code == 0
    saved = module.load_postings(str(postings_file))
    assert saved[0]["notified"] is False


def test_main_returns_error_code_when_companies_config_missing(tmp_path, monkeypatch):
    module = _load_fetch_postings_module()

    monkeypatch.setattr(module, "COMPANIES_PATH", str(tmp_path / "missing.yaml"))
    monkeypatch.setattr(module, "POSTINGS_PATH", str(tmp_path / "postings.local.yaml"))

    exit_code = module.main()

    assert exit_code == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_fetch_postings.py -v`
Expected: FAIL — `FileNotFoundError` (script doesn't exist yet)

- [ ] **Step 3: Write the implementation**

`fetch-postings.py`:
```python
#!/usr/bin/env python3
"""Fetch job postings from configured companies' ATS APIs and email new ones.

Usage:
    ./fetch-postings.py

Reads companies.local.yaml for the list of companies to check, fetches current
postings from each company's ATS (Greenhouse or Lever), merges them into
postings.local.yaml, and emails a summary of anything new. Designed to run
once a day via launchd (see launchd/com.cvapplicate.fetch-postings.plist.example).

Exit codes: 0 = ran (with or without new postings), 2 = config/usage error.
"""

from __future__ import annotations

import datetime
import sys
import time

from job_fetcher.ats import fetch_postings_for_company
from job_fetcher.config import ConfigError, load_companies
from job_fetcher.env import load_dotenv
from job_fetcher.notify import build_summary_email, send_email, smtp_config_from_env
from job_fetcher.store import load_postings, mark_notified, merge_new_postings, save_postings

COMPANIES_PATH = "companies.local.yaml"
POSTINGS_PATH = "postings.local.yaml"
DELAY_BETWEEN_COMPANIES_SECONDS = 1


def main() -> int:
    load_dotenv()

    try:
        companies = load_companies(COMPANIES_PATH)
    except ConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    fetched = []
    for company in companies:
        try:
            fetched.extend(fetch_postings_for_company(company))
        except Exception as error:
            print(f"warning: failed to fetch {company['name']}: {error}", file=sys.stderr)
        time.sleep(DELAY_BETWEEN_COMPANIES_SECONDS)

    existing = load_postings(POSTINGS_PATH)
    today = datetime.date.today().isoformat()
    merged, _ = merge_new_postings(existing, fetched, today)
    save_postings(POSTINGS_PATH, merged)

    to_notify = [posting for posting in merged if not posting["notified"]]
    if to_notify:
        subject, body = build_summary_email(to_notify)
        try:
            config = smtp_config_from_env()
            send_email(subject, body, config)
        except Exception as error:
            print(f"warning: failed to send notification email: {error}", file=sys.stderr)
        else:
            mark_notified(merged, {posting["id"] for posting in to_notify})
            save_postings(POSTINGS_PATH, merged)

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Make the script executable and run tests to verify they pass**

Run: `chmod +x fetch-postings.py && python3 -m pytest tests/test_fetch_postings.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the full test suite**

Run: `python3 -m pytest -v`
Expected: all tests pass (env, config, ats, store, notify, fetch_postings)

- [ ] **Step 6: Commit**

```bash
git add fetch-postings.py tests/test_fetch_postings.py
git commit -m "Add fetch-postings.py CLI entry point"
```

---

## Task 9: Scheduling + documentation

**Files:**
- Create: `launchd/com.cvapplicate.fetch-postings.plist.example`
- Modify: `README.md`

- [ ] **Step 1: Create the launchd template**

`launchd/com.cvapplicate.fetch-postings.plist.example`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.cvapplicate.fetch-postings</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/ABSOLUTE/PATH/TO/CVApplicate/fetch-postings.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/ABSOLUTE/PATH/TO/CVApplicate</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/ABSOLUTE/PATH/TO/CVApplicate/fetch-postings.log</string>
    <key>StandardErrorPath</key>
    <string>/ABSOLUTE/PATH/TO/CVApplicate/fetch-postings.log</string>
</dict>
</plist>
```

- [ ] **Step 2: Add a section to `README.md`**

Add this section (placement: after the existing skills documentation, before any closing/license section):

```markdown
## Job Postings Fetcher

Pulls new job listings from companies' ATS APIs (Greenhouse, Lever) once a day and
emails you a summary. See
`docs/superpowers/specs/2026-08-14-job-postings-fetcher-design.md` for the full design.

### Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Copy `companies.example.yaml` to `companies.local.yaml` and fill in the companies
   you want to track (see the comments in that file for how to find each company's
   ATS slug).
3. Copy `.env.example` to `.env` and fill in your SMTP credentials — for Gmail, use
   an App Password (https://myaccount.google.com/apppasswords), not your normal
   password.
4. Run it once by hand to confirm it works: `python3 fetch-postings.py`
5. To run it automatically every day:
   - Copy `launchd/com.cvapplicate.fetch-postings.plist.example` to
     `~/Library/LaunchAgents/com.cvapplicate.fetch-postings.plist`
   - Replace every `/ABSOLUTE/PATH/TO/CVApplicate` placeholder in that copied file
     with this repo's actual absolute path (find it with `pwd`).
   - Load it: `launchctl load ~/Library/LaunchAgents/com.cvapplicate.fetch-postings.plist`
   - It now runs daily at 8:00am; check `fetch-postings.log` in the repo for output.
   - To stop it: `launchctl unload ~/Library/LaunchAgents/com.cvapplicate.fetch-postings.plist`

`companies.local.yaml`, `postings.local.yaml`, and `.env` are all gitignored — your
real target list, fetched postings, and credentials never get committed to this
template repo.
```

- [ ] **Step 3: Commit**

```bash
git add launchd/com.cvapplicate.fetch-postings.plist.example README.md
git commit -m "Add launchd scheduling template and README setup docs"
```

---

## Task 10: End-to-end manual verification

**Files:** none (verification only)

- [ ] **Step 1: Set up real local config**

```bash
cp companies.example.yaml companies.local.yaml
```

Edit `companies.local.yaml` and replace the placeholder entry with one real company
you know posts jobs via Greenhouse or Lever (check their careers page URL — if it's
`job-boards.greenhouse.io/<slug>` or `boards.greenhouse.io/<slug>`, use `ats: greenhouse`
with that `<slug>`; if it's `jobs.lever.co/<slug>`, use `ats: lever`).

- [ ] **Step 2: Run without email configured first**

Run: `python3 fetch-postings.py`
Expected: postings fetched and written to `postings.local.yaml`; a `warning: failed to
send notification email` line on stderr (no `.env` yet) — confirms the "email fails but
postings still save" error-handling path works with real data, not just fixtures.

- [ ] **Step 3: Verify the postings file**

Run: `cat postings.local.yaml`
Expected: one or more entries with `notified: false`, each with `id`, `company`, `title`,
`url`, `location`, `posted_date`, `first_seen` populated with real values.

- [ ] **Step 4: Configure email and re-run**

```bash
cp .env.example .env
```

Fill in real SMTP values in `.env`, then run: `python3 fetch-postings.py`
Expected: no warning on stderr; a summary email arrives at `NOTIFY_TO`; re-running
`cat postings.local.yaml` shows `notified: true` on those entries.

- [ ] **Step 5: Verify a second run finds nothing new**

Run: `python3 fetch-postings.py`
Expected: exit code 0, no email sent (same postings already known), `postings.local.yaml`
unchanged aside from any genuinely new postings that appeared since Step 4.

- [ ] **Step 6: Confirm nothing personal leaked into git**

Run: `git status`
Expected: `companies.local.yaml`, `postings.local.yaml`, and `.env` do **not** appear as
trackable/staged files (all three should be silently ignored per `.gitignore`).
