---
name: cv-score-postings
description: Score every not-yet-scored posting in postings.local.yaml against each industry branch's CV data, using the same JD Fit rubric cv-review applies. Read-only — never edits cv.tex or master-data.md, never commits, never checks out a branch. Normally run nightly, unattended, by score-postings.sh; can also be invoked by hand to score on demand.
---

# CV Score Postings

Scores fetched job postings against your CV data across every industry branch you
maintain, so postings worth pursuing surface on their own. This is scoring only — it
never edits `cv.tex` or `master-data.md`, never runs `cv-review`'s fix-and-commit flow,
and never touches git state beyond read-only inspection.

## When to use

Normally invoked unattended by `score-postings.sh` on a nightly schedule, after
`fetch-postings.py` has run. Can also be run by hand ("score my new postings") to score
on demand instead of waiting for the next scheduled run.

## Inputs needed

None from the user — this reads `postings.local.yaml` directly and discovers industry
branches from git. If `postings.local.yaml` doesn't exist or has no unscored postings,
say so and stop; don't ask the user anything.

## Procedure

1. Read `postings.local.yaml`. Select postings where `scored` is `false`. If there are
   none, report that and stop.
2. Discover industry branches: `git for-each-ref --format='%(refname:short)'
   refs/heads/ refs/remotes/origin/`, then strip any `origin/` prefix and de-duplicate
   by the resulting short name. Exclude `main` (which holds shared data, not a CV),
   `origin/HEAD`, and any worktree scratch branches. Reading the remote-tracking refs
   as well is load-bearing: in a fresh clone the industry branches exist *only* under
   `refs/remotes/origin/`, and looking at `refs/heads/` alone reports "no industry
   branches" and silently scores nothing. If no industry branches exist, stop and say
   so.
3. For each unscored posting:
   - If `description` is null or empty, don't score it. Record it in
     `matches.local.yaml` with `skipped: "no description"` and move on — never guess a
     score from the title alone.
   - Otherwise, for each industry branch:
     - Read the shared experience bank once from `main` via `git show
       main:master-data.md`, and that branch's CV via `git show <branch>:cv.tex`.
       `master-data.md` is authoritative on `main` only — the per-branch copies drift
       behind it, and scoring against a stale copy hides experience you actually have.
       Only `cv.tex` is read per branch. Never run `git checkout` — the working tree's
       currently checked-out branch and any uncommitted changes in it must be left
       exactly as found.
     - If `cv.tex` is missing on that branch (e.g. a branch mid-scaffold), skip that
       branch for this posting and note it; continue with the remaining branches. If
       `main` has no `master-data.md`, stop — there is no experience bank to score
       against.
     - Score **JD Fit /100** using the same rubric `cv-review` uses:
       - Required skills/keyword match (40%): does the CV surface the specific
         skills/tools the posting's `description` asks for?
       - Experience relevance (40%): do past roles/projects map to the posting's actual
         responsibilities?
       - Seniority/level fit (20%): does the CV read as the right level for this
         posting?
       - Compute `total` as the weighted sum of the three subscores.
   - Pick the branch with the highest `total` as `best_branch`. Write a one-line
     rationale for why it's the best fit — or, if every branch scored low, say so
     plainly rather than praising a weak match.
4. Append this run's results to `matches.local.yaml` (create it if it doesn't exist yet;
   never overwrite prior runs' entries). One entry per posting processed this run:
   ```yaml
   - posting_id: examplecorp-12345
     company: "Example Corp"
     title: "Software Engineer Intern"
     url: "https://boards.greenhouse.io/examplecorp/jobs/12345"
     scored_date: 2026-08-31
     best_branch: swe
     jd_fit_score: {total: 82, keyword_match: 85, experience_relevance: 80, seniority_fit: 80}
     rationale: "Strong Python/REST match; seniority slightly senior for current level."
     all_branches: {swe: 82, ai-ml: 61, data-science: 55, quant-trading: 40}
   ```
   A skipped posting gets a shorter entry: `posting_id`, `company`, `title`, `url`,
   `scored_date`, and `skipped: "no description"` — no score fields.
5. Mark every posting processed this run (scored or skipped) as `scored: true` in
   `postings.local.yaml` and save it, so nothing gets reprocessed on the next run.
6. Never edit `cv.tex`, `master-data.md`, or `claims-guardrails.md`. Never run `git
   commit`, `git checkout`, or `git push`. The only git commands this skill runs are
   `git show` and `git for-each-ref`, both read-only.

## Output

Report to the user: how many postings were scored, how many skipped for missing
descriptions, and the single highest-scoring match from this run (if any) with its
`best_branch` and `total`. Full detail lives in `matches.local.yaml` — point the user
there rather than repeating every entry in chat.

## Error handling

- `postings.local.yaml` missing or has no unscored postings → report that, stop.
- No industry branches exist → report that, stop.
- A branch missing `cv.tex` → skip that branch for the affected posting(s), note it,
  continue with the remaining branches.
- `main` missing `master-data.md` → stop and say so; there is nothing to score against.
- A posting with no `description` → record as `skipped: "no description"`, mark
  `scored: true`, never scored on the title alone.
