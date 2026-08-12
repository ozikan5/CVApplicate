# CV Review & Version Control Pipeline — Design

**Date:** 2026-08-12
**Status:** Approved for planning

## Purpose

Turn an ad-hoc "paste CV + JD into Claude, get a score, fix weak points, submit" workflow
into a repeatable Claude Code skill set, backed by a git-based version control system for
tracking CV variants across industries and a log of every application submitted.

The result is a **generic, publishable template repository** — not a personal CV repo.
It contains no personal data. A user (the author, or anyone else) forks it and fills in
their own content in their own fork; that fork is where real version control of a
person's actual CVs happens.

## Non-goals

- This repo does not contain anyone's real CV content, real application history, or a
  real Overleaf remote configuration. All of that belongs in a fork.
- No hard gate blocking submission based on score. Scoring is informational; the human
  decides when a CV is ready.
- No automatic regeneration of LaTeX from `master-data.md`. The data file is a reference
  source, not a template-rendering pipeline.

## Repository structure

```
CVApplicate/                          (generic, publishable template repo)
├── cv.tex                            placeholder LaTeX CV ("Jane Doe" example content)
├── master-data.md                    example structure: Education/Experience/Projects/Skills
├── applications/
│   └── log.yaml                      schema + one example entry, not real data
├── .claude/skills/
│   ├── cv-review/SKILL.md
│   ├── cv-new-industry/SKILL.md
│   ├── cv-log-outcome/SKILL.md
│   └── cv-sanity-check/SKILL.md
└── README.md                         fork-and-fill-in instructions, Overleaf remote setup

Branches:
main                    ← placeholder base CV (most general-purpose version)
├── swe                 ← example industry branch
├── ai-ml
├── quant-trading
└── data-science
```

### Branch/file ownership rule

`master-data.md` and `applications/log.yaml` are authoritative on `main` only — a single,
unified experience bank and application history regardless of how many industry branches
exist. `cv.tex` diverges per industry branch.

When a skill running on an industry branch needs to update the log or master data, it:
1. Commits the `cv.tex` change on the current industry branch.
2. Switches to `main`.
3. Commits the log/master-data change there.
4. Switches back to the industry branch.

This keeps CV content properly branched per industry while keeping application history
and the experience bank as one continuous timeline.

## The four skills

### 1. `cv-review` — score, fix, recheck

**Input:** industry (target branch), job description (pasted text or a URL), company/role name.

**Steps:**
1. Checkout the target industry branch.
2. Read `cv.tex` + `master-data.md`.
3. Score **Base Quality** /100 (see Scoring Rubric below).
4. Score **JD Fit** /100 against the specific posting.
5. Identify the combined worst 3 weaknesses across both layers.
6. Edit `cv.tex` directly to fix them; update `master-data.md` with any improved phrasing.
7. If a local LaTeX toolchain is available, compile-check the edit:
   - Pass → proceed.
   - Fail → revert the edit, report the compile error, do not commit.
8. Commit the `cv.tex` change on the industry branch.
9. Re-score both layers (final check) and report before/after. No hard gate — reporting only.
10. Switch to `main`, append an entry to `applications/log.yaml` (+ any `master-data.md`
    change), commit, switch back to the industry branch.

**Output:** Base score, JD Fit score, the 3 weaknesses fixed and why, final re-scored numbers.

### 2. `cv-new-industry` — create an industry variant

**Input:** new industry name.

**Steps:** checkout `main` → create branch `<industry>` → first-pass adapt `cv.tex` for
that industry using `master-data.md` as source material → commit.

**Output:** branch created, summary of what was emphasized/reordered.

### 3. `cv-log-outcome` — record an application result

**Input:** company/role identifier (defaults to most recent if omitted), outcome
(`interview` | `rejected` | `offer` | `no_response`).

**Steps:** checkout `main` → find the matching entry in `applications/log.yaml` by
company+role (or `id`) → if ambiguous (multiple matches), ask the user to disambiguate →
update `outcome` + `outcome_date` → commit.

**Output:** confirmation of what was updated.

### 4. `cv-sanity-check` — AI-writing smell check

**Input:** none required; defaults to the current branch's `cv.tex`.

**Steps:** scan for buzzword overuse, repetitive sentence/verb openings, em-dash overuse,
generic filler phrases, unnatural cadence, inconsistent tense, vague/unverifiable claims,
unnaturally uniform bullet lengths → auto-fix `cv.tex` → compile-check (same rule as
`cv-review` step 7) → commit.

**Output:** what was found and changed, so nothing is silently altered without the user
seeing why.

## Scoring rubric

### Base Quality /100 (generic to any job)

| Category | Weight | What it measures |
|---|---|---|
| Impact | 40% | Strong action verbs, specificity, quantified outcomes |
| Competencies | 35% | Skills/qualifications vs. general employer expectations for the field |
| Presentation | 25% | Bullet formatting: active voice, no filler words, appropriate length, no over-usage of any single word/phrase |

