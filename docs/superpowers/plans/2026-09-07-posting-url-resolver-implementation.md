# Posting URL Resolver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve an arbitrary job-posting URL into the posting dict the pipeline already speaks, store it, and let the existing scorer score it.

**Architecture:** A URL router tries five per-ATS adapters that call public JSON endpoints; failing that, the page is fetched once and mined for schema.org `JobPosting` markup, then for plain text. A thin skill fills in fields only when text extraction was needed, and pipes the result back into Python for persistence, so all YAML writing stays in tested code.

**Tech Stack:** Python 3 standard library (`urllib`, `json`, `re`, `html.parser`), PyYAML, pytest. No new third-party dependencies.

## Global Constraints

- **Python 3.9 compatible.** The launchd jobs may run under `/usr/bin/python3`, which is 3.9.6 on this machine. Every module starts with `from __future__ import annotations`; no `match` statements; no `X | Y` unions outside annotations.
- **No new dependencies.** `requirements.txt` stays `PyYAML>=6.0` and `pytest>=7.0`.
- **stdout is machine-readable JSON only.** Every human-readable message goes to stderr. This is what makes the CLI callable from a future orchestration node.
- **No network access in tests.** All HTTP is monkeypatched; fixtures live in `tests/fixtures/`.
- **Exit codes are contract:** `0` resolved (including already-tracked), `2` bad URL/usage/incomplete posting, `3` needs_browser, `4` fetch failed, `5` adapter failed and generic failed.
- **Never use `hiringOrganization.name` as the Workday company.** It is the legal hiring entity. Use the tenant subdomain.
- **Reference spec:** `docs/superpowers/specs/2026-09-07-posting-url-resolver-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `job_fetcher/htmltext.py` | **New.** HTML→text helpers moved out of `ats.py` |
| `job_fetcher/fetching.py` | **New.** Resolver exception hierarchy and `http_get` with retry |
| `job_fetcher/adapters.py` | **New.** The five per-ATS adapters and the router |
| `job_fetcher/resolve.py` | **New.** JSON-LD tier, generic-HTML tier, `resolve()` orchestration |
| `resolve-posting.py` | **New.** CLI: resolve mode and store mode |
| `job_fetcher/ats.py` | Modify: import HTML helpers from `htmltext` instead of defining them |
| `job_fetcher/store.py` | Modify: `merge_new_postings` gains an optional `notified` parameter |
| `plugins/cvapplicate/skills/cv-resolve-posting/SKILL.md` | **New.** The skill |
| `tests/test_htmltext.py`, `tests/test_fetching.py`, `tests/test_adapters.py`, `tests/test_resolve.py`, `tests/test_resolve_cli.py` | **New.** Tests |

The module is named `htmltext.py`, **not** `html.py`, deliberately: `job_fetcher/html.py` would sit confusingly beside its own `from html.parser import HTMLParser` import. Absolute imports would resolve correctly, but the name is a foot-gun.

`fetching.py` exists separately from `resolve.py` so that `adapters.py` can use `http_get` without `resolve.py` and `adapters.py` importing each other.

---

### Task 1: Development environment

No test cycle — this task exists because no Python on this machine currently has the dependencies installed, so every later task's test command would fail.

**Files:**
- Create: `.gitignore` entry for the virtualenv (verify it is not already covered)

- [ ] **Step 1: Create a virtualenv and install dependencies**

```bash
python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
```

- [ ] **Step 2: Confirm the existing suite passes before changing anything**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass. Record the count — later tasks must not reduce it.

- [ ] **Step 3: Make sure the virtualenv is gitignored**

```bash
grep -q '^\.venv' .gitignore || echo '.venv/' >> .gitignore
```

- [ ] **Step 4: Commit if `.gitignore` changed**

```bash
git add .gitignore
git commit -m "Ignore the local virtualenv" || echo "nothing to commit"
```

**Every later task uses `.venv/bin/python -m pytest`.**

---

### Task 2: Extract the HTML helpers into `job_fetcher/htmltext.py`

Pure refactor. `ats.py` currently owns `_strip_html`, `_description_from_html`, `_description_from_plain`, `_HTMLTextExtractor`, `_BLOCK_TAGS`, and `MAX_DESCRIPTION_LENGTH`. The resolver needs all of them, and duplicating them would let the two copies drift.

**Files:**
- Create: `job_fetcher/htmltext.py`
- Create: `tests/test_htmltext.py`
- Modify: `job_fetcher/ats.py` (delete the moved definitions, import them instead)
- Modify: `tests/test_ats.py` (move the one helper test out)

**Interfaces:**
- Consumes: nothing.
- Produces: `strip_html(html_text: str) -> str`, `description_from_html(html_text: str | None) -> str | None`, `description_from_plain(plain_text: str | None) -> str | None`, `MAX_DESCRIPTION_LENGTH: int`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_htmltext.py`:

```python
from __future__ import annotations

from job_fetcher import htmltext


def test_strip_html_removes_tags_and_collapses_whitespace():
    html = "<p>Hello</p>\n\n<ul><li>One</li><li>Two</li></ul>"

    result = htmltext.strip_html(html)

    assert result == "Hello One Two"


def test_description_from_html_returns_none_for_empty_input():
    assert htmltext.description_from_html(None) is None
    assert htmltext.description_from_html("") is None
    assert htmltext.description_from_html("<p> </p>") is None


def test_description_from_html_truncates_to_max_length():
    html = "<p>" + ("word " * 4000) + "</p>"

    result = htmltext.description_from_html(html)

    assert len(result) == htmltext.MAX_DESCRIPTION_LENGTH


def test_description_from_plain_collapses_whitespace():
    assert htmltext.description_from_plain("a\n\n  b\tc") == "a b c"


def test_description_from_plain_returns_none_for_blank():
    assert htmltext.description_from_plain("   \n ") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_htmltext.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'job_fetcher.htmltext'`

- [ ] **Step 3: Create the module**

Create `job_fetcher/htmltext.py`:

```python
from __future__ import annotations

from html.parser import HTMLParser

MAX_DESCRIPTION_LENGTH = 6000

_BLOCK_TAGS = {
    "p", "li", "ul", "ol", "div", "br", "tr", "td",
    "h1", "h2", "h3", "h4", "h5", "h6",
}


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


def strip_html(html_text: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html_text)
    return parser.text()


def description_from_html(html_text: str | None) -> str | None:
    if not html_text:
        return None
    stripped = strip_html(html_text)
    if not stripped:
        return None
    return stripped[:MAX_DESCRIPTION_LENGTH]


def description_from_plain(plain_text: str | None) -> str | None:
    if not plain_text:
        return None
    collapsed = " ".join(plain_text.split())
    if not collapsed:
        return None
    return collapsed[:MAX_DESCRIPTION_LENGTH]
```

- [ ] **Step 4: Run the new test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_htmltext.py -q`
Expected: 5 passed

- [ ] **Step 5: Rewrite `ats.py` to import instead of define**

In `job_fetcher/ats.py`, delete `_BLOCK_TAGS`, `_HTMLTextExtractor`, `_strip_html`, `MAX_DESCRIPTION_LENGTH`, `_description_from_html`, and `_description_from_plain`, and delete the now-unused `from html.parser import HTMLParser` import. Replace the import block at the top so it reads:

```python
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone

from job_fetcher.htmltext import description_from_html, description_from_plain
```

Then update the three call sites inside `normalize_greenhouse` and `normalize_lever`, renaming `_description_from_html` to `description_from_html` and `_description_from_plain` to `description_from_plain`. There are exactly three: one in `normalize_greenhouse`, two in `normalize_lever`.

- [ ] **Step 6: Move the stale helper test out of `test_ats.py`**

`tests/test_ats.py` has `test_strip_html_removes_tags_and_collapses_whitespace`, which calls `ats._strip_html`. That function no longer exists and the identical test now lives in `tests/test_htmltext.py`. Delete the test function from `tests/test_ats.py`.

- [ ] **Step 7: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass, total count unchanged from Task 1 Step 2 (one test moved, four added)

- [ ] **Step 8: Commit**

```bash
git add job_fetcher/htmltext.py job_fetcher/ats.py tests/test_htmltext.py tests/test_ats.py
git commit -m "Extract HTML text helpers into job_fetcher.htmltext"
```

---

### Task 3: The fetch layer — errors and `http_get`

**Files:**
- Create: `job_fetcher/fetching.py`
- Create: `tests/test_fetching.py`

**Interfaces:**
- Consumes: `USER_AGENT` from `job_fetcher.ats`.
- Produces: `ResolveError` (with `exit_code`), `UsageError`, `NeedsBrowser`, `FetchError`, `UnresolvableError`, `AdapterParseError`, and `http_get(url: str, accept: str = "application/json") -> str`.

`AdapterParseError` is deliberately **not** a `ResolveError`: it is caught and turned into degradation, never surfaced as an exit code.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fetching.py`:

