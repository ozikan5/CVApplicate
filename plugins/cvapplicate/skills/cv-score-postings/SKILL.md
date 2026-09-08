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
3. Load the eligibility profile and apply the gate to each unscored posting **before**
   scoring it. If `profile.local.yaml` does not exist, skip this step entirely for
   every posting and note in the report that no eligibility profile was found — never
   invent one.

   Load the profile once (reuse the values for every posting this run):
   ```bash
   python3 -c "
   from job_fetcher.profile import load_profile
   import json
   print(json.dumps(load_profile('profile.local.yaml')))
   "
   ```

   Reject a posting, recording every applicable reason, when:
   - the JD states a minimum years-of-experience above
     `max_years_experience_required`. This is a judgment call, not pattern-matching:
     decide whether the figure is a *requirement* rather than incidental prose —
     "4+ years of experience" in a requirements list counts, the same words inside a
     company blurb ("our engineers average 4+ years of experience") do not.
   - `seeking` is `internship` and the posting is plainly a full-time
     non-internship role — also a judgment call.
   - `locations` is non-empty and no stated location matches. Check this with
     `location_matches` rather than eyeballing the text:
     ```bash
     python3 -c "
     from job_fetcher.profile import location_matches
     print(location_matches('<posting location text>', <profile['locations']>))
     "
     ```
   - the work-authorization check returns `disqualified`. Write the posting's
     `description` to a temp file with the **Write tool** (a Bash heredoc cannot
     reliably carry arbitrary JD text), then run `authorization_verdict` on it. Run
     the helper rather than judging authorization language yourself — it encodes
     which phrasings disqualify and, critically, which do not:
     ```bash
     python3 -c "
     from job_fetcher.profile import authorization_verdict
     jd_text = open('/tmp/jd.txt', encoding='utf-8').read()
     verdict, reason = authorization_verdict(jd_text, '<profile work_authorization>')
     print(verdict, reason or '')
     "
     ```
     If it returns `ambiguous`, you adjudicate: read the quoted sentence in `reason`
     and decide, defaulting to eligible.

   **When a rule is ambiguous, the posting stays eligible** and the ambiguity goes
   into the rationale. A gate that guesses is worse than no gate: a wrongly rejected
   posting is invisible to the user, while a wrongly accepted one merely costs one
   score.

   Record an ineligible posting in `matches.local.yaml` (per step 5's format) as:
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
   No score fields, and do not tailor it. Skip step 4's scoring for this posting —
   go straight to steps 5-6 to record and mark it processed. A posting that passes
   the gate (or every posting, if the gate was skipped) proceeds to step 4 normally.
4. For each posting that passed the gate in step 3 (or every unscored posting, if
   step 3 was skipped because `profile.local.yaml` is absent):
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
5. Append this run's results to `matches.local.yaml` (create it if it doesn't exist yet;
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
   `scored_date`, and `skipped: "no description"` — no score fields. A posting
   rejected by step 3's gate gets the `eligible: false` / `reasons` entry shown
   there — no score fields either.
6. Mark every posting processed this run (scored, skipped, or rejected by the gate)
   as `scored: true` in `postings.local.yaml` and save it, so nothing gets
   reprocessed on the next run.
7. Never edit `cv.tex`, `master-data.md`, or `claims-guardrails.md`. Never run `git
   commit`, `git checkout`, or `git push`. The only git commands this skill runs are
   `git show` and `git for-each-ref`, both read-only.

## Output

Report to the user: how many postings were scored, how many skipped for missing
descriptions, how many rejected by the eligibility gate and why (list each rejected
posting's title with its `reasons`, not just a count — a mass rejection should be
visible immediately rather than looking like a quiet night), and the single
highest-scoring match from this run (if any) with its `best_branch` and `total`. If
`profile.local.yaml` was absent, say so explicitly so the user knows the gate did not
run. Full detail lives in `matches.local.yaml` — point the user there rather than
repeating every entry in chat.

## Error handling

- `postings.local.yaml` missing or has no unscored postings → report that, stop.
- No industry branches exist → report that, stop.
- A branch missing `cv.tex` → skip that branch for the affected posting(s), note it,
  continue with the remaining branches.
- `main` missing `master-data.md` → stop and say so; there is nothing to score against.
- A posting with no `description` → record as `skipped: "no description"`, mark
  `scored: true`, never scored on the title alone.
- `profile.local.yaml` missing → skip the eligibility gate for every posting this run
  and say so in the report; never invent a profile.
