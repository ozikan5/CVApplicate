# Tailor Packets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Append a job posting URL to a queue and get back a submit-ready packet in `outbox/`, without touching the industry branch or claiming an application you didn't make.

**Architecture:** An eligibility gate rejects postings you cannot accept before any money is spent on them. A queue runner then chains Phase A's resolver, the existing scorer, and a new tailoring skill that works inside a throwaway git worktree. A separate interactive skill commits the CV and writes the log entry only when you actually apply.

**Tech Stack:** Python 3 standard library plus PyYAML, pytest. No new third-party dependencies.

## Global Constraints

- **Python 3.9 compatible.** `from __future__ import annotations` in every module; no `match` statements; no `X | Y` unions outside annotations. Verify with `.venv39/bin/python -m pytest` as well as `.venv/bin/python -m pytest`.
- **No new dependencies.** `requirements.txt` stays `PyYAML>=6.0` and `pytest>=7.0`.
- **No network access in tests.** Fixtures in `tests/fixtures/`.
- **The tailoring path must not be able to write git history.** `tailor-packets.sh` grants no `git add` and no `git commit`. Only `cv-log-application`, which is interactive, may commit.
- **`log.yaml` schema is unchanged.** Entries written by `cv-log-application` match the existing shape exactly.
- **The eligibility gate errs toward eligible.** Ambiguity is escalated, never guessed into a rejection.
- **Reference spec:** `docs/superpowers/specs/2026-09-08-tailor-packets-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `job_fetcher/profile.py` | **New.** Profile config loading; the deterministic authorization verdict |
| `job_fetcher/tailor.py` | **New.** Queue parsing and packet slug generation |
| `job_fetcher/store.py` | Modify: `packeted` flag and `mark_packeted` |
| `profile.example.yaml` | **New.** Template for `profile.local.yaml` |
| `tailor-packets.sh` | **New.** Queue runner |
| `launchd/com.cvapplicate.tailor-packets.plist.example` | **New.** Optional schedule |
| `plugins/cvapplicate/skills/cv-tailor-packet/SKILL.md` | **New.** Tailoring + packet writing |
| `plugins/cvapplicate/skills/cv-log-application/SKILL.md` | **New.** Apply-time commit and log |
| `plugins/cvapplicate/skills/cv-score-postings/SKILL.md` | Modify: apply the eligibility gate |
| `.gitignore` | Modify: `profile.local.yaml`, `queue.local.txt`, `outbox/` |
| `tests/test_profile.py`, `tests/test_tailor.py` | **New.** |

`profile.py` and `tailor.py` are separate because the gate is consumed by the scorer while the queue and slug logic is consumed only by the tailoring runner; keeping them apart stops the scorer from importing queue code it never uses.

---

### Task 1: Profile config loading

**Files:**
- Create: `job_fetcher/profile.py`, `profile.example.yaml`, `tests/test_profile.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `ProfileError`, `load_profile(path: str) -> dict`, `VALID_SEEKING`, `VALID_AUTHORIZATION`

- [ ] **Step 1: Write the failing test**

Create `tests/test_profile.py`:

```python
from __future__ import annotations

import pytest

from job_fetcher import profile


def _write(tmp_path, text):
    path = tmp_path / "profile.local.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_load_profile_reads_a_full_profile(tmp_path):
    path = _write(tmp_path, """
seeking: internship
graduation: 2028-06
locations: ["United States", "Remote (US)"]
max_years_experience_required: 1
work_authorization: cpt-opt
""")

    result = profile.load_profile(path)

    assert result["seeking"] == "internship"
    assert result["locations"] == ["United States", "Remote (US)"]
    assert result["max_years_experience_required"] == 1
    assert result["work_authorization"] == "cpt-opt"


def test_load_profile_defaults_optional_keys_to_none(tmp_path):
    path = _write(tmp_path, "seeking: internship\n")

    result = profile.load_profile(path)

    assert result["work_authorization"] is None
    assert result["max_years_experience_required"] is None
    assert result["locations"] == []


def test_load_profile_missing_file_names_the_example(tmp_path):
    with pytest.raises(profile.ProfileError) as excinfo:
        profile.load_profile(str(tmp_path / "absent.yaml"))

    assert "profile.example.yaml" in str(excinfo.value)


def test_load_profile_rejects_an_unknown_seeking_value(tmp_path):
    path = _write(tmp_path, "seeking: astronaut\n")

    with pytest.raises(profile.ProfileError) as excinfo:
        profile.load_profile(path)

    assert "astronaut" in str(excinfo.value)


def test_load_profile_rejects_an_unknown_authorization_value(tmp_path):
    path = _write(tmp_path, "seeking: internship\nwork_authorization: green-card\n")

    with pytest.raises(profile.ProfileError) as excinfo:
        profile.load_profile(path)

    assert "green-card" in str(excinfo.value)


def test_load_profile_rejects_a_non_mapping(tmp_path):
    path = _write(tmp_path, "- internship\n")

    with pytest.raises(profile.ProfileError):
        profile.load_profile(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_profile.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'job_fetcher.profile'`

- [ ] **Step 3: Write the implementation**

Create `job_fetcher/profile.py`:

```python
from __future__ import annotations

import yaml

VALID_SEEKING = ("internship", "new-grad", "full-time")
VALID_AUTHORIZATION = ("cpt-opt", "citizen-or-pr", "unrestricted")


class ProfileError(Exception):
    pass


def load_profile(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except FileNotFoundError:
        raise ProfileError(
            f"{path} not found. Copy profile.example.yaml to {path} and fill in what "
            "you are seeking and eligible for."
        )

    if data is None:
        raise ProfileError(f"{path} is empty. See profile.example.yaml for the shape.")
    if not isinstance(data, dict):
        raise ProfileError(
            f"{path} must be a mapping of settings. See profile.example.yaml."
        )

    seeking = data.get("seeking", "internship")
    if seeking not in VALID_SEEKING:
        raise ProfileError(
            f"seeking: {seeking!r} is not one of {', '.join(VALID_SEEKING)}"
        )

    authorization = data.get("work_authorization")
    if authorization is not None and authorization not in VALID_AUTHORIZATION:
        raise ProfileError(
            f"work_authorization: {authorization!r} is not one of "
            f"{', '.join(VALID_AUTHORIZATION)} (omit the key to disable the rule)"
        )

    locations = data.get("locations") or []
    if not isinstance(locations, list):
        raise ProfileError("locations: must be a list of location strings")

    return {
        "seeking": seeking,
        "graduation": data.get("graduation"),
        "locations": locations,
        "max_years_experience_required": data.get("max_years_experience_required"),
        "work_authorization": authorization,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_profile.py -q`
Expected: 6 passed

- [ ] **Step 5: Create the example file**

Create `profile.example.yaml`:

```yaml
# Copy to profile.local.yaml (gitignored) and edit.
# Used to reject postings you cannot accept before any tailoring is spent on them.

# What you are looking for: internship | new-grad | full-time
seeking: internship

# Graduation, YYYY-MM. Used as context when judging seniority language.
graduation: 2028-06

# Acceptable locations, matched loosely against the posting's location text.
# An empty list disables the location rule.
locations:
  - "United States"
  - "Remote (US)"

# Reject postings demanding more prior experience than this, in years.
# Omit or set to null to disable.
max_years_experience_required: 1

# cpt-opt        — F-1 student on practical training. Rejects citizens-only roles
#                  and employers that explicitly refuse CPT/OPT. Does NOT reject
#                  "no visa sponsorship", which CPT already satisfies for an
#                  internship.
# citizen-or-pr  — nothing is rejected on authorization grounds.
# unrestricted   — same, stated explicitly.
# Omit the key entirely to disable the rule.
work_authorization: cpt-opt
```

- [ ] **Step 6: Gitignore the local files**

```bash
grep -q '^profile.local.yaml' .gitignore || printf 'profile.local.yaml\nqueue.local.txt\noutbox/\n' >> .gitignore
```

- [ ] **Step 7: Run both suites and commit**

Run: `.venv/bin/python -m pytest -q` then `.venv39/bin/python -m pytest -q`
Expected: both pass, +6 tests

```bash
git add job_fetcher/profile.py profile.example.yaml tests/test_profile.py .gitignore
git commit -m "Add eligibility profile config"
```

---

### Task 2: The authorization verdict and location matching

The heart of the gate. Its three fixtures are real phrasings taken from a live board on 2026-09-08; the third is the one that breaks naive implementations.

**Files:**
- Modify: `job_fetcher/profile.py`, `tests/test_profile.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `OK`, `DISQUALIFIED`, `AMBIGUOUS`, `authorization_verdict(jd_text: str, mode) -> tuple[str, str | None]` returning `(verdict, reason_or_none)`; `location_matches(location_text, allowed) -> bool`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_profile.py`:

```python
# Real phrasings from a live job board, 2026-09-08.
CANNOT_SPONSOR_CPT = (
    "Unfortunately, we are not able to sponsor visas, including CPT/OPT or "
    "employ corp-to-corp."
)
CLEARANCE_AND_CITIZENSHIP = (
    "Clearance: Ability to hold or obtain a U.S. security clearance; U.S. "
    "citizenship as required for cleared federal work."
)
EEO_BOILERPLATE = (
    "Scale is an equal opportunity employer. We consider all qualified applicants "
    "regardless of race, color, ancestry, religion, sex, national origin, sexual "
    "orientation, age, citizenship, marital status, disability status, gender "
    "identity or Veteran status."
)
NO_SPONSORSHIP_PLAIN = (
    "Applicants must be authorized to work in the United States without "
    "sponsorship. We are unable to provide visa sponsorship for this role."
)


def test_authorization_rejects_a_no_cpt_opt_employer():
    verdict, reason = profile.authorization_verdict(CANNOT_SPONSOR_CPT, "cpt-opt")

    assert verdict == profile.DISQUALIFIED
    assert "CPT" in reason


def test_authorization_rejects_citizenship_and_clearance_requirements():
    verdict, reason = profile.authorization_verdict(
        CLEARANCE_AND_CITIZENSHIP, "cpt-opt"
    )

    assert verdict == profile.DISQUALIFIED
    assert reason


def test_authorization_ignores_equal_opportunity_boilerplate():
    """The trap. 'regardless of ... citizenship' is a non-discrimination clause,
    the opposite of a requirement, and appears in most US postings. A rule that
    matches on the word alone rejects nearly every eligible posting."""
    verdict, reason = profile.authorization_verdict(EEO_BOILERPLATE, "cpt-opt")

    assert verdict == profile.OK
    assert reason is None


def test_authorization_allows_plain_no_sponsorship_language():
    """CPT is school-authorized, so an F-1 intern already satisfies 'without
    sponsorship'. Rejecting this would discard a large share of open internships."""
    verdict, _ = profile.authorization_verdict(NO_SPONSORSHIP_PLAIN, "cpt-opt")

    assert verdict == profile.OK


def test_authorization_escalates_an_unclear_cpt_mention():
    text = "Sponsorship and CPT/OPT questions are handled case by case."

    verdict, reason = profile.authorization_verdict(text, "cpt-opt")

    assert verdict == profile.AMBIGUOUS
    assert reason


def test_authorization_is_disabled_for_other_modes():
    for mode in ("citizen-or-pr", "unrestricted", None):
        assert profile.authorization_verdict(CANNOT_SPONSOR_CPT, mode) == (
            profile.OK,
            None,
        )


def test_authorization_handles_empty_text():
    assert profile.authorization_verdict("", "cpt-opt") == (profile.OK, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_profile.py -q`