```python
from __future__ import annotations

import urllib.error

import pytest

from job_fetcher import fetching


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_exit_codes_are_stable():
    assert fetching.UsageError("x").exit_code == 2
    assert fetching.NeedsBrowser("x").exit_code == 3
    assert fetching.FetchError("x").exit_code == 4
    assert fetching.UnresolvableError("x").exit_code == 5


def test_adapter_parse_error_is_not_a_resolve_error():
    assert not issubclass(fetching.AdapterParseError, fetching.ResolveError)


def test_http_get_returns_decoded_body(monkeypatch):
    monkeypatch.setattr(
        fetching.urllib.request, "urlopen",
        lambda request, timeout=None: _FakeResponse(b'{"ok": true}'),
    )

    assert fetching.http_get("https://example.com/x") == '{"ok": true}'


def test_http_get_raises_stale_message_on_404(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError("https://example.com/x", 404, "Not Found", {}, None)

    monkeypatch.setattr(fetching.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(fetching.FetchError) as excinfo:
        fetching.http_get("https://example.com/x")

    assert "no longer available" in str(excinfo.value)


def test_http_get_does_not_retry_on_404(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(1)
        raise urllib.error.HTTPError("https://example.com/x", 404, "Not Found", {}, None)

    monkeypatch.setattr(fetching.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(fetching.time, "sleep", lambda seconds: None)

    with pytest.raises(fetching.FetchError):
        fetching.http_get("https://example.com/x")

    assert len(calls) == 1


def test_http_get_retries_once_on_500_then_succeeds(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError("https://example.com/x", 500, "Boom", {}, None)
        return _FakeResponse(b"second try")

    monkeypatch.setattr(fetching.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(fetching.time, "sleep", lambda seconds: None)

    assert fetching.http_get("https://example.com/x") == "second try"
    assert len(calls) == 2


def test_http_get_gives_up_after_second_failure(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("dns is down")

    monkeypatch.setattr(fetching.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(fetching.time, "sleep", lambda seconds: None)

    with pytest.raises(fetching.FetchError):
        fetching.http_get("https://example.com/x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_fetching.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'job_fetcher.fetching'`

- [ ] **Step 3: Write the implementation**

Create `job_fetcher/fetching.py`:

```python
from __future__ import annotations

import time
import urllib.error
import urllib.request

from job_fetcher.ats import USER_AGENT

TIMEOUT_SECONDS = 10
RETRY_BACKOFF_SECONDS = 2
MAX_ATTEMPTS = 2


class ResolveError(Exception):
    """Base for failures that map onto a CLI exit code."""

    exit_code = 5


class UsageError(ResolveError):
    exit_code = 2


class NeedsBrowser(ResolveError):
    exit_code = 3


class FetchError(ResolveError):
    exit_code = 4


class UnresolvableError(ResolveError):
    exit_code = 5


class AdapterParseError(Exception):
    """An adapter matched but its response did not parse.

    Deliberately not a ResolveError: this triggers degradation to the
    generic path rather than an exit code.
    """


def http_get(url: str, accept: str = "application/json") -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept}
    )
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise FetchError(f"posting no longer available (HTTP 404): {url}")
            if error.code < 500 or attempt == MAX_ATTEMPTS:
                raise FetchError(f"HTTP {error.code} fetching {url}")
        except urllib.error.URLError as error:
            if attempt == MAX_ATTEMPTS:
                raise FetchError(f"network error fetching {url}: {error.reason}")
        except TimeoutError:
            if attempt == MAX_ATTEMPTS:
                raise FetchError(f"timed out fetching {url}")
        time.sleep(RETRY_BACKOFF_SECONDS)
    raise FetchError(f"failed to fetch {url}")
```

`urllib.error.HTTPError` subclasses `URLError`, so it must be caught first. The final `raise` is unreachable but keeps the function's return type honest.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_fetching.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add job_fetcher/fetching.py tests/test_fetching.py
git commit -m "Add the resolver fetch layer with retry and typed errors"
```

---

### Task 4: `merge_new_postings` learns about `notified`

Manually resolved postings must not appear in the digest email — you brought them, so mailing them back is noise.

**Files:**
- Modify: `job_fetcher/store.py`
- Modify: `tests/test_store.py`

**Interfaces:**
- Produces: `merge_new_postings(existing, fetched, today, notified=False) -> tuple[list[dict], list[dict]]`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_store.py`:

```python
def test_merge_new_postings_defaults_notified_to_false():
    fetched = [{"id": "acme-1", "company": "Acme", "title": "Engineer"}]

    merged, new = store.merge_new_postings([], fetched, "2026-09-07")

    assert merged[0]["notified"] is False
    assert new[0]["notified"] is False


def test_merge_new_postings_can_mark_new_entries_notified():
    fetched = [{"id": "acme-1", "company": "Acme", "title": "Engineer"}]

    merged, new = store.merge_new_postings([], fetched, "2026-09-07", notified=True)

    assert merged[0]["notified"] is True
    assert merged[0]["scored"] is False
    assert merged[0]["first_seen"] == "2026-09-07"
    assert new[0]["notified"] is True


def test_merge_new_postings_returns_no_new_entries_for_a_known_id():
    existing = [{"id": "acme-1", "company": "Acme", "notified": True, "scored": True}]
    fetched = [{"id": "acme-1", "company": "Acme", "title": "Engineer"}]

    merged, new = store.merge_new_postings(existing, fetched, "2026-09-07", notified=True)

    assert new == []
    assert merged == existing
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_store.py -q`
Expected: FAIL — `TypeError: merge_new_postings() got an unexpected keyword argument 'notified'`

- [ ] **Step 3: Add the parameter**

In `job_fetcher/store.py`, change the signature and the one assignment:

```python
def merge_new_postings(
    existing: list[dict], fetched: list[dict], today: str, notified: bool = False
) -> tuple[list[dict], list[dict]]:
    existing_ids = {p["id"] for p in existing}
    merged = list(existing)
    new_postings = []
    for posting in fetched:
        if posting["id"] in existing_ids:
            continue
        posting = dict(posting)
        posting["first_seen"] = today
        posting["notified"] = notified
        posting["scored"] = False
        merged.append(posting)
        new_postings.append(posting)
        existing_ids.add(posting["id"])
    return merged, new_postings
```

The default keeps `fetch-postings.py` and its existing tests working untouched.

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add job_fetcher/store.py tests/test_store.py
git commit -m "Let merge_new_postings mark new entries as already notified"
```

---

### Task 5: The router and the Greenhouse adapter

**Files:**
- Create: `job_fetcher/adapters.py`
- Create: `tests/test_adapters.py`
- Create: `tests/fixtures/greenhouse_job.json`

**Interfaces:**
- Consumes: `http_get`, `AdapterParseError` from `job_fetcher.fetching`; `normalize_greenhouse` from `job_fetcher.ats`.
- Produces: `Adapter` base class with `name`, `matches(url)`, `fetch(url)`; `ADAPTERS: list`; `find_adapter(url) -> Adapter | None`; `GreenhouseAdapter`.

Every adapter's `fetch` returns the standard posting dict plus `"resolution": "api"`, or raises `AdapterParseError`.

- [ ] **Step 1: Create the fixture**

Create `tests/fixtures/greenhouse_job.json` — the real single-job response shape, trimmed to the fields the adapter reads:

```json
{
  "id": 8172508,
  "title": "Abuse Investigator",
  "absolute_url": "https://stripe.com/jobs/search?gh_jid=8172508",
  "company_name": "Stripe",
  "location": {"name": "Dublin"},
  "updated_at": "2026-09-04T14:12:20-04:00",
  "content": "<p>Investigate abuse. Python and SQL required.</p>"
}
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_adapters.py`:

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_adapters.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'job_fetcher.adapters'`

- [ ] **Step 4: Write the implementation**

Create `job_fetcher/adapters.py`:

```python
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
```

Reusing `normalize_greenhouse` means the required-field validation and the `{slug}-{id}` id convention are shared with the nightly fetch by construction, not by duplication.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_adapters.py -q`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add job_fetcher/adapters.py tests/test_adapters.py tests/fixtures/greenhouse_job.json
git commit -m "Add the adapter router and the Greenhouse adapter"
```