Score bands (adapted from VMock's public methodology): 🔴 0–32 Red · 🟡 33–85 Yellow · 🟢 86–100 Green.

### JD Fit /100 (specific to one posting)

| Category | Weight | What it measures |
|---|---|---|
| Required skills/keyword match | 40% | Does the CV surface the specific skills/tools the JD asks for? |
| Experience relevance | 40% | Do past roles/projects map to the JD's actual responsibilities? |
| Seniority/level fit | 20% | Does the CV read as the right level for this posting (intern/new-grad/experienced)? |

Weights are a starting point, adjustable over time — they are not derived from any
official VMock weighting (VMock does not publish exact weights).

### Weak-point selection

`cv-review` pools weaknesses from both Base Quality and JD Fit and reports the single
worst 3, regardless of which layer they came from.

## Application log schema (`applications/log.yaml`)

```yaml
- id: example-corp-swe-2026-08
  company: "Example Corp"
  role: "Software Engineer Intern"
  industry_branch: swe
  date_applied: 2026-08-12
  jd_source: pasted        # or "url"
  jd_url: null
  jd_summary: "Short summary of key requirements"
  cv_commit: <git sha of the cv.tex used>
  base_quality_score:
    total: 82
    impact: 78
    competencies: 85
    presentation: 80
  jd_fit_score:
    total: 74
    keyword_match: 70
    experience_relevance: 80
    seniority_fit: 70
  weak_points_fixed:
    - "Bullet 3 lacked quantified outcome"
  outcome: pending          # pending | interview | rejected | offer | no_response
  outcome_date: null
```

`cv_commit` ties an application to the exact CV version used, so `git show <sha>:cv.tex`
recovers precisely what was submitted even after the branch has since moved on.

## Data flow summary

1. User forks the template, replaces placeholder `cv.tex`/`master-data.md` with real
   content, adds their Overleaf project as a git remote (`git.overleaf.com`).
2. User runs `cv-new-industry` per industry they apply to (SWE, AI/ML, etc.).
3. Per application: user runs `cv-review` with the JD and target industry branch. The
   skill scores, fixes, re-scores, commits, and logs.
4. Occasionally: user runs `cv-sanity-check` to catch AI-writing smells, independent of
   whether `cv-review` was just run (e.g. after manual Overleaf edits).
5. After hearing back: user runs `cv-log-outcome` to close the loop on that application.
6. User pushes/pulls between their fork and their Overleaf remote as needed to keep the
   "live editing" view in Overleaf in sync with the git history.

## Error handling

- **JD URL fetch fails** → fall back to asking the user to paste the text.
- **Dirty working tree when a skill needs to switch branches** → stop and report; never
  stash or discard silently.
- **LaTeX compile fails after an edit** (toolchain available) → revert the edit, report
  the error, do not commit.
- **No local LaTeX toolchain found** → skip the compile check, note in the report that
  compilation was not verified.
- **Ambiguous match in `cv-log-outcome`** → ask the user to disambiguate by role or id.
- **Overleaf git remote conflicts** → surfaced as a normal git merge conflict; the skill
  never auto-resolves or picks a side.

## Validating the template

Since the four skills are Claude Code Skill instructions (not application code),
validation is end-to-end and manual:

- Run `cv-new-industry` to create a scratch branch.
- Run `cv-review` with a sample pasted JD against the placeholder `cv.tex`; confirm the
  score report format and that `applications/log.yaml` gets a correctly-committed entry
  on `main`.
- Confirm branch-switching returns to the correct branch afterward.
- Run `cv-sanity-check` against a test fixture with an intentionally-planted AI-smell
  sentence and confirm it's caught and fixed.
- Clean up scratch branches/log entries before considering the template done.

## Key decisions log

- **Full automation, in-repo** — skills edit `.tex` directly rather than only suggesting
  changes; user does a final human review before submitting.
- **Git branches per industry**, not folders or separate repos — enables sharing
  improvements from `main` via merge/rebase.
- **Application tracking is in scope** — every `cv-review` run logs a structured entry
  tied to a git commit.
- **Overleaf stays the live-editing surface**, synced via Overleaf's native git remote,
  not replaced by this repo.
- **`master-data.md` is a reference source, hand-curated `.tex` is authoritative** — no
  auto-generation pipeline from data to LaTeX.
- **Scoring is two independent layers** (Base Quality, generic; JD Fit, per-posting), not
  one blended number — Base Quality should hold up regardless of which job is being
  targeted.
- **This repository is a generic template**, not personal data. Personal use happens in a
  fork. This resolves the tension between "shareable with others" and "real git version
  control of my own CVs" without gitignoring tracked content.