Expected: FAIL — `AttributeError: module 'job_fetcher.profile' has no attribute 'authorization_verdict'`

- [ ] **Step 3: Write the implementation**

Add `import re` to `job_fetcher/profile.py`'s imports, then append:

```python
OK = "ok"
DISQUALIFIED = "disqualified"
AMBIGUOUS = "ambiguous"

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+")

# A match inside any of these is a non-discrimination statement, which is the
# opposite of a requirement. Discard the whole sentence.
_NON_DISCRIMINATION = re.compile(
    r"(regardless of|without regard to|does not discriminate|"
    r"equal opportunity|equal employment)",
    re.I,
)

_DISQUALIFYING = (
    (
        re.compile(r"(not able to|cannot|can't|unable to)\s+sponsor[^;]{0,90}\b(CPT|OPT)\b", re.I),
        "employer states it cannot sponsor CPT/OPT",
    ),
    (
        re.compile(r"(do(es)? not|cannot|can't|unable to)\s+(hire|accept|employ)[^;]{0,60}\b(CPT|OPT)\b", re.I),
        "employer does not accept CPT/OPT",
    ),
    (
        re.compile(r"U\.?S\.?\s+citizenship\s+(is\s+)?(required|as required)", re.I),
        "US citizenship required",
    ),
    (
        re.compile(r"must be (a|an)\s+U\.?S\.?\s+citizen", re.I),
        "must be a US citizen",
    ),
    (
        re.compile(r"U\.?S\.?\s+citizens?(\s+or\s+permanent\s+residents?)?\s+only", re.I),
        "US citizens or permanent residents only",
    ),
    (
        re.compile(r"(ability to (hold or )?obtain|active|current)[^;]{0,30}security clearance", re.I),
        "security clearance required",
    ),
)

# Mentions that are relevant but match no known disqualifying frame: escalate
# rather than guess.
_UNCLEAR = re.compile(r"\b(CPT|OPT)\b|citizenship|citizen", re.I)


def authorization_verdict(jd_text: str, mode):
    """Judge a JD's work-authorization language against the profile's mode.

    Returns (verdict, reason). Only the 'cpt-opt' mode filters anything.
    """
    if mode != "cpt-opt" or not jd_text:
        return OK, None

    unclear_reason = None
    for sentence in _SENTENCE_SPLIT.split(jd_text):
        if _NON_DISCRIMINATION.search(sentence):
            continue
        for pattern, reason in _DISQUALIFYING:
            if pattern.search(sentence):
                return DISQUALIFIED, reason
        if unclear_reason is None and _UNCLEAR.search(sentence):
            unclear_reason = (
                "work-authorization language present but not clearly disqualifying: "
                + " ".join(sentence.split())[:160]
            )

    if unclear_reason is not None:
        return AMBIGUOUS, unclear_reason
    return OK, None
```

The sentence-level loop is what makes the EEO exclusion work: discarding the whole sentence containing "regardless of" means a `citizenship` match inside it can never be seen, while the same word in a requirement sentence elsewhere still is.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_profile.py -q`
Expected: 13 passed (the 6 from Task 1 plus 7 new)

- [ ] **Step 5: Write the failing location test**

Location matching is the other genuinely deterministic rule, so it belongs here rather
than in a skill's judgment. Append to `tests/test_profile.py`:

```python
def test_location_matches_is_case_and_substring_tolerant():
    allowed = ["United States", "Remote (US)"]

    assert profile.location_matches("San Francisco, CA, United States", allowed)
    assert profile.location_matches("remote (us)", allowed)


def test_location_matches_rejects_an_unlisted_location():
    assert not profile.location_matches("Israel, Raanana", ["United States"])


def test_location_matches_allows_everything_when_no_locations_configured():
    assert profile.location_matches("Israel, Raanana", [])


def test_location_matches_treats_missing_location_text_as_a_match():
    """An unstated location is ambiguous, and the gate errs toward eligible."""
    assert profile.location_matches(None, ["United States"])
    assert profile.location_matches("", ["United States"])
```

- [ ] **Step 6: Run it and watch it fail**

Run: `.venv/bin/python -m pytest tests/test_profile.py -q`
Expected: FAIL — no attribute `location_matches`

- [ ] **Step 7: Implement location matching**

Append to `job_fetcher/profile.py`:

```python
def location_matches(location_text, allowed) -> bool:
    """True when the posting's location is acceptable.

    An empty `allowed` disables the rule, and missing location text counts as a
    match: an unstated location is ambiguous, and the gate errs toward eligible.
    """
    if not allowed:
        return True
    if not location_text:
        return True
    haystack = location_text.lower()
    return any(entry.lower() in haystack for entry in allowed)