---

### Task 6: The Lever adapter

**Files:**
- Modify: `job_fetcher/adapters.py`
- Modify: `tests/test_adapters.py`
- Create: `tests/fixtures/lever_job.json`

**Interfaces:**
- Consumes: `Adapter`, `_company_from_slug`, `http_get`, `AdapterParseError`; `normalize_lever` from `job_fetcher.ats`.
- Produces: `LeverAdapter`, registered in `ADAPTERS`.

- [ ] **Step 1: Create the fixture**

Create `tests/fixtures/lever_job.json` — real single-posting shape, trimmed:

```json
{
  "id": "ac978161-6f46-4f6b-ad9e-a258e642751c",
  "text": "Administrative Business Partner",
  "hostedUrl": "https://jobs.lever.co/palantir/ac978161-6f46-4f6b-ad9e-a258e642751c",
  "createdAt": 1711403416463,
  "categories": {"commitment": "Full-time", "location": "London, United Kingdom"},
  "descriptionPlain": "Support the team.  Calendar management required.",
  "description": "<p>Support the team.</p>"
}
```

- [ ] **Step 2: Write the failing test**

Append to `tests/test_adapters.py`:

```python
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
```

`posted_date` is `2024-03-25` because `normalize_lever` converts the `createdAt` epoch-milliseconds value using UTC. If this assertion fails, print the value rather than changing the expectation — a mismatch means the conversion changed.

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_adapters.py -q`
Expected: FAIL — `AttributeError: module 'job_fetcher.adapters' has no attribute 'LeverAdapter'`

- [ ] **Step 4: Write the implementation**

In `job_fetcher/adapters.py`, change the `ats` import to `from job_fetcher.ats import normalize_greenhouse, normalize_lever`, then add before `ADAPTERS`:

```python
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
        try:
            raw = json.loads(http_get(endpoint))
        except ValueError as error:
            raise AdapterParseError(f"Lever response was not JSON: {error}")
        if not isinstance(raw, dict):
            raise AdapterParseError("Lever returned a board, not a single posting")

        postings = normalize_lever(_company_from_slug(slug), slug, [raw])
        if not postings:
            raise AdapterParseError("Lever response missing required fields")
        posting = postings[0]
        posting["resolution"] = "api"
        return posting
```

The `isinstance` guard is real defence: requesting `/v0/postings/{slug}/` with an empty id returns the whole board as a list, and `normalize_lever` would then silently return the first job on the board.

Update the registry:

```python
ADAPTERS = [GreenhouseAdapter(), LeverAdapter()]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_adapters.py -q`
Expected: 10 passed

- [ ] **Step 6: Commit**

```bash
git add job_fetcher/adapters.py tests/test_adapters.py tests/fixtures/lever_job.json
git commit -m "Add the Lever adapter"
```

---

### Task 7: The Workday adapter

The most involved adapter: the endpoint is undocumented, the URL carries an optional locale segment, and two fields are traps.

**Files:**
- Modify: `job_fetcher/adapters.py`
- Modify: `tests/test_adapters.py`
- Create: `tests/fixtures/workday_job.json`

**Interfaces:**
- Consumes: `Adapter`, `_company_from_slug`, `http_get`, `AdapterParseError`; `description_from_html` from `job_fetcher.htmltext`.
- Produces: `WorkdayAdapter`, registered in `ADAPTERS`.

- [ ] **Step 1: Create the fixture**

Create `tests/fixtures/workday_job.json` — the verified response shape, trimmed. `hiringOrganization` is kept in the fixture **on purpose**, so the test can prove the adapter ignores it:

```json
{
  "jobPostingInfo": {
    "id": "e7bc26f57e641000ef95d8ab0be10000",
    "title": "Senior Software Engineer, NVLINK",
    "jobDescription": "<p>Work on NVLINK. C++ and CUDA required.</p>",
    "location": "Israel, Yokneam",
    "additionalLocations": ["Israel, Tel Aviv"],
    "postedOn": "Posted Today",
    "startDate": "2026-09-07",
    "timeType": "Full time",
    "jobReqId": "JR2004601",
    "externalUrl": "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/Israel-Yokneam/Senior-Software-Engineer--NVLINK_JR2004601"
  },
  "hiringOrganization": {"name": "IL00 Mellanox Technologies, Ltd.", "url": ""},
  "userAuthenticated": false
}
```

- [ ] **Step 2: Write the failing test**

Append to `tests/test_adapters.py`:

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_adapters.py -q`
Expected: FAIL — `AttributeError: module 'job_fetcher.adapters' has no attribute 'WorkdayAdapter'`

- [ ] **Step 4: Write the implementation**

In `job_fetcher/adapters.py`, add `from job_fetcher.htmltext import description_from_html` to the imports, then add before `ADAPTERS`:

```python
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
        try:
            raw = json.loads(http_get(endpoint))
        except ValueError as error:
            raise AdapterParseError(f"Workday response was not JSON: {error}")

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
```

Two constraints are encoded here rather than commented: `company` comes from `tenant`, never `hiringOrganization`; `posted_date` comes from `startDate`, never `postedOn`.

Update the registry:

```python
ADAPTERS = [GreenhouseAdapter(), LeverAdapter(), WorkdayAdapter()]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_adapters.py -q`
Expected: 18 passed

- [ ] **Step 6: Commit**

```bash
git add job_fetcher/adapters.py tests/test_adapters.py tests/fixtures/workday_job.json
git commit -m "Add the Workday adapter"
```

---

### Task 8: The Ashby adapter

Ashby has no single-posting endpoint — the board endpoint returns every job, and the adapter selects by the UUID in the URL.

**Files:**
- Modify: `job_fetcher/adapters.py`
- Modify: `tests/test_adapters.py`
- Create: `tests/fixtures/ashby_board.json`

**Interfaces:**
- Consumes: `Adapter`, `_company_from_slug`, `http_get`, `AdapterParseError`; `description_from_html`, `description_from_plain` from `job_fetcher.htmltext`.
- Produces: `AshbyAdapter`, registered in `ADAPTERS`.

- [ ] **Step 1: Create the fixture**

Create `tests/fixtures/ashby_board.json` — two jobs, so the selection logic is actually exercised:

```json
{
  "apiVersion": "1",
  "jobs": [
    {
      "id": "11111111-1111-1111-1111-111111111111",
      "title": "Decoy Job",
      "location": "Nowhere",
      "publishedAt": "2026-01-01T00:00:00.000+00:00",
      "jobUrl": "https://jobs.ashbyhq.com/openai/11111111-1111-1111-1111-111111111111",
      "descriptionPlain": "Should not be selected.",
      "descriptionHtml": "<p>Should not be selected.</p>"
    },
    {
      "id": "8fb1615c-34bf-47c4-a1d1-b7b2f836bbd3",
      "title": "Technical Program Manager, Compute Infrastructure",
      "location": "San Francisco",
      "publishedAt": "2026-03-12T16:38:15.322+00:00",
      "jobUrl": "https://jobs.ashbyhq.com/openai/8fb1615c-34bf-47c4-a1d1-b7b2f836bbd3",
      "descriptionPlain": "ABOUT THE TEAM\n\nThe compute infrastructure team runs the GPU fleet.",
      "descriptionHtml": "<h3>About the Team</h3><p>The compute infrastructure team runs the GPU fleet.</p>"
    }
  ]
}
```

- [ ] **Step 2: Write the failing test**

Append to `tests/test_adapters.py`:

```python
ASHBY_URL = "https://jobs.ashbyhq.com/openai/8fb1615c-34bf-47c4-a1d1-b7b2f836bbd3"


def test_find_adapter_matches_ashby_posting_urls():
    adapter = adapters.find_adapter(ASHBY_URL)
    assert adapter is not None
    assert adapter.name == "ashby"


def test_ashby_adapter_selects_the_job_named_in_the_url(monkeypatch):
    body = (FIXTURES / "ashby_board.json").read_text()
    _stub_http_get(
        monkeypatch,
        body,
        expected_url="https://api.ashbyhq.com/posting-api/job-board/openai",
    )

    posting = adapters.AshbyAdapter().fetch(ASHBY_URL)

    assert posting == {
        "id": "ashby-openai-8fb1615c-34bf-47c4-a1d1-b7b2f836bbd3",
        "company": "Openai",
        "title": "Technical Program Manager, Compute Infrastructure",
        "url": ASHBY_URL,
        "location": "San Francisco",
        "posted_date": "2026-03-12",
        "description": (
            "ABOUT THE TEAM The compute infrastructure team runs the GPU fleet."
        ),
        "resolution": "api",
    }


def test_ashby_adapter_raises_when_the_uuid_is_not_on_the_board(monkeypatch):
    body = (FIXTURES / "ashby_board.json").read_text()
    _stub_http_get(monkeypatch, body)

    with pytest.raises(AdapterParseError):
        adapters.AshbyAdapter().fetch(
            "https://jobs.ashbyhq.com/openai/99999999-9999-9999-9999-999999999999"
        )
```

