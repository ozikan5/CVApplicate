# Job Postings Scoring — Design

**Date:** 2026-08-31
**Status:** Approved for planning

## Purpose

Phase 2 of the job-application pipeline (Phase 1: `fetch-postings.py`, see
`docs/superpowers/specs/2026-08-14-job-postings-fetcher-design.md`). Score every newly
fetched job posting against the user's CV data, unattended, once a day, so the postings
worth acting on surface on their own instead of requiring the user to read every posting
by hand.

Scoring reuses the same JD Fit rubric `cv-review` already applies interactively
(keyword match, experience relevance, seniority fit) — this phase only automates running
that rubric nightly across every new posting and every industry branch the user
maintains. It does not replace `cv-review`; a strong match found here still goes through
`cv-review` (or is applied to manually) before anything gets submitted.

## Non-goals

- **No CV edits.** This phase only reads `master-data.md` and `cv.tex`; it never writes
  to them, and never runs `cv-review`'s edit-and-commit flow. Editing stays a human-in-
  the-loop decision, triggered manually per posting.
- **No git commits, no branch checkouts.** Branch content is read via
  `git show <branch>:<path>`, so the working tree's checked-out branch and any
  in-progress uncommitted changes are never touched by the nightly run.
- **No auto-apply.** Scoring produces a ranked local file the user reads when they choose
  to; nothing gets submitted anywhere automatically.
- **No email/push notification.** Unlike Phase 1's summary email, scores are written only
  to a local file. Revisit as a separate decision if the user later wants a proactive
  nudge for high-scoring matches.
- **No re-scoring on demand / no score-invalidation on `master-data.md` changes.** Each
  posting is scored once, the same way Phase 1 marks postings `notified` once. If the
  user's CV data changes materially, previously-scored postings keep their old scores
  until re-scored by hand (out of scope for the nightly job).
- **No pre-filtering of which branches to score against.** Every posting is scored
  against every industry branch in the repo. With a handful of branches this is cheap
  enough that a relevance pre-filter would be premature optimization.

## Repository structure

```
CVApplicate/
├── fetch-postings.py           unchanged entry point; still Phase 1 only
├── score-postings.sh           new; thin wrapper invoking `claude -p` headlessly
├── postings.local.yaml         Phase 1 store; gains `description` and `scored` fields
├── matches.local.yaml          new; scored results — gitignored, personal data
├── job_fetcher/
│   ├── ats.py                  extended: captures JD description text
│   └── store.py                extended: `scored: bool` flag alongside `notified`
├── plugins/cvapplicate/skills/
│   └── cv-score-postings/
│       └── SKILL.md            new; the scoring procedure, Claude-executed
└── launchd/
    └── com.cvapplicate.score-postings.plist.example   new; separate launchd entry
```

`matches.local.yaml` follows the same gitignore convention as `postings.local.yaml` —
personal scoring data never gets committed to this template repo.

## Components

### 1. `ats.py` — JD description capture (extended)

Both adapters currently normalize postings without any description text. This phase adds
one field, `description` (plain text, HTML tags stripped using the stdlib `html.parser`
— no new dependency), truncated to 6000 characters to keep prompt size bounded:

- **Greenhouse:** `fetch_greenhouse` requests
  `https://boards-api.greenhouse.io/v1/boards/<slug>/jobs?content=true`, which includes
  each job's `content` field (HTML job description). `normalize_greenhouse` strips tags
  and stores the result as `description`.
- **Lever:** `https://api.lever.co/v0/postings/<slug>?mode=json` already returns
  `descriptionPlain` per posting. `normalize_lever` stores it directly as `description`
  (falls back to stripped `description` HTML if `descriptionPlain` is absent).

If a posting has no usable description after this (empty string, or the field is
missing), it's stored with `description: null` — handled explicitly at scoring time
rather than scored on an empty string.

### 2. `store.py` — `scored` flag (extended)

New postings gain `scored: false` at merge time, the same way they gain
`notified: false` today (`merge_new_postings` sets both). A new `mark_scored(postings,
ids)` function mirrors the existing `mark_notified`. The two flags are independent:
whether a posting was emailed and whether it's been scored are unrelated facts about it.

### 3. `cv-score-postings` — new skill

A markdown-instruction skill (same style as `cv-application-skills`), not a script,
because JD-fit scoring is a judgment call, not a formula. Procedure:

1. Read `postings.local.yaml`; select postings where `scored: false`.
2. If none, exit — nothing to do tonight.
3. Discover industry branches with `git for-each-ref --format='%(refname:short)'
   refs/heads/` (excludes `main`, which holds shared data, not a CV).
4. For each unscored posting with a non-null `description`:
   - For each industry branch: read that branch's `master-data.md` and `cv.tex` via
     `git show <branch>:master-data.md` / `git show <branch>:cv.tex` (working tree is
     never checked out).
   - Apply the JD Fit rubric from `cv-review` step 5 (keyword match 40%, experience
     relevance 40%, seniority fit 20%) using the posting's `description` as the JD text.
   - Record that branch's `total` plus the three sub-scores.
   - Pick the highest-scoring branch as `best_branch`, write a one-line rationale for why
     it's the best fit (or why every branch scored low, if none fit well).
5. For a posting with `description: null`, skip scoring and record it in
   `matches.local.yaml` with `skipped: "no description"` instead of guessing.
6. Append all results for this run to `matches.local.yaml` (create the file if absent).
7. Call `mark_scored` for every posting processed this run (scored or skipped) and save
   `postings.local.yaml`.