```

- [ ] **Step 8: Run both suites and commit**

Run: `.venv/bin/python -m pytest -q` then `.venv39/bin/python -m pytest -q`
Expected: 17 tests in `tests/test_profile.py`

```bash
git add job_fetcher/profile.py tests/test_profile.py
git commit -m "Add the work-authorization verdict and location matching"
```

---

### Task 3: The `packeted` flag

**Files:**
- Modify: `job_fetcher/store.py`, `tests/test_store.py`

**Interfaces:**
- Produces: `merge_new_postings` also sets `packeted: False`; `mark_packeted(postings, ids) -> None`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_store.py`:

```python
def test_merge_new_postings_initialises_packeted_false():
    fetched = [{"id": "acme-1", "company": "Acme", "title": "Engineer"}]

    merged, _ = store.merge_new_postings([], fetched, "2026-09-08")

    assert merged[0]["packeted"] is False


def test_mark_packeted_sets_only_the_named_ids():
    postings = [
        {"id": "acme-1", "packeted": False},
        {"id": "acme-2", "packeted": False},
    ]

    store.mark_packeted(postings, {"acme-1"})

    assert postings[0]["packeted"] is True
    assert postings[1]["packeted"] is False


def test_mark_packeted_tolerates_a_posting_without_the_key():
    postings = [{"id": "acme-1"}]

    store.mark_packeted(postings, {"acme-1"})

    assert postings[0]["packeted"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_store.py -q`
Expected: FAIL — `KeyError: 'packeted'`, then `AttributeError: ... has no attribute 'mark_packeted'`

- [ ] **Step 3: Write the implementation**

In `job_fetcher/store.py`, add one line inside `merge_new_postings`'s loop, immediately after `posting["scored"] = False`:

```python
        posting["packeted"] = False
```

and append this function:

```python
def mark_packeted(postings: list[dict], ids: set) -> None:
    for posting in postings:
        if posting["id"] in ids:
            posting["packeted"] = True
```

- [ ] **Step 4: Run both suites and commit**

Run: `.venv/bin/python -m pytest -q` then `.venv39/bin/python -m pytest -q`

```bash
git add job_fetcher/store.py tests/test_store.py
git commit -m "Track whether a posting already has a packet"
```

---

### Task 4: Queue parsing and packet slugs

**Files:**
- Create: `job_fetcher/tailor.py`, `tests/test_tailor.py`

**Interfaces:**
- Produces: `parse_queue(path: str) -> tuple[list[str], list[str]]` returning `(urls, skipped_lines)`; `packet_slug(company, role, posting_id, existing) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tailor.py`:

```python
from __future__ import annotations

from job_fetcher import tailor


def _queue(tmp_path, text):
    path = tmp_path / "queue.local.txt"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_parse_queue_returns_empty_when_the_file_is_absent(tmp_path):
    assert tailor.parse_queue(str(tmp_path / "absent.txt")) == ([], [])


def test_parse_queue_strips_comments_blanks_and_whitespace(tmp_path):
    path = _queue(tmp_path, """
# postings to tailor for
  https://job-boards.greenhouse.io/stripe/jobs/1

https://jobs.lever.co/palantir/abc   # trailing note
""")

    urls, skipped = tailor.parse_queue(path)

    assert urls == [
        "https://job-boards.greenhouse.io/stripe/jobs/1",
        "https://jobs.lever.co/palantir/abc",
    ]
    assert skipped == []


def test_parse_queue_deduplicates_preserving_order(tmp_path):
    path = _queue(tmp_path, """
https://example.com/a
https://example.com/b
https://example.com/a
""")

    urls, _ = tailor.parse_queue(path)

    assert urls == ["https://example.com/a", "https://example.com/b"]


def test_parse_queue_reports_lines_that_are_not_urls(tmp_path):
    path = _queue(tmp_path, "https://example.com/a\nremember the NVIDIA one\n")

    urls, skipped = tailor.parse_queue(path)

    assert urls == ["https://example.com/a"]
    assert skipped == ["remember the NVIDIA one"]


def test_packet_slug_combines_company_and_role():
    slug = tailor.packet_slug("Nvidia", "Infiniband Network Software Engineer", "x-1", set())

    assert slug == "nvidia-infiniband-network-software-engineer"


def test_packet_slug_truncates_a_very_long_role():
    slug = tailor.packet_slug("Acme", "Senior " * 40 + "Engineer", "x-1", set())

    assert len(slug) <= tailor.MAX_SLUG_LENGTH
    assert slug.startswith("acme-senior")
    assert not slug.endswith("-")


def test_packet_slug_folds_non_ascii_and_punctuation():
    slug = tailor.packet_slug("Bosch Group", "Pflichtpraktikum — People & Matter", "x-1", set())

    assert slug == "bosch-group-pflichtpraktikum-people-matter"


def test_packet_slug_disambiguates_a_collision_with_the_posting_id():
    existing = {"acme-engineer"}

    slug = tailor.packet_slug("Acme", "Engineer", "greenhouse-4567890", existing)

    assert slug != "acme-engineer"
    assert "4567890" in slug


```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_tailor.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'job_fetcher.tailor'`

- [ ] **Step 3: Write the implementation**

Create `job_fetcher/tailor.py`:

```python
from __future__ import annotations

import os
import re
import unicodedata

MAX_SLUG_LENGTH = 80