`company` is `"Openai"` because it comes from title-casing the org slug. That is ugly but honest, and it is the field the skill can correct; inventing a prettier mapping would mean maintaining a slug-to-name table.

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_adapters.py -q`
Expected: FAIL — `AttributeError: module 'job_fetcher.adapters' has no attribute 'AshbyAdapter'`

- [ ] **Step 4: Write the implementation**

In `job_fetcher/adapters.py`, extend the `htmltext` import to `from job_fetcher.htmltext import description_from_html, description_from_plain`, then add before `ADAPTERS`:

```python
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
        try:
            raw = json.loads(http_get(endpoint))
        except ValueError as error:
            raise AdapterParseError(f"Ashby response was not JSON: {error}")

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
```

Update the registry:

```python
ADAPTERS = [
    GreenhouseAdapter(),
    LeverAdapter(),
    WorkdayAdapter(),
    AshbyAdapter(),
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_adapters.py -q`
Expected: 21 passed

- [ ] **Step 6: Commit**

```bash
git add job_fetcher/adapters.py tests/test_adapters.py tests/fixtures/ashby_board.json
git commit -m "Add the Ashby adapter"
```

---

### Task 9: The SmartRecruiters adapter

SmartRecruiters splits the JD across `jobAd.sections`. `companyDescription` is boilerplate about the employer, not the role, so it is deliberately excluded — including it would dilute keyword scoring with marketing copy.

**Files:**
- Modify: `job_fetcher/adapters.py`
- Modify: `tests/test_adapters.py`
- Create: `tests/fixtures/smartrecruiters_job.json`

**Interfaces:**
- Consumes: `Adapter`, `http_get`, `AdapterParseError`, `description_from_html`.
- Produces: `SmartRecruitersAdapter`, registered in `ADAPTERS`.

- [ ] **Step 1: Create the fixture**

Create `tests/fixtures/smartrecruiters_job.json`:

```json
{
  "id": "744000147914329",
  "name": "Senior Engineer - Production Planning",
  "refNumber": "REF295348M",
  "company": {"name": "Bosch Group", "identifier": "BoschGroup"},
  "location": {
    "city": "Jaipur",
    "region": "Rajasthan",
    "country": "in",
    "fullLocation": "Jaipur, Rajasthan, India"
  },
  "releasedDate": "2026-09-07T11:39:37.651Z",
  "postingUrl": "https://jobs.smartrecruiters.com/BoschGroup/744000147914329-senior-engineer",
  "jobAd": {
    "sections": {
      "companyDescription": {
        "title": "Company Description",
        "text": "<p>MARKETING BOILERPLATE about Bosch.</p>"
      },
      "jobDescription": {
        "title": "Job Description",
        "text": "<p>Ensure timely production fulfilment.</p>"
      },
      "qualifications": {
        "title": "Qualifications",
        "text": "<p>Bachelors degree in engineering.</p>"
      },
      "additionalInformation": {
        "title": "Additional Information",
        "text": "<p>Shift work possible.</p>"
      }
    }
  }
}
```

- [ ] **Step 2: Write the failing test**

Append to `tests/test_adapters.py`:

```python
SMARTRECRUITERS_URL = (
    "https://jobs.smartrecruiters.com/BoschGroup/744000147914329-senior-engineer"
)


def test_find_adapter_matches_smartrecruiters_posting_urls():
    adapter = adapters.find_adapter(SMARTRECRUITERS_URL)
    assert adapter is not None
    assert adapter.name == "smartrecruiters"


def test_smartrecruiters_adapter_produces_the_expected_posting(monkeypatch):
    body = (FIXTURES / "smartrecruiters_job.json").read_text()
    _stub_http_get(
        monkeypatch,
        body,
        expected_url=(
            "https://api.smartrecruiters.com/v1/companies/BoschGroup"
            "/postings/744000147914329"
        ),
    )

    posting = adapters.SmartRecruitersAdapter().fetch(SMARTRECRUITERS_URL)

    assert posting == {
        "id": "smartrecruiters-BoschGroup-744000147914329",
        "company": "Bosch Group",
        "title": "Senior Engineer - Production Planning",
        "url": SMARTRECRUITERS_URL,
        "location": "Jaipur, Rajasthan, India",
        "posted_date": "2026-09-07",
        "description": (
            "Ensure timely production fulfilment. "
            "Bachelors degree in engineering. Shift work possible."
        ),
        "resolution": "api",
    }


def test_smartrecruiters_adapter_excludes_the_company_boilerplate(monkeypatch):
    body = (FIXTURES / "smartrecruiters_job.json").read_text()
    _stub_http_get(monkeypatch, body)

    posting = adapters.SmartRecruitersAdapter().fetch(SMARTRECRUITERS_URL)

    assert "BOILERPLATE" not in posting["description"]


def test_smartrecruiters_adapter_raises_when_the_name_is_missing(monkeypatch):
    _stub_http_get(monkeypatch, json.dumps({"id": "744000147914329"}))

    with pytest.raises(AdapterParseError):
        adapters.SmartRecruitersAdapter().fetch(SMARTRECRUITERS_URL)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_adapters.py -q`
Expected: FAIL — `AttributeError: module 'job_fetcher.adapters' has no attribute 'SmartRecruitersAdapter'`

- [ ] **Step 4: Write the implementation**

In `job_fetcher/adapters.py`, add before `ADAPTERS`:

```python
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
        try:
            raw = json.loads(http_get(endpoint))
        except ValueError as error:
            raise AdapterParseError(
                f"SmartRecruiters response was not JSON: {error}"
            )

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
```

Unlike Workday, `company.name` here is the recognisable employer (`"Bosch Group"`), so it is used directly.

Update the registry:

```python
ADAPTERS = [
    GreenhouseAdapter(),
    LeverAdapter(),
    WorkdayAdapter(),
    AshbyAdapter(),
    SmartRecruitersAdapter(),
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_adapters.py -q`
Expected: 25 passed

- [ ] **Step 6: Commit**

```bash
git add job_fetcher/adapters.py tests/test_adapters.py tests/fixtures/smartrecruiters_job.json
git commit -m "Add the SmartRecruiters adapter"
```

---

### Task 10: Tier 2 — schema.org `JobPosting` from JSON-LD

**Files:**
- Create: `job_fetcher/resolve.py`
- Create: `tests/test_resolve.py`
- Create: `tests/fixtures/jsonld_page.html`, `tests/fixtures/jsonld_graph_page.html`, `tests/fixtures/jsonld_wrong_type_page.html`, `tests/fixtures/jsonld_malformed_page.html`

**Interfaces:**
- Consumes: `description_from_html`, `MAX_DESCRIPTION_LENGTH` from `job_fetcher.htmltext`.
- Produces: `url_id(url: str) -> str`, `extract_jsonld_posting(html_text: str, url: str) -> dict | None`.

- [ ] **Step 1: Create the fixtures**

`tests/fixtures/jsonld_page.html`:

```html
<html><head><title>Careers</title>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "JobPosting",
  "title": "Backend Engineer",
  "datePosted": "2026-08-30",
  "description": "<p>Build APIs in Python.</p>",
  "hiringOrganization": {"@type": "Organization", "name": "Tiny Co"},
  "jobLocation": {
    "@type": "Place",
    "address": {"addressLocality": "Berlin", "addressRegion": "BE"}
  }
}
</script>
</head><body>page chrome</body></html>
```

`tests/fixtures/jsonld_graph_page.html` — the same posting nested in an `@graph`, alongside an unrelated node:

```html
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"WebSite","name":"Tiny Co"},
  {"@type":["JobPosting"],"title":"Backend Engineer",
   "datePosted":"2026-08-30","description":"<p>Build APIs in Python.</p>",
   "hiringOrganization":{"name":"Tiny Co"},
   "jobLocation":{"address":{"addressLocality":"Berlin","addressRegion":"BE"}}}
]}
</script>
</head><body>page chrome</body></html>
```

`tests/fixtures/jsonld_wrong_type_page.html`:

```html
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Organization","name":"Tiny Co"}
</script>
</head><body>page chrome</body></html>
```

`tests/fixtures/jsonld_malformed_page.html`:

```html
<html><head>
<script type="application/ld+json">
{"@type": "JobPosting", "title": "Broken",
</script>
</head><body>page chrome</body></html>
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_resolve.py`:

```python
from __future__ import annotations

from pathlib import Path

from job_fetcher import resolve

FIXTURES = Path(__file__).parent / "fixtures"

PAGE_URL = "https://careers.tinyco.example/jobs/backend-engineer"


def test_url_id_is_stable_and_prefixed():
    first = resolve.url_id(PAGE_URL)
    second = resolve.url_id(PAGE_URL)

    assert first == second
    assert first.startswith("url-")
    assert len(first) == len("url-") + 12


def test_url_id_differs_between_urls():
    assert resolve.url_id(PAGE_URL) != resolve.url_id(PAGE_URL + "-2")


def test_extract_jsonld_posting_reads_a_plain_jobposting():
    html_text = (FIXTURES / "jsonld_page.html").read_text()

    posting = resolve.extract_jsonld_posting(html_text, PAGE_URL)

    assert posting == {
        "id": resolve.url_id(PAGE_URL),
        "company": "Tiny Co",
        "title": "Backend Engineer",
        "url": PAGE_URL,
        "location": "Berlin, BE",
        "posted_date": "2026-08-30",
        "description": "Build APIs in Python.",
        "resolution": "jsonld",
    }


def test_extract_jsonld_posting_finds_a_posting_inside_an_at_graph():
    html_text = (FIXTURES / "jsonld_graph_page.html").read_text()

    posting = resolve.extract_jsonld_posting(html_text, PAGE_URL)

    assert posting is not None
    assert posting["title"] == "Backend Engineer"
    assert posting["resolution"] == "jsonld"


def test_extract_jsonld_posting_ignores_a_non_jobposting_type():
    html_text = (FIXTURES / "jsonld_wrong_type_page.html").read_text()

    assert resolve.extract_jsonld_posting(html_text, PAGE_URL) is None


def test_extract_jsonld_posting_survives_malformed_json():
    html_text = (FIXTURES / "jsonld_malformed_page.html").read_text()

    assert resolve.extract_jsonld_posting(html_text, PAGE_URL) is None


def test_extract_jsonld_posting_returns_none_when_there_is_no_markup():
    assert resolve.extract_jsonld_posting("<html><body>hi</body></html>", PAGE_URL) is None


def test_extract_jsonld_posting_requires_both_title_and_company():
    html_text = (
        '<script type="application/ld+json">'
        '{"@type":"JobPosting","title":"No Company"}'
        "</script>"
    )

    assert resolve.extract_jsonld_posting(html_text, PAGE_URL) is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_resolve.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'job_fetcher.resolve'`

- [ ] **Step 4: Write the implementation**

Create `job_fetcher/resolve.py`:

```python
from __future__ import annotations

import hashlib
import json
import re

from job_fetcher.htmltext import description_from_html

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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_resolve.py -q`
Expected: 8 passed

- [ ] **Step 6: Commit**

```bash
git add job_fetcher/resolve.py tests/test_resolve.py tests/fixtures/jsonld_*.html
git commit -m "Add JSON-LD JobPosting extraction as the second resolver tier"
```

---

### Task 11: Tier 3 — generic HTML, hints, and `needs_browser`

**Files:**
- Modify: `job_fetcher/resolve.py`
- Modify: `tests/test_resolve.py`
- Create: `tests/fixtures/plain_page.html`, `tests/fixtures/js_shell_page.html`

**Interfaces:**
- Consumes: `strip_html`, `MAX_DESCRIPTION_LENGTH`; `NeedsBrowser` from `job_fetcher.fetching`.
- Produces: `RAW_TEXT_MAX_LENGTH`, `JS_SHELL_TEXT_THRESHOLD`, `extract_hints(html_text, url) -> dict`, `resolve_generic(html_text, url) -> dict`.

- [ ] **Step 1: Create the fixtures**

`tests/fixtures/plain_page.html` — long enough to clear the JS-shell threshold:

```html
<html><head>
<title>Backend Engineer at Tiny Co</title>
<meta property="og:title" content="Backend Engineer">
</head><body>
<nav>Home About Careers</nav>
<h1>Backend Engineer</h1>
<p>We are looking for a backend engineer to build and operate our Python
services. You will design REST APIs, own a Postgres schema, and share an
on-call rotation. We expect solid SQL, comfort with containers, and an
interest in distributed systems. This role is based in Berlin with a hybrid
schedule. You will work with a small team that ships continuously and
reviews every change. Experience with asynchronous Python, message queues,
and infrastructure as code is welcome but not required. We offer a learning
budget, a home office allowance, and twenty-eight days of leave. Apply with
a CV; a cover letter is optional but read carefully when provided.</p>
</body></html>
```

`tests/fixtures/js_shell_page.html`:

```html
<html><head><title>Careers</title></head>
<body><div id="root"></div><script src="/app.js"></script></body></html>
```

- [ ] **Step 2: Write the failing test**

Append to `tests/test_resolve.py`:

```python
import pytest

from job_fetcher.fetching import NeedsBrowser


def test_extract_hints_reads_og_title_and_document_title():
    html_text = (FIXTURES / "plain_page.html").read_text()

    hints = resolve.extract_hints(html_text, PAGE_URL)

    assert hints["og_title"] == "Backend Engineer"
    assert hints["document_title"] == "Backend Engineer at Tiny Co"
    assert hints["domain"] == "careers.tinyco.example"


def test_extract_hints_tolerates_missing_metadata():
    hints = resolve.extract_hints("<html><body>hi</body></html>", PAGE_URL)

    assert hints["og_title"] is None
    assert hints["document_title"] is None
    assert hints["domain"] == "careers.tinyco.example"


def test_resolve_generic_leaves_fields_null_and_flags_extraction():
    html_text = (FIXTURES / "plain_page.html").read_text()

    posting = resolve.resolve_generic(html_text, PAGE_URL)

    assert posting["id"] == resolve.url_id(PAGE_URL)
    assert posting["url"] == PAGE_URL
    assert posting["company"] is None
    assert posting["title"] is None
    assert posting["location"] is None
    assert posting["posted_date"] == ""
    assert posting["resolution"] == "html"
    assert posting["needs_extraction"] is True
    assert "backend engineer" in posting["raw_text"].lower()
    assert posting["hints"]["og_title"] == "Backend Engineer"


def test_resolve_generic_caps_raw_text():
    html_text = "<p>" + ("word " * 20000) + "</p>"

    posting = resolve.resolve_generic(html_text, PAGE_URL)

    assert len(posting["raw_text"]) == resolve.RAW_TEXT_MAX_LENGTH


def test_resolve_generic_raises_needs_browser_for_a_js_shell():
    html_text = (FIXTURES / "js_shell_page.html").read_text()

    with pytest.raises(NeedsBrowser) as excinfo:
        resolve.resolve_generic(html_text, PAGE_URL)

    assert excinfo.value.exit_code == 3
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_resolve.py -q`
Expected: FAIL — `AttributeError: module 'job_fetcher.resolve' has no attribute 'extract_hints'`

- [ ] **Step 4: Write the implementation**

In `job_fetcher/resolve.py`, extend the imports:

```python
from urllib.parse import urlparse

from job_fetcher.fetching import NeedsBrowser
from job_fetcher.htmltext import MAX_DESCRIPTION_LENGTH, description_from_html, strip_html
```

Then append:

```python
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
```

`description` is populated even on Tier 3 so a posting is scoreable the moment the skill fills in the three identity fields.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_resolve.py -q`
Expected: 13 passed

- [ ] **Step 6: Commit**

```bash
git add job_fetcher/resolve.py tests/test_resolve.py tests/fixtures/plain_page.html tests/fixtures/js_shell_page.html
git commit -m "Add generic HTML extraction and needs_browser detection"
```

---

### Task 12: `resolve()` orchestration and degradation

**Files:**
- Modify: `job_fetcher/resolve.py`
- Modify: `tests/test_resolve.py`

**Interfaces:**
- Consumes: `find_adapter` from `job_fetcher.adapters`; `http_get`, `AdapterParseError`, `UsageError`, `NeedsBrowser`, `UnresolvableError` from `job_fetcher.fetching`.
- Produces: `resolve(url: str) -> dict`.

Degradation rule: only `AdapterParseError` degrades. A `FetchError` from an adapter — a 404 on a filled job — propagates, because retrying the same dead posting against the generic path would waste a request and report a confusing failure.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_resolve.py`:

```python
from job_fetcher.fetching import AdapterParseError, FetchError, UnresolvableError, UsageError


class _StubAdapter:
    name = "stub"

    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    def matches(self, url):
        return True

    def fetch(self, url):
        if self._error is not None:
            raise self._error
        return self._result


def test_resolve_rejects_a_non_http_url():
    with pytest.raises(UsageError) as excinfo:
        resolve.resolve("ftp://example.com/job")

    assert excinfo.value.exit_code == 2


def test_resolve_returns_the_adapter_result_when_one_matches(monkeypatch):
    expected = {"id": "x-1", "title": "T", "resolution": "api"}
    monkeypatch.setattr(resolve, "find_adapter", lambda url: _StubAdapter(expected))

    assert resolve.resolve(PAGE_URL) == expected


def test_resolve_does_not_fetch_the_page_when_an_adapter_succeeds(monkeypatch):
    monkeypatch.setattr(
        resolve, "find_adapter", lambda url: _StubAdapter({"id": "x", "resolution": "api"})
    )

    def fail(*args, **kwargs):
        raise AssertionError("http_get should not be called")

    monkeypatch.setattr(resolve, "http_get", fail)

    resolve.resolve(PAGE_URL)


def test_resolve_propagates_a_fetch_error_from_an_adapter(monkeypatch):
    monkeypatch.setattr(
        resolve,
        "find_adapter",
        lambda url: _StubAdapter(error=FetchError("posting no longer available")),
    )

    with pytest.raises(FetchError) as excinfo:
        resolve.resolve(PAGE_URL)

    assert excinfo.value.exit_code == 4


def test_resolve_degrades_to_jsonld_when_an_adapter_cannot_parse(monkeypatch, capsys):
    monkeypatch.setattr(
        resolve,
        "find_adapter",
        lambda url: _StubAdapter(error=AdapterParseError("shape changed")),
    )
    monkeypatch.setattr(
        resolve,
        "http_get",
        lambda url, accept="application/json": (FIXTURES / "jsonld_page.html").read_text(),
    )

    posting = resolve.resolve(PAGE_URL)

    assert posting["resolution"] == "jsonld"
    assert "shape changed" in capsys.readouterr().err


def test_resolve_falls_through_to_generic_when_there_is_no_adapter(monkeypatch):
    monkeypatch.setattr(resolve, "find_adapter", lambda url: None)
    monkeypatch.setattr(
        resolve,
        "http_get",
        lambda url, accept="application/json": (FIXTURES / "plain_page.html").read_text(),
    )

    posting = resolve.resolve(PAGE_URL)

    assert posting["resolution"] == "html"


def test_resolve_reports_needs_browser_when_no_adapter_matched(monkeypatch):
    monkeypatch.setattr(resolve, "find_adapter", lambda url: None)
    monkeypatch.setattr(
        resolve,
        "http_get",
        lambda url, accept="application/json": (FIXTURES / "js_shell_page.html").read_text(),
    )

    with pytest.raises(NeedsBrowser) as excinfo:
        resolve.resolve(PAGE_URL)

    assert excinfo.value.exit_code == 3


def test_resolve_reports_unresolvable_when_the_adapter_failed_too(monkeypatch):
    monkeypatch.setattr(
        resolve,
        "find_adapter",
        lambda url: _StubAdapter(error=AdapterParseError("shape changed")),
    )
    monkeypatch.setattr(
        resolve,
        "http_get",
        lambda url, accept="application/json": (FIXTURES / "js_shell_page.html").read_text(),
    )

    with pytest.raises(UnresolvableError) as excinfo:
        resolve.resolve(PAGE_URL)

    assert excinfo.value.exit_code == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_resolve.py -q`
Expected: FAIL — `AttributeError: module 'job_fetcher.resolve' has no attribute 'resolve'`

- [ ] **Step 3: Write the implementation**

In `job_fetcher/resolve.py`, add `import sys` to the stdlib imports, then
**replace** the `from job_fetcher.fetching import NeedsBrowser` line added in
Task 11 with these two — do not append, or the module ends up importing from
`fetching` twice:

```python
from job_fetcher.adapters import find_adapter
from job_fetcher.fetching import (
    AdapterParseError,
    NeedsBrowser,
    UnresolvableError,
    UsageError,
    http_get,
)
```

The module now imports `find_adapter` and `http_get` into its own namespace, which is what lets the tests monkeypatch `resolve.find_adapter` and `resolve.http_get`.

Append:

```python
def resolve(url: str) -> dict:
    if not url.startswith(("http://", "https://")):
        raise UsageError(f"not an http(s) URL: {url}")

    adapter_failed = False
    adapter = find_adapter(url)
    if adapter is not None:
        try:
            return adapter.fetch(url)
        except AdapterParseError as error:
            adapter_failed = True
            print(
                f"warning: {adapter.name} adapter failed ({error}); "
                "falling back to generic extraction",
                file=sys.stderr,
            )

    html_text = http_get(url, accept="text/html")

    posting = extract_jsonld_posting(html_text, url)
    if posting is not None:
        return posting

    try:
        return resolve_generic(html_text, url)
    except NeedsBrowser:
        if adapter_failed:
            raise UnresolvableError(
                f"{adapter.name} adapter failed and the page needs a browser: {url}"
            )
        raise
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_resolve.py -q`
Expected: 21 passed

- [ ] **Step 5: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add job_fetcher/resolve.py tests/test_resolve.py
git commit -m "Add resolve() orchestration with adapter-to-generic degradation"
```

---

### Task 13: The CLI — resolve mode

**Files:**
- Create: `resolve-posting.py`
- Create: `tests/test_resolve_cli.py`

**Interfaces:**
- Consumes: `resolve` from `job_fetcher.resolve`; `ResolveError` from `job_fetcher.fetching`.
- Produces: `main(argv: list[str]) -> int`, importable as `resolve_posting` via `importlib`.

The filename has a hyphen, matching `fetch-postings.py`, so it is not importable by name. The test loads it through `importlib.util.spec_from_file_location`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_resolve_cli.py`:

```python
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from job_fetcher.fetching import FetchError, NeedsBrowser, UnresolvableError

REPO_ROOT = Path(__file__).parent.parent


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "resolve_posting", REPO_ROOT / "resolve-posting.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = _load_cli()

POSTING = {
    "id": "stripe-8172508",
    "company": "Stripe",
    "title": "Abuse Investigator",
    "url": "https://job-boards.greenhouse.io/stripe/jobs/8172508",
    "location": "Dublin",
    "posted_date": "2026-09-04",
    "description": "Investigate abuse.",
    "resolution": "api",
}


def test_resolve_mode_prints_json_to_stdout(monkeypatch, capsys):
    monkeypatch.setattr(cli, "resolve", lambda url: dict(POSTING))

    exit_code = cli.main(["resolve-posting.py", POSTING["url"]])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == POSTING


def test_resolve_mode_keeps_stdout_pure_json(monkeypatch, capsys):
    """A human summary on stdout would break a machine consumer."""
    monkeypatch.setattr(cli, "resolve", lambda url: dict(POSTING))

    cli.main(["resolve-posting.py", POSTING["url"]])

    captured = capsys.readouterr()
    json.loads(captured.out)
    assert "Stripe" in captured.err


@pytest.mark.parametrize(
    "error,expected_code",
    [
        (NeedsBrowser("js shell"), 3),
        (FetchError("posting no longer available"), 4),
        (UnresolvableError("both paths failed"), 5),
    ],
)
def test_resolve_mode_maps_errors_to_exit_codes(monkeypatch, capsys, error, expected_code):
    def raise_error(url):
        raise error

    monkeypatch.setattr(cli, "resolve", raise_error)

    exit_code = cli.main(["resolve-posting.py", POSTING["url"]])

    assert exit_code == expected_code
    assert capsys.readouterr().out == ""


def test_needs_browser_message_names_the_escape_hatch(monkeypatch, capsys):
    def raise_error(url):
        raise NeedsBrowser("js shell")

    monkeypatch.setattr(cli, "resolve", raise_error)

    cli.main(["resolve-posting.py", POSTING["url"]])

    assert "cv-review" in capsys.readouterr().err


def test_usage_error_without_arguments(capsys):
    exit_code = cli.main(["resolve-posting.py"])

    assert exit_code == 2
    assert "usage:" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_resolve_cli.py -q`
Expected: FAIL — `FileNotFoundError` on `resolve-posting.py`

- [ ] **Step 3: Write the implementation**

Create `resolve-posting.py`:

```python
#!/usr/bin/env python3
"""Resolve a job posting URL into the pipeline's posting format.

Usage:
    ./resolve-posting.py <url>
    ./resolve-posting.py --store -

Resolve mode prints one JSON object on stdout: the standard posting dict plus
a `resolution` field saying how it was obtained. Tier 3 results additionally
carry `needs_extraction`, `raw_text`, and `hints`, with company/title/location
left null for a model to fill in.

Store mode reads a completed posting dict on stdin and merges it into
postings.local.yaml with notified=True and scored=False.

Human-readable messages go to stderr; stdout is always machine-readable.

Exit codes: 0 = resolved (including already tracked), 2 = usage or incomplete
posting, 3 = needs a browser, 4 = fetch failed, 5 = unresolvable.
"""

from __future__ import annotations

import json
import sys

from job_fetcher.fetching import NeedsBrowser, ResolveError
from job_fetcher.resolve import resolve

USAGE = (
    "usage: resolve-posting.py <url>\n"
    "       resolve-posting.py --store -\n"
)


def _resolve_mode(url: str) -> int:
    try:
        posting = resolve(url)
    except NeedsBrowser as error:
        print(f"error: {error}", file=sys.stderr)
        print(
            "hint: this page needs a browser. Until that is supported, run "
            "cv-review with the job description pasted in.",
            file=sys.stderr,
        )
        return error.exit_code
    except ResolveError as error:
        print(f"error: {error}", file=sys.stderr)
        return error.exit_code

    print(json.dumps(posting))
    print(
        f"info: resolved via {posting['resolution']}: "
        f"{posting.get('company') or '?'} — {posting.get('title') or '?'}",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str]) -> int:
    arguments = argv[1:]
    if len(arguments) == 1 and not arguments[0].startswith("-"):
        return _resolve_mode(arguments[0])
    print(USAGE, file=sys.stderr, end="")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_resolve_cli.py -q`
Expected: 7 passed

- [ ] **Step 5: Make it executable and smoke-test against a live posting**

```bash
chmod +x resolve-posting.py
.venv/bin/python resolve-posting.py https://job-boards.greenhouse.io/stripe/jobs/8172508 | .venv/bin/python -m json.tool | head -20
```

Expected: a JSON object with `"resolution": "api"` and `"company": "Stripe"`. If that specific job has been filled, exit code 4 with "posting no longer available" is also a correct result — pick another id from `https://boards-api.greenhouse.io/v1/boards/stripe/jobs`.

