---
name: cv-review
description: Score a CV against a specific job description, fix the weakest points, and log the application. Use when the user wants to check their CV's fit for a job posting before applying, or asks to "review my CV against this JD".
---

# CV Review

Scores a CV two ways — general quality and fit to a specific job — fixes the three
weakest points found across both scores, re-checks, and logs the application.

## When to use

The user gives you a job description (pasted text or a URL) and wants their CV
evaluated and improved before they submit it, or explicitly invokes this skill.

## Inputs needed

Ask for anything missing before starting:
1. **Industry/branch** — which industry-specific CV to review (e.g. `swe`, `ai-ml`).
   If unclear, ask; do not guess.
2. **Job description** — pasted text, or a URL to fetch. If a URL is given, try
   fetching it first; if the fetch fails or returns unusable content, ask the user to
   paste the text instead.
3. **Company and role name** — for the application log entry.

## Procedure

1. Run `git status` to confirm the working tree is clean. If not, stop and tell the
   user what's uncommitted — do not proceed until it's clean.
2. Run `git checkout <industry-branch>`.
3. Read `cv.tex` and `master-data.md` in full.
4. **Score Base Quality /100** using this rubric:
   - Impact (40%): strong action verbs, specificity, quantified outcomes
   - Competencies (35%): skills/qualifications vs. general expectations for the field
   - Presentation (25%): active voice, no filler words, appropriate bullet length, no
     over-usage of any single word/phrase
   - Compute `total` as the weighted sum of the three category scores (each 0-100).
5. **Score JD Fit /100** using this rubric:
   - Required skills/keyword match (40%): does the CV surface the specific
     skills/tools the JD asks for?
   - Experience relevance (40%): do past roles/projects map to the JD's actual
     responsibilities?
   - Seniority/level fit (20%): does the CV read as the right level for this posting?
   - Compute `total` as the weighted sum.
6. Pool weaknesses from both layers and pick the worst 3 overall (not 3 from each).
7. Edit `cv.tex` directly to fix those 3 weaknesses. If a fix rephrases an experience
   bullet, note the improved wording — you'll write it into `master-data.md` at step
   12. Do **not** edit `master-data.md` on this branch: it is authoritative on `main`
   only, so editing it here would fragment it across industry branches.
8. Compile-check the edit using whichever of these is found first on the system:
   `latexmk`, then `pdflatex`, then `tectonic` (check with e.g. `which latexmk`).
   - If none are found, skip this step and note in your final report that
     compilation was not verified.
   - If found, compile `cv.tex`. On failure, run `git checkout -- cv.tex` to revert
     the edit, report the compile error to the user, and stop — do not commit.
9. Commit `cv.tex` on the industry branch (this file only — see step 7):
   `git add cv.tex && git commit -m "Review: <company> <role>"`
   Record the resulting commit SHA (`git rev-parse HEAD`) for step 12's `cv_commit`.
10. Re-score both layers against the fixed `cv.tex` (repeat steps 4-6). This is the
    final check — report the before/after scores. Do not block on any threshold; the
    user decides if it's ready.
11. Switch to `main`: `git checkout main`.
12. On `main`, do both of these:
    a. Apply the improved bullet wording noted in step 7 to the matching entries in
       `master-data.md`, so future CVs inherit the improvement.
    b. Append an entry to `applications/log.yaml` with this shape:
    ```yaml
    - id: <company-slug>-<industry>-<yyyy-mm>
      company: "<company>"
      role: "<role>"
      industry_branch: <industry>
      date_applied: <today, YYYY-MM-DD>
      jd_source: pasted        # or url
      jd_url: <url or null>
      jd_summary: "<1-2 sentence AI-generated summary of the JD's key requirements>"
      cv_commit: <sha from step 9>
      base_quality_score:
        total: <int>
        impact: <int>
        competencies: <int>
        presentation: <int>
      jd_fit_score:
        total: <int>
        keyword_match: <int>
        experience_relevance: <int>
        seniority_fit: <int>
      weak_points_fixed:
        - "<weakness 1>"
        - "<weakness 2>"
        - "<weakness 3>"
      outcome: pending
      outcome_date: null
    ```
13. Commit both on `main`:
    `git add applications/log.yaml master-data.md && git commit -m "Log application: <company> <role>"`
14. Switch back to the industry branch: `git checkout <industry-branch>`.
15. Report to the user: initial Base/JD Fit scores, the 3 weaknesses fixed and why,
    and the final re-scored numbers.

## Error handling

- Dirty working tree at step 1 → stop, do not switch branches.
- JD URL unreachable → ask the user to paste the text.
- Compile failure at step 8 → revert, report, stop before committing.
- `master-data.md` showing up as modified on an industry branch → you edited it in the
  wrong place. Revert it there (`git checkout -- master-data.md`) and redo the edit on
  `main` at step 12.