_COMMENT = re.compile(r"\s+#.*$")


def parse_queue(path: str):
    """Read the URL queue. Returns (urls, skipped_lines).

    The queue is owned by the user and never rewritten: comments, blank lines and
    duplicates are all tolerated, and anything that is not an http(s) URL is
    reported rather than guessed at.
    """
    if not os.path.exists(path):
        return [], []

    urls = []
    skipped = []
    seen = set()
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            line = _COMMENT.sub("", line).strip()
            if not line:
                continue
            if not line.startswith(("http://", "https://")):
                skipped.append(line)
                continue
            if line in seen:
                continue
            seen.add(line)
            urls.append(line)
    return urls, skipped


def _slugify(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text or "")
    folded = folded.encode("ascii", "ignore").decode("ascii")
    folded = re.sub(r"[^A-Za-z0-9]+", "-", folded).strip("-").lower()
    return re.sub(r"-{2,}", "-", folded)


def packet_slug(company: str, role: str, posting_id: str, existing) -> str:
    base = f"{_slugify(company)}-{_slugify(role)}".strip("-")
    base = re.sub(r"-{2,}", "-", base)
    if len(base) > MAX_SLUG_LENGTH:
        base = base[:MAX_SLUG_LENGTH].rstrip("-")
    if base not in existing:
        return base

    suffix = _slugify(posting_id).split("-")[-1]
    room = MAX_SLUG_LENGTH - len(suffix) - 1
    return f"{base[:room].rstrip('-')}-{suffix}"

```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_tailor.py -q`
Expected: 8 passed

- [ ] **Step 5: Run both suites and commit**

```bash
git add job_fetcher/tailor.py tests/test_tailor.py
git commit -m "Add queue parsing and packet slug generation"
```

---

### Task 5: Apply the eligibility gate in the scorer

**Files:**
- Modify: `plugins/cvapplicate/skills/cv-score-postings/SKILL.md`

**Interfaces:**
- Consumes: `job_fetcher/profile.py`.
- Produces: `matches.local.yaml` entries may now carry `eligible: false` and `reasons`.

No test cycle: this is instructions for a model. Verification is the frontmatter check plus a read-through against the spec.

- [ ] **Step 1: Read the spec's gate section**

Read the "Prerequisite: the eligibility gate" section of `docs/superpowers/specs/2026-09-08-tailor-packets-design.md` in full, including the three real phrasings. Your edit must not contradict it.

- [ ] **Step 2: Insert the gate as a new step 3**

In `plugins/cvapplicate/skills/cv-score-postings/SKILL.md`, insert this immediately after the existing step 2 (branch discovery) and renumber the following steps:

```markdown
3. Load the eligibility profile from `profile.local.yaml` and apply the gate to each
   unscored posting **before** scoring it. If the file is absent, skip the gate
   entirely and note that in the report — do not invent a profile.

   Reject a posting, recording every applicable reason, when:
   - the JD states a minimum years-of-experience above
     `max_years_experience_required`. Judge whether the figure is a *requirement*
     rather than incidental prose; "4+ years of experience" in a requirements list
     counts, the same words inside a company blurb do not.
   - `seeking` is `internship` and the posting is plainly a full-time non-internship
     role.
   - `locations` is non-empty and no stated location matches any entry.
   - `python3 -c "from job_fetcher.profile import authorization_verdict; ..."` returns
     `disqualified` for the JD text under the profile's `work_authorization`. Run that
     helper rather than judging authorization language yourself: it encodes which
     phrasings disqualify and, critically, which do not. If it returns `ambiguous`,
     you adjudicate — read the quoted sentence it returns and decide, defaulting to
     eligible.

   Record an ineligible posting in `matches.local.yaml` as:
   ```yaml
   - posting_id: workday-nvidia-JR2007263
     company: "Nvidia"
     title: "Infiniband Network Software Engineer"
     url: "https://…"
     scored_date: 2026-09-08
     eligible: false
     reasons:
       - "requires 4+ years of experience; profile allows 1"
       - "location Israel, Raanana matches none of: United States, Remote (US)"
   ```
   No score fields. Mark it `scored: true` in `postings.local.yaml` so it is not
   reprocessed, and do not tailor it.

   **When a rule is ambiguous, the posting stays eligible** and the ambiguity goes in
   the rationale. A gate that guesses is worse than no gate: a wrongly rejected
   posting is invisible, while a wrongly accepted one merely costs one score.
```

- [ ] **Step 3: Note the eligible-count in the Output section**

In the `## Output` section, extend the report line to include how many postings were rejected by the gate and why, so a silent mass-rejection is visible immediately rather than looking like a quiet night.

- [ ] **Step 4: Verify the frontmatter still parses**

```bash
.venv/bin/python -c "
import pathlib, yaml
text = pathlib.Path('plugins/cvapplicate/skills/cv-score-postings/SKILL.md').read_text()
print('frontmatter OK:', yaml.safe_load(text.split('---')[1])['name'])
"
```

Expected: `frontmatter OK: cv-score-postings`

- [ ] **Step 5: Commit**

```bash
git add plugins/cvapplicate/skills/cv-score-postings/SKILL.md
git commit -m "Apply the eligibility gate before scoring"
```

---

### Task 6: The `cv-tailor-packet` skill

**Files:**
- Create: `plugins/cvapplicate/skills/cv-tailor-packet/SKILL.md`

- [ ] **Step 1: Read a sibling skill for house style**

