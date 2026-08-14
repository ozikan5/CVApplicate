# Job Postings Fetcher — Design

**Date:** 2026-08-14
**Status:** Approved for planning

## Purpose

Phase 1 of a larger job-application pipeline. Automatically pull job listings from
companies' Applicant Tracking System (ATS) APIs, store them locally, detect which ones
are new since the last run, and email a summary. Runs unattended, once a day.

This replaces manually checking career pages. It deliberately does **not** scrape
LinkedIn or Handshake — both prohibit scraping in their terms of service and carry real
account-suspension risk (LinkedIn actively detects and bans automation; Handshake is tied
to the user's university identity). Instead it targets ATS platforms (Greenhouse, Lever)
that expose public, unauthenticated, ToS-compliant JSON APIs for their job boards.

## Non-goals

- No LinkedIn/Handshake scraping, now or later, without a separate explicit decision.
- No scoring/matching against the CV — that's Phase 2, a separate spec once this exists.
- No auto-tailoring or auto-applying — a human reads the email and decides what to act on.
- No Workday or other ATS platforms yet — Greenhouse and Lever cover a large share of
  companies with public, well-documented, uniform APIs. Others can be added later as
  separate adapters without changing the rest of the design.
- No push notifications for now — that requires an active Claude Code session, which
  doesn't fit a script meant to run quietly in the background via the OS scheduler.

## Repository structure

```
CVApplicate/
├── fetch-postings.py         script; same style/standalone-ness as check-cv-text.py
├── companies.example.yaml    generic placeholder company list, ships in the template repo
├── companies.local.yaml      user's real target list — gitignored (*.local.yaml)
├── postings.local.yaml       fetched postings store — gitignored, personal data
└── .env                      SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_APP_PASSWORD /
                               NOTIFY_TO — gitignored (already covered by .gitignore)
```

This mirrors the repo's existing personal-vs-template split: `.example` files ship
generic and get filled in per-user; `.local.*` files hold real data and are gitignored by
the patterns already in `.gitignore`. No fork is required just to use this feature —
unlike `cv.tex`/`master-data.md`, which do require forking because they're tracked files
meant to carry real git history.

## Components

### 1. Config loader
Reads `companies.local.yaml`: a list of entries `{name, slug, ats}` where `ats` is
`greenhouse` or `lever`. If the file is missing, fails with a message pointing at
`companies.example.yaml` to copy from.

### 2. ATS adapters
One function per ATS platform, each calling that platform's public JSON endpoint for a
given company slug and normalizing the response into a common posting shape:

```
{ id, company, title, url, location, posted_date }
```

- `fetch_greenhouse(slug)` → `https://boards-api.greenhouse.io/v1/boards/<slug>/jobs`
- `fetch_lever(slug)` → `https://api.lever.co/v0/postings/<slug>?mode=json`

Both are public, unauthenticated, documented endpoints — no login, no scraping-detection
risk, no ToS conflict.

### 3. Dedup/diff engine
Loads the existing `postings.local.yaml`, compares freshly fetched postings against it by
stable ATS job ID. Anything not previously seen is "new" for this run. Postings that
disappear from the ATS feed (closed/filled) are left in the local store as-is, not
deleted — historical record, not a live mirror.

### 4. Persistence
Merges new postings into `postings.local.yaml`, preserving `first_seen` date on postings
that already existed. Each stored posting carries a `notified: bool` flag, set `true`
only after a successful email covering it. Writes the file back after every run,
successful or partial.

### 5. Notifier
If there are new postings, sends one summary email (company, title, location, link — one
line per posting) via SMTP using an app-specific password read from `.env`. No email is
sent when nothing new was found, to keep the channel quiet and worth reading.

## Data flow summary

1. User copies `companies.example.yaml` → `companies.local.yaml` and fills in real
   companies/slugs they want to track, and creates `.env` with SMTP credentials.
2. `launchd` (macOS scheduler) runs `fetch-postings.py` once a day.
3. For each configured company: call the matching ATS adapter, normalize results.
4. Diff against `postings.local.yaml` to find new postings.
5. Write merged results back to `postings.local.yaml`.
6. If any postings were new, send the summary email.

## Error handling

- **One company's fetch fails** (network error, unknown slug, non-200 response) → log the
  error, skip that company, continue with the rest. One bad company shouldn't block the
  whole run.
- **`companies.local.yaml` missing** → fail fast with a clear message pointing at the
  `.example` file; don't run with an empty/implicit config.
- **SMTP send fails** → log the error, but don't mark those postings as notified. They
  stay flagged "new" in `postings.local.yaml` (e.g. a `notified: false` field) so the next
  successful run's email still includes them instead of silently dropping them because
  they're no longer new by ID.
- **ATS response shape changes** (unexpected/missing fields) → log and skip that posting
  rather than crashing the whole run.
- Between-company requests include a brief delay — good citizenship on public APIs, not
  a workaround for any rate limit these APIs currently document.

## Testing

- ATS adapters tested against recorded fixture JSON (sample real responses saved as test
  fixtures) — no live network calls in the test suite.
- Dedup logic tested with synthetic before/after posting sets, including the "posting
  disappeared from feed" case.
- Email sending is mocked in tests; a test never actually sends mail.
- Config loader tested for both the happy path and the missing-file case.

## Key decisions log

- **Greenhouse + Lever only, to start** — public, uniform, well-documented APIs; covers a
  large share of companies without needing scraping at all.
- **No LinkedIn/Handshake** — ToS and account-risk reasons, see Purpose above.
- **Local OS scheduling (`launchd`), not a Claude Code scheduled session** — keeps the
  script self-contained and working independent of whether Claude Code is open; also a
  cleaner artifact for learning the underlying mechanics directly.
- **Email only, no push notification, for now** — push requires a live Claude Code
  session; a background daily job shouldn't depend on one being open. Revisit if wanted
  later as a second channel.
- **`.local.yaml` pattern instead of requiring a fork** — this feature's personal data
  (target companies, fetched postings) doesn't need real git history the way CV content
  does, so the lighter-weight gitignore convention already in this repo is a better fit
  than forking.
- **Postings are an append-only historical record**, not a live mirror — closed postings
  stay in `postings.local.yaml` rather than being deleted when they drop off the ATS feed.