- [ ] **Step 6: Commit**

```bash
git add resolve-posting.py tests/test_resolve_cli.py
git commit -m "Add resolve-posting.py resolve mode"
```

---

### Task 14: The CLI — store mode

**Files:**
- Modify: `resolve-posting.py`
- Modify: `tests/test_resolve_cli.py`

**Interfaces:**
- Consumes: `load_postings`, `merge_new_postings`, `save_postings` from `job_fetcher.store`.
- Produces: `POSTINGS_PATH`, `REQUIRED_FIELDS`, `store_mode(stream) -> int`.

Store mode's output is a small JSON status object, not the posting — the caller already has the posting.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_resolve_cli.py`:

```python
import io

from job_fetcher import store


def test_store_mode_writes_the_posting_as_notified(monkeypatch, tmp_path, capsys):
    path = tmp_path / "postings.local.yaml"
    monkeypatch.setattr(cli, "POSTINGS_PATH", str(path))

    exit_code = cli.store_mode(io.StringIO(json.dumps(POSTING)))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {
        "stored": True,
        "already_tracked": False,
        "id": "stripe-8172508",
        "scored": False,
    }

    stored = store.load_postings(str(path))
    assert len(stored) == 1
    assert stored[0]["notified"] is True
    assert stored[0]["scored"] is False
    assert "resolution" not in stored[0]
    assert "raw_text" not in stored[0]


def test_store_mode_reports_an_already_tracked_posting(monkeypatch, tmp_path, capsys):
    path = tmp_path / "postings.local.yaml"
    monkeypatch.setattr(cli, "POSTINGS_PATH", str(path))
    existing = dict(POSTING)
    existing.pop("resolution")
    existing.update({"first_seen": "2026-09-01", "notified": True, "scored": True})
    store.save_postings(str(path), [existing])

    exit_code = cli.store_mode(io.StringIO(json.dumps(POSTING)))

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "stored": False,
        "already_tracked": True,
        "id": "stripe-8172508",
        "scored": True,
    }
    assert len(store.load_postings(str(path))) == 1


@pytest.mark.parametrize("missing", ["company", "title", "url"])
def test_store_mode_rejects_a_posting_with_a_null_identity_field(
    monkeypatch, tmp_path, capsys, missing
):
    path = tmp_path / "postings.local.yaml"
    monkeypatch.setattr(cli, "POSTINGS_PATH", str(path))
    incomplete = dict(POSTING)
    incomplete[missing] = None

    exit_code = cli.store_mode(io.StringIO(json.dumps(incomplete)))

    assert exit_code == 2
    assert missing in capsys.readouterr().err
    assert store.load_postings(str(path)) == []


def test_store_mode_rejects_invalid_json(monkeypatch, tmp_path, capsys):
    path = tmp_path / "postings.local.yaml"
    monkeypatch.setattr(cli, "POSTINGS_PATH", str(path))

    exit_code = cli.store_mode(io.StringIO("not json"))

    assert exit_code == 2
    assert store.load_postings(str(path)) == []


def test_store_mode_is_reachable_through_main(monkeypatch, tmp_path, capsys):
    path = tmp_path / "postings.local.yaml"
    monkeypatch.setattr(cli, "POSTINGS_PATH", str(path))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(POSTING)))

    exit_code = cli.main(["resolve-posting.py", "--store", "-"])

    assert exit_code == 0
    assert len(store.load_postings(str(path))) == 1
```