8. Never edit `cv.tex`, `master-data.md`, `claims-guardrails.md`, or run any `git`
   command other than `show`/`for-each-ref` (both read-only, no checkout, no commit).

### 4. `score-postings.sh` — launchd entry point

A thin shell wrapper, mirroring how `fetch-postings.py` is invoked directly today:

```bash
#!/bin/bash
cd "$(dirname "$0")"
claude -p "Run cv-score-postings" --allowedTools "..."
```

Runs unattended, so its tool permissions must be scoped tightly to exactly what the skill
needs — read-only git inspection (`git show`, `git for-each-ref`), reading the postings
store, writing only `matches.local.yaml` and the `scored` field in `postings.local.yaml`.
It must not be able to edit `cv.tex` or `master-data.md`, run `git
commit`/`checkout`/`push`, or touch any file outside this narrow set, regardless of what
a given night's run decides to do. The exact `--allowedTools`/permission-mode flag syntax
is a CLI detail to confirm against `claude --help` during implementation, not a design
decision — the requirement is the allowlist's scope, not its exact spelling.

A separate `launchd/com.cvapplicate.score-postings.plist.example` schedules this
independently of `fetch-postings.py`'s plist, at a later time in the morning (e.g.
8:30am, thirty minutes after the 8:00am fetch) so scoring has fresh postings to work from
without the two scripts racing each other. Keeping them as two separate launchd jobs
(rather than chaining inside one script) keeps each one independently rerunnable and
debuggable via its own log file, matching the existing `fetch-postings.log` convention.

## Data flow summary

1. 8:00am: `fetch-postings.py` runs (unchanged trigger), fetches postings, now including
   `description` text, and merges them into `postings.local.yaml` with both `notified:
   false` and `scored: false`.
2. 8:30am: `score-postings.sh` runs, invoking headless Claude with the `cv-score-postings`
   skill.
3. The skill reads unscored postings, reads each industry branch's CV data via `git
   show`, scores each posting against each branch, and appends results to
   `matches.local.yaml`.
4. Scored (or explicitly skipped) postings are marked `scored: true` in
   `postings.local.yaml`.
5. The user reads `matches.local.yaml` whenever they choose, sorts/filters as they like,
   and runs `cv-review` by hand on postings worth pursuing.

## Error handling

- **`claude` CLI not found on PATH** (same class of failure as the documented
  `python3`/launchd PATH mismatch for `fetch-postings.py`): the launchd job fails, logged
  to `score-postings.log`; `fetch-postings.py`'s own run is unaffected since they're
  separate jobs.
- **A posting has no description** (Greenhouse/Lever returned nothing usable): recorded
  in `matches.local.yaml` as `skipped: "no description"`, marked `scored: true` so it
  isn't retried forever, not scored on empty/guessed content.
- **A branch is missing `cv.tex` or `master-data.md`** (e.g. a branch mid-scaffold via
  `cv-new-industry`): that branch is skipped for that posting only, noted in the
  posting's result; scoring continues against the remaining branches.
- **Every branch scores low for a posting**: still recorded normally with the highest
  (even if low) score as `best_branch` — the user decides what "low" means when reading
  the file; the skill doesn't suppress or hide low-scoring entries.
- **Headless Claude run is interrupted mid-batch** (killed, crashes): postings already
  appended to `matches.local.yaml` and marked `scored: true` stay that way; postings not
  yet reached remain `scored: false` and are picked up by the next night's run. No
  partial/half-written posting entries, since each posting's result is only marked
  `scored: true` after its `matches.local.yaml` entry is written.

## Testing

- Unit tests for `ats.py`'s description capture and HTML-stripping, extending the
  existing fixture-based `test_ats.py` pattern (recorded sample responses, no live
  network calls).
- Unit tests for `store.py`'s `mark_scored`, mirroring the existing `mark_notified` tests.
- The `cv-score-postings` skill's actual scoring judgment isn't unit-testable — same as
  `cv-review` and `cv-application-skills` today, it's verified by a manual run against
  real fixture postings and a fixture branch, checking the rubric is applied consistently
  with `cv-review`'s own scoring on the same JD.

## Key decisions log

- **Headless Claude for scoring, not a deterministic script** — the JD Fit rubric is
  judgment-based (the same rubric `cv-review` already uses interactively); a keyword-
  overlap script would be a materially worse approximation of it, not a faster version of
  the same thing.
- **Score against every branch, no pre-filtering** — branch count is small and
  user-controlled; guessing relevance from a posting's title risks missing genuine
  cross-branch fits (e.g. a "Data Engineer" posting that actually fits `swe` better than
  `data-science`).
- **Read branch content via `git show`, never `git checkout`** — an unattended nightly
  job must not depend on, or disturb, whatever the user has checked out or has
  uncommitted in their working tree at 8:30am.
- **Local file only, no email** — matches Phase 1's non-goal deferral of push
  notifications, extended to this phase's own output; revisit if the user wants a
  proactive nudge later.
- **Score once, like the existing `notified` flag** — avoids re-scoring the same posting
  every night indefinitely; re-scoring after a `master-data.md` change is a manual,
  explicit action, not automatic, to avoid silently invalidating a user's own read of
  `matches.local.yaml`.
- **Separate launchd job from `fetch-postings.py`, not chained in one script** — keeps
  each script independently rerunnable, testable, and debuggable via its own log, and
  avoids a scoring failure ever blocking the fetch step (or vice versa).
- **Tightly scoped `--allowedTools` on the headless invocation** — this runs unattended
  with nobody present to approve a permission prompt; the allowlist is the only thing
  standing between "reads data and writes two files" and a broader unintended action, so
  it's scoped to exactly the skill's declared file/command set.