Run: `cat plugins/cvapplicate/skills/cv-review/SKILL.md`

Match its frontmatter shape and its numbered imperative procedure. This skill is `cv-review`'s scoring and editing logic, minus every git write, plus artifact output.

- [ ] **Step 2: Write the skill**

Create `plugins/cvapplicate/skills/cv-tailor-packet/SKILL.md`:

```markdown
---
name: cv-tailor-packet
description: Tailor the CV for one scored posting and write a submit-ready packet to outbox/, without committing anything or touching the working tree. Use when a posting has been resolved and scored and a packet is wanted; normally invoked by tailor-packets.sh draining the queue.
---

# CV Tailor Packet

Produces everything needed to submit one application, as files. Writes no git
history: it never runs `git add`, `git commit`, or `git checkout`, and its runner is
not granted those. Recording that you applied is `cv-log-application`'s job.

## Inputs needed

1. **A posting id** present in `postings.local.yaml` with `scored: true` and an entry
   in `matches.local.yaml`. If it is marked `eligible: false`, stop and report the
   reasons — never tailor for a posting the gate rejected.
2. **A branch**, optional. Defaults to the posting's `best_branch` from
   `matches.local.yaml`.

## Procedure

1. Read the posting from `postings.local.yaml`. If `description` is null or empty,
   stop — never tailor against a title alone.
2. If `packeted` is already true, report the existing packet path and stop.
3. Read `claims-guardrails.md` and the experience bank via
   `git show main:master-data.md`. **The guardrails are binding**, exactly as in
   `cv-review`: they state how each claim may and may not be phrased. Never write a
   bullet that violates one, however much better it would score.
4. Create an isolated checkout:
   `git worktree add .worktrees/tailor-<posting-id> <branch>`
   Work only inside it. Never `git checkout` in the main working tree — this skill
   runs unattended and must not disturb whatever the user has open.
5. Score the branch's `cv.tex` as `cv-review` does: **Base Quality /100** (impact 40%,
   competencies 35%, presentation 25%) and **JD Fit /100** (keyword match 40%,
   experience relevance 40%, seniority fit 20%). Keep both as the *before* scores.
6. Pool weaknesses across both layers, take the worst 3, and edit the worktree's
   `cv.tex` to fix them, staying inside the guardrails. Where the JD wants something
   not grounded in the experience bank, keep the honest wording and record it as a
   gap.
7. Compile-check inside the worktree with whichever of `latexmk`, `pdflatex`,
   `tectonic` is found first.
   - None found → `compile: skipped`, no PDF, and say so in `PACKET.md`.
   - Compile fails → `compile: failed`; keep the tailored `.tex`, write the LaTeX
     error into `PACKET.md`, and continue to step 9. A broken packet must never look
     submit-ready.
8. Re-score both layers against the edited `cv.tex` for the *after* scores.
9. Produce the ranked skills list for the portal's Skills field using the same method
   as `cv-application-skills`, grounded in the experience bank and the guardrails.
10. Write the packet to `outbox/<slug>/`, where `<slug>` comes from
    `job_fetcher/tailor.py`'s `packet_slug`:
    - `<First>_<Last>_CV_<Company>.pdf` — the upload, named as `cv-review` names it
    - `cv.tex` — the tailored source, copied out of the worktree
    - `jd.txt` — the posting's `description`
    - `skills.txt` — the ranked keywords, one per line
    - `PACKET.md` — for the user: before/after scores, the three fixes and why, the
      gap list, and any compile problem
    - `packet.yaml` — machine-readable, for the Filler:
      ```yaml
      posting_id: workday-nvidia-JR2007263
      company: "Nvidia"
      role: "Infiniband Network Software Engineer"
      url: "https://…"
      industry_branch: quant-trading
      created: 2026-09-08
      cv_pdf: Ozan_Kan_CV_Nvidia.pdf
      cv_tex: cv.tex
      compile: ok            # ok | failed | skipped
      skills: ["C++", "…"]
      base_quality_before: {total: 93, impact: 93, competencies: 93, presentation: 91}
      base_quality_after:  {total: 95, impact: 95, competencies: 94, presentation: 93}
      jd_fit_before: {total: 61, keyword_match: 78, experience_relevance: 60, seniority_fit: 30}
      jd_fit_after:  {total: 72, keyword_match: 88, experience_relevance: 70, seniority_fit: 30}
      weak_points_fixed: ["…"]
      gaps: ["…"]
      applied: false
      ```
11. Remove the worktree, **on every exit path including failure**:
    `git worktree remove --force .worktrees/tailor-<posting-id>` then
    `git worktree prune`. A leftover worktree breaks the next run.
12. Set `packeted: true` for that posting in `postings.local.yaml`.
13. Report: the packet path, before/after scores, the three fixes, and the gap list.

## Error handling

- Posting missing, unscored, or `eligible: false` → stop and say which.
- `description` empty → stop; never tailor blind.
- Branch has no `cv.tex` → stop and name the branch.
- Compile failure → packet still written, marked `compile: failed`.
- Worktree removal is unconditional. If removal itself fails, say so loudly in the
  report: the next run cannot proceed until it is cleaned up.
- Never run `git add`, `git commit`, `git push`, or `git checkout`. Never edit
  `cv.tex` outside the worktree, and never edit `master-data.md` or
  `claims-guardrails.md` at all.

## Permission scope

This skill needs no commit rights, by design:

```
Read Write Edit(postings.local.yaml) Bash(git worktree:*) Bash(git show:*)
Bash(latexmk:*) Bash(pdflatex:*) Bash(tectonic:*)
```

The absence of `Bash(git add:*)` and `Bash(git commit:*)` is what makes it impossible
for an unattended run to claim an application it did not make.
```