The `"resolution" not in stored[0]` assertion matters: `resolution`, `needs_extraction`, `raw_text`, and `hints` are transport fields. Persisting them would put a 20,000-character `raw_text` into `postings.local.yaml` on every Tier 3 add.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_resolve_cli.py -q`
Expected: FAIL — `AttributeError: module 'resolve_posting' has no attribute 'store_mode'`

- [ ] **Step 3: Write the implementation**

In `resolve-posting.py`, extend the imports:

```python
import datetime

from job_fetcher.store import load_postings, merge_new_postings, save_postings
```

Add the constants below `USAGE`:

```python
POSTINGS_PATH = "postings.local.yaml"
REQUIRED_FIELDS = ("company", "title", "url")
TRANSPORT_FIELDS = ("resolution", "needs_extraction", "raw_text", "hints")
```

Add `store_mode` above `main`:

```python
def store_mode(stream) -> int:
    try:
        posting = json.load(stream)
    except ValueError as error:
        print(f"error: stdin was not valid JSON: {error}", file=sys.stderr)
        return 2
    if not isinstance(posting, dict):
        print("error: expected a single JSON object on stdin", file=sys.stderr)
        return 2

    missing = [field for field in REQUIRED_FIELDS if not posting.get(field)]
    if missing:
        print(
            f"error: posting is incomplete, refusing to store it: "
            f"{', '.join(missing)} must not be null",
            file=sys.stderr,
        )
        return 2
    if not posting.get("id"):
        print("error: posting is missing an id", file=sys.stderr)
        return 2

    entry = {key: value for key, value in posting.items() if key not in TRANSPORT_FIELDS}

    existing = load_postings(POSTINGS_PATH)
    today = datetime.date.today().isoformat()
    merged, new_postings = merge_new_postings(existing, [entry], today, notified=True)

    if not new_postings:
        tracked = next(item for item in merged if item["id"] == entry["id"])
        print(json.dumps({
            "stored": False,
            "already_tracked": True,
            "id": entry["id"],
            "scored": bool(tracked.get("scored")),
        }))
        print(
            f"info: already tracked as {entry['id']} "
            f"(scored: {bool(tracked.get('scored'))})",
            file=sys.stderr,
        )
        return 0

    save_postings(POSTINGS_PATH, merged)
    print(json.dumps({
        "stored": True,
        "already_tracked": False,
        "id": entry["id"],
        "scored": False,
    }))
    print(f"info: stored {entry['id']}", file=sys.stderr)
    return 0
```

Then extend `main` to route store mode, keeping the existing resolve branch:

```python
def main(argv: list[str]) -> int:
    arguments = argv[1:]
    if len(arguments) == 2 and arguments[0] == "--store" and arguments[1] == "-":
        return store_mode(sys.stdin)
    if len(arguments) == 1 and not arguments[0].startswith("-"):
        return _resolve_mode(arguments[0])
    print(USAGE, file=sys.stderr, end="")
    return 2
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_resolve_cli.py -q`
Expected: 14 passed

- [ ] **Step 5: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add resolve-posting.py tests/test_resolve_cli.py
git commit -m "Add resolve-posting.py store mode"
```

---

### Task 15: The `cv-resolve-posting` skill

**Files:**
- Create: `plugins/cvapplicate/skills/cv-resolve-posting/SKILL.md`

**Interfaces:**
- Consumes: `resolve-posting.py` in both modes; the existing `cv-score-postings` skill.
- Produces: nothing other skills depend on.

- [ ] **Step 1: Read a sibling skill to match the house style**

Run: `cat plugins/cvapplicate/skills/cv-log-outcome/SKILL.md`

Note the frontmatter shape (`name`, `description`) and the Inputs / Procedure / Error handling section pattern. Match it.

- [ ] **Step 2: Write the skill**