- [ ] **Step 3: Verify the frontmatter parses**

```bash
.venv/bin/python -c "
import pathlib, yaml
text = pathlib.Path('plugins/cvapplicate/skills/cv-tailor-packet/SKILL.md').read_text()
data = yaml.safe_load(text.split('---')[1])
assert data['name'] == 'cv-tailor-packet'
print('frontmatter OK:', data['name'])
"
```

- [ ] **Step 4: Commit**

```bash
git add plugins/cvapplicate/skills/cv-tailor-packet/SKILL.md
git commit -m "Add the cv-tailor-packet skill"
```

---

### Task 7: The `cv-log-application` skill

**Files:**
- Create: `plugins/cvapplicate/skills/cv-log-application/SKILL.md`

- [ ] **Step 1: Read the existing log schema**

Run: `sed -n '1,30p' applications/log.yaml` and
`cat plugins/cvapplicate/skills/cv-log-outcome/SKILL.md`

The entry you write must match the existing shape field-for-field. `cv-log-outcome`
is the closest sibling in style, and it is what later updates the `outcome` field.

- [ ] **Step 2: Write the skill**

Create `plugins/cvapplicate/skills/cv-log-application/SKILL.md`:

```markdown
---
name: cv-log-application
description: Record that you actually submitted an application from an outbox packet - commits that packet's cv.tex to the industry branch and appends the log entry with the real submission date. Use when the user says they have applied.
---

# CV Log Application

The only step in the packet flow that writes git history. It runs when you have
actually submitted an application, which is what keeps `applications/log.yaml` honest:
tailoring a CV is not applying with it.

## Inputs needed

1. **Which packet** — a company name, role, or `outbox/` directory. If ambiguous,
   list the candidates with their `created` dates and ask; never guess.

## Procedure

1. Run `git status`. If the working tree is not clean, stop and say what is
   uncommitted.
2. Read the packet's `packet.yaml`. If `applied` is already `true`, report the
   existing log entry id and stop — this application is already recorded.
3. If `compile` is `failed` or `skipped`, warn the user that no verified PDF was
   produced and confirm they still want to record the application before continuing.
4. `git checkout <industry_branch>` from `packet.yaml`.
5. Copy the packet's `cv.tex` over the branch's `cv.tex`.
6. Commit that file only:
   `git add cv.tex && git commit -m "Apply: <company> <role>"`
   Capture the SHA with `git rev-parse HEAD`.
7. `git checkout main`.
8. Append one entry to `applications/log.yaml`, matching the existing schema exactly:
   ```yaml
   - id: <company-slug>-<industry>-<yyyy-mm>
     company: "<company>"
     role: "<role>"
     industry_branch: <branch>
     date_applied: <today>
     jd_source: url
     jd_url: "<packet url>"
     jd_summary: "<two or three sentences on what the posting actually asks for>"
     cv_commit: "<sha from step 6>"
     base_quality_score: <base_quality_after from packet.yaml>
     jd_fit_score: <jd_fit_after from packet.yaml>
     weak_points_fixed: <from packet.yaml, plus any gaps as GAP entries>
     outcome: pending
     outcome_date: null
   ```
   Use the **after** scores: they describe the CV that was actually sent.
9. Commit: `git add applications/log.yaml && git commit -m "Log application: <company> <role>"`.
10. Set `applied: true` in the packet's `packet.yaml`.
11. Report the entry id, the branch, the `cv_commit`, and that
    `git show <cv_commit>:cv.tex` will recover the exact CV sent.

## Error handling

- Dirty working tree at step 1 → stop before any checkout.
- Ambiguous packet → list candidates and ask.
- `applied: true` already → stop; do not write a second entry.
- Packet missing `cv.tex` → stop; there is nothing to commit.
- If the run fails after step 6 but before step 9, the branch has a commit with no log
  entry. Say so explicitly and name the SHA so it can be logged or reverted by hand —
  never leave the user to discover the mismatch later.
```

- [ ] **Step 3: Verify the frontmatter parses and commit**

```bash
.venv/bin/python -c "
import pathlib, yaml
text = pathlib.Path('plugins/cvapplicate/skills/cv-log-application/SKILL.md').read_text()
print('frontmatter OK:', yaml.safe_load(text.split('---')[1])['name'])
"
git add plugins/cvapplicate/skills/cv-log-application/SKILL.md
git commit -m "Add the cv-log-application skill"
```

---

### Task 8: The queue runner

**Files:**
- Create: `tailor-packets.sh`, `launchd/com.cvapplicate.tailor-packets.plist.example`

- [ ] **Step 1: Read the existing runner for the house pattern**

Run: `cat score-postings.sh`

Match its shape: header comment explaining the schedule and the PATH pitfall,
`set -euo pipefail`, `cd "$(dirname "$0")"`, then `claude -p` with an explicit
`--allowedTools`.

- [ ] **Step 2: Write the runner**

Create `tailor-packets.sh`:

```bash
#!/bin/bash
# Drains queue.local.txt: resolves each URL, scores it (applying the eligibility
# gate), and writes a submit-ready packet to outbox/ for anything eligible.
#
# Writes no git history. The allowedTools list below deliberately grants no
# `git add` and no `git commit`, so an unattended run cannot claim an application
# you did not make. Recording an application is cv-log-application's job, and it
# is interactive only.
#
# Can run on a schedule (see launchd/com.cvapplicate.tailor-packets.plist.example)
# or by hand after adding URLs. Requires the `claude` CLI on PATH — if
# `which claude` differs between your interactive shell and a bare launchd
# environment, update the plist, the same PATH mismatch documented for
# fetch-postings.py's python3.
set -euo pipefail
cd "$(dirname "$0")"

claude -p "Drain queue.local.txt: for each URL, run cv-resolve-posting, then score it, then run cv-tailor-packet for every eligible posting that has no packet yet. Report what was packeted, what the gate rejected and why, and any queue line that was not a URL." \
  --permission-mode acceptEdits \
  --allowedTools "Read Write Edit(postings.local.yaml) Edit(matches.local.yaml) Bash(python3 resolve-posting.py:*) Bash(git worktree:*) Bash(git show:*) Bash(git for-each-ref:*) Bash(latexmk:*) Bash(pdflatex:*) Bash(tectonic:*)"
```

- [ ] **Step 3: Make it executable and confirm the grant has no commit rights**

```bash
chmod +x tailor-packets.sh
grep -E 'git (add|commit|push)' tailor-packets.sh && echo "FAIL: grant includes a git write" || echo "OK: no git write in the grant"
```

Expected: `OK: no git write in the grant`

- [ ] **Step 4: Write the launchd example**

Create `launchd/com.cvapplicate.tailor-packets.plist.example`. It runs at 9:00, after
the 8:30 scoring job, so the queue is drained against fresh scores:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>com.cvapplicate.tailor-packets</string>
	<key>ProgramArguments</key>
	<array>
		<string>/ABSOLUTE/PATH/TO/CVApplicate/tailor-packets.sh</string>
	</array>
	<key>WorkingDirectory</key>
	<string>/ABSOLUTE/PATH/TO/CVApplicate</string>
	<key>StartCalendarInterval</key>
	<dict>
		<key>Hour</key>
		<integer>9</integer>
		<key>Minute</key>
		<integer>0</integer>
	</dict>
	<key>StandardOutPath</key>
	<string>/ABSOLUTE/PATH/TO/CVApplicate/tailor-packets.log</string>
	<key>StandardErrorPath</key>
	<string>/ABSOLUTE/PATH/TO/CVApplicate/tailor-packets.log</string>
</dict>
</plist>
```

Add `tailor-packets.log` to `.gitignore` if the existing `*.log` pattern does not
already cover it.

- [ ] **Step 5: Commit**

```bash
git add tailor-packets.sh launchd/com.cvapplicate.tailor-packets.plist.example
git commit -m "Add the queue-draining runner"
```

---

### Task 9: Documentation

The README advertises eight skills in several places; this phase adds two.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Find every place the count appears**

```bash
grep -n "eight skills\|All eight" README.md
```

- [ ] **Step 2: Update the count to ten and add both table rows**

Change each "eight skills" to "ten skills", and in the `## Skills` table add:

```markdown
| **cv-tailor-packet** | Tailors the CV for one scored posting and writes a submit-ready packet to `outbox/` — never commits, never claims you applied |
| **cv-log-application** | Records that you actually submitted a packet: commits that CV to the industry branch and appends the log entry |
```

In `## Status`, change "All eight skills are implemented" to "All ten skills are
implemented" and leave the "six are validated end-to-end" figure alone — these two are
new and unvalidated, like the rest.

- [ ] **Step 3: Add a usage section**

Add after the "Scoring a posting you found yourself" section:

```markdown
## Building a packet to submit

Add posting URLs to `queue.local.txt`, one per line:

```
# things to apply to
https://job-boards.greenhouse.io/example/jobs/12345
```

Then drain it:

```bash
./tailor-packets.sh
```

Each eligible posting becomes a folder under `outbox/` holding the tailored PDF, the
`cv.tex` behind it, the ranked skills list for the portal's Skills field, the gap list,
and the before/after scores. Nothing is committed and nothing is logged — a packet is
a draft, not an application.

Postings you cannot accept never reach a tailoring pass. `profile.local.yaml` states
what you are seeking and eligible for, and the gate rejects clear-cut mismatches —
too much required experience, wrong location, citizens-only roles — recording the
reasons in `matches.local.yaml` instead of a misleading score. Ambiguous cases are
deliberately allowed through.

When you have actually submitted one:

```
Run cv-log-application for Example Corp
```

That commits the packet's `cv.tex` to the industry branch and writes the log entry
with the real submission date, so `git show <cv_commit>:cv.tex` recovers exactly what
you sent — for the applications you really made, and no others.
```

- [ ] **Step 4: Verify no stale count remains, run both suites, commit**

```bash
grep -n "eight skills" README.md && echo "STILL STALE" || echo "clean"
.venv/bin/python -m pytest -q
.venv39/bin/python -m pytest -q
git add README.md
git commit -m "Document the packet flow"
```

---

## Deferred

Recorded so a reviewer does not read these as gaps:

- **Filling and submitting the application.** Phase C. This plan ends at a packet.
- **Nightly discovery → tailoring.** Dropped in the spec, with reasoning.
- **The scorer's seniority weighting** for postings that pass the gate.
- **Plugin distribution of the Python pipeline.** This phase adds two more root-level
  modules and a runner, so the manual sync into a data repo grows further.