Create `plugins/cvapplicate/skills/cv-resolve-posting/SKILL.md`:

```markdown
---
name: cv-resolve-posting
description: Resolve a job posting URL into the tracked postings file and score it against every industry branch. Use when the user pastes a link to a job posting and wants to know how well it fits, or wants it added to the pipeline.
---

# CV Resolve Posting

Turns a job posting URL into a stored, scored posting. All fetching and all
file writing happen in `resolve-posting.py`; this skill only fills in fields
that could not be extracted mechanically.

## Inputs needed

1. **A job posting URL.** If the user pasted a job description without a URL,
   this skill does not apply — use `cv-review` instead.

## Procedure

1. Run `python3 resolve-posting.py <url>` and capture stdout and the exit code.
2. Handle the exit code:
   - **0** — continue to step 3.
   - **2** — report the message and stop; the URL was not usable.
   - **3** — tell the user the page needs a browser, which is not yet
     supported, and that they can run `cv-review` with the job description
     pasted in. Stop.
   - **4** — report the message and stop. If it says the posting is no longer
     available, say that plainly: the job was filled or pulled.
   - **5** — report that both the ATS adapter and generic extraction failed,
     quote the warning from stderr, and suggest opening an issue since it names
     the adapter that broke. Stop.
3. Parse the JSON object from stdout. If it has no `needs_extraction` field, it
   is complete — go to step 5.
4. If `needs_extraction` is true, read `raw_text` and `hints` and determine
   `company`, `title`, and `location`:
   - Prefer `hints.og_title` and `hints.document_title` for the title, but
     strip any company-name suffix (`"Backend Engineer at Tiny Co"` → `"Backend
     Engineer"`).
   - Take the company from the page text or `hints.domain`.
   - Use `"Unknown"` for `location` only if the text genuinely does not say.
   - **Do not invent a title or company.** If `raw_text` is navigation chrome
     with no job description in it, say so and stop — a posting with a guessed
     title would be scored and reported as if it were real.
5. Write the completed posting object to stdin of
   `python3 resolve-posting.py --store -`. Include every field from the resolve
   output with the nulls filled in; the script drops its own transport fields.
6. Read the JSON status object from stdout:
   - `already_tracked: true` — tell the user the posting is already tracked,
     give the `id`, and say whether it has been scored. If `scored` is true,
     read the entry from `matches.local.yaml` and report the existing score
     instead of re-scoring. Stop.
   - `stored: true` — continue.
7. Invoke the `cv-score-postings` skill. It scores every posting whose `scored`
   flag is false, which now includes this one. Do not re-implement the JD Fit
   rubric here — it must live in exactly one place.
8. Report to the user: the company, title, location, how it was resolved
   (`resolution`), the `best_branch`, the `jd_fit_score`, and the one-line
   rationale from `matches.local.yaml`.

## Error handling

- Never hand-edit `postings.local.yaml` or `matches.local.yaml`. Every write
  goes through `resolve-posting.py` or `cv-score-postings`.
- If step 4 cannot determine the company or title from the page text, stop and
  report it. Do not guess.
- If `resolve-posting.py` writes a `warning:` line to stderr, include it in the
  report even on success — it means an ATS adapter is broken and the result came
  from a lower tier.
```

- [ ] **Step 3: Record the permission scope in the skill**

Append this section to the end of `SKILL.md`. The spec calls out that this
skill needs no write permission at all, because Python owns every write — that
is worth stating where a future runner script would read it.

```markdown
## Permission scope

This skill needs no `Edit` grant. Every write goes through
`resolve-posting.py`, so an unattended runner needs only:

```
Read Bash(python3 resolve-posting.py:*)
```

Compare `score-postings.sh`, which must grant
`Edit(matches.local.yaml) Edit(postings.local.yaml)`. When deterministic code
owns persistence, the agent needs no write permission.
```

- [ ] **Step 4: Verify the frontmatter parses**

```bash
.venv/bin/python -c "
import pathlib, yaml
text = pathlib.Path('plugins/cvapplicate/skills/cv-resolve-posting/SKILL.md').read_text()
front = text.split('---')[1]
data = yaml.safe_load(front)
assert data['name'] == 'cv-resolve-posting', data
assert len(data['description']) > 40
print('frontmatter OK:', data['name'])
"
```

Expected: `frontmatter OK: cv-resolve-posting`

- [ ] **Step 5: Commit**

```bash
git add plugins/cvapplicate/skills/cv-resolve-posting/SKILL.md
git commit -m "Add the cv-resolve-posting skill"
```

---

### Task 16: Documentation

The README advertises "seven skills" in four places and lists them in a table. Adding an eighth without updating those leaves the README lying.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Find every place the skill count appears**

```bash
grep -n "seven skills\|seven\b\|Skills$\|six are validated" README.md
```

- [ ] **Step 2: Update the skills table**

In the `## Skills` table in `README.md`, add a row after the `cv-score-postings` row:

```markdown
| **cv-resolve-posting** | Resolves a pasted job posting URL into the tracked postings file and scores it against every industry branch |
```

- [ ] **Step 3: Update every "seven skills" reference to eight**

Change "packages that loop into seven skills" to "eight skills", "The seven skills below" to "The eight skills below", "This installs the seven skills once" to "eight skills", and in `## Status` change "All seven skills are implemented; six are validated end-to-end as skills." to "All eight skills are implemented; six are validated end-to-end as skills." Use the grep output from Step 1 to confirm none are missed.

- [ ] **Step 4: Add a usage section**

Add this after the `## Filling in an application's "Skills" field` section, before the `# Guardrails` heading:

```markdown
## Scoring a posting you found yourself

```
Run cv-resolve-posting for https://job-boards.greenhouse.io/example/jobs/12345
```

The nightly fetcher only sees companies listed in `companies.local.yaml`. This
takes any posting URL, pulls the job description, adds it to
`postings.local.yaml`, and scores it against every industry branch right away —
so a link someone sends you goes through the same rubric as a fetched one.

It reads the posting from the ATS's own API where it recognises one (Greenhouse,
Lever, Workday, Ashby, SmartRecruiters), from the page's schema.org markup where
present, and from the page text otherwise. Pages that render the job description
only in JavaScript are reported as needing a browser, which isn't supported yet
— paste the description into `cv-review` for those.

Pasting a link for a company already in `companies.local.yaml` is safe: it
resolves to the same id the nightly fetch produces, so it reports the existing
entry and its score rather than creating a duplicate.
```

- [ ] **Step 5: Verify no stale count remains**

```bash
grep -n "seven skills" README.md && echo "STILL STALE — fix it" || echo "clean"
```

Expected: `clean`

- [ ] **Step 6: Run the whole suite one final time**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "Document cv-resolve-posting in the README"
```

---

## Deferred to later phases

Recorded so a reviewer does not read these as gaps:

- **Tier 4 (browser resolution).** `NeedsBrowser` is raised and reported; Phase C implements it behind the same interface.
- **Taleo and iCIMS adapters.** Excluded by the spec; both fall through to the generic path.
- **Plugin distribution of the Python pipeline.** The spec's open item. `resolve-posting.py` and `job_fetcher/` stay at repo root, so a data repo created from this template needs them merged from upstream by hand.
