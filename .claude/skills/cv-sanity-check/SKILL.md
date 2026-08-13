---
name: cv-sanity-check
description: Scan a CV for AI-writing smells (buzzword overuse, repetitive phrasing, unnatural cadence, vague claims) and fix them. Use when the user wants to make sure their CV doesn't read as AI-generated, independent of a specific job review.
---

# CV Sanity Check

Scans the current branch's `cv.tex` for patterns that read as AI-generated writing,
and fixes them.

## Inputs needed

None required. Defaults to the currently checked-out branch's `cv.tex`. If the user
names a specific industry branch, checkout that branch first (after confirming the
working tree is clean).

## What to look for

Detection runs in two passes: a mechanical one you must not skip, then your own reading.

### Pass 1 — mechanical (run the script)

`check-cv-text.py` counts what is countable, so nothing slips past judgment alone:

```bash
python3 check-cv-text.py cv.tex
```

It reports, with line numbers:
- **Buzzwords** — any occurrence of ~50 flagged terms ("spearheaded", "leveraged",
  "cutting-edge", "robust", "delve", …)
- **Filler phrases** — any occurrence of ~35 padding phrases ("responsible for",
  "worked on", "a variety of", "successfully", "utilized", …)
- **Repeated bullet openers** — any word opening more than one bullet
- **Overused words** — any content word appearing in more than three bullets
- **Em-dash overuse** — more than three across the document
- **Uniform bullet length** — length variation under 15%, which reads as templated
- **Unquantified bullets** — bullets containing no figure at all

Exit code is 0 when clean, 1 when it has findings. Findings are **signals, not
verdicts**: a repeated domain term ("search", "pipeline") may be unavoidable and
correct. Judge each one — but never ignore the list wholesale.

### Pass 2 — your reading (the script cannot see these)

- **Inconsistent tense** — past vs. present mixed across equivalent entries
- **Unnatural cadence** — every bullet following the same grammatical skeleton even
  when lengths differ
- **Vague claims** — statements with a number attached that still say nothing concrete
- **Guardrail violations** — anything conflicting with `claims-guardrails.md`

## Procedure

1. Run `git status` to confirm the working tree is clean. If not, stop and tell the
   user what's uncommitted.
2. Read `cv.tex`, plus `claims-guardrails.md` and `master-data.md` if they exist.
3. Run `python3 check-cv-text.py cv.tex` (Pass 1) and read every finding. Then do your
   own Pass 2 reading for what the script cannot detect. Decide, per finding, whether
   it's a real problem or an unavoidable domain term — and say which in your report.
   Also flag any bullet that violates `claims-guardrails.md` — an overstated metric
   scope, an ownership verb stronger than the work supports, or something described as
   live that isn't.
4. Edit `cv.tex` to fix each one — vary word choice, add concrete specifics where a
   claim is vague, fix tense consistency, vary sentence structure.
   **Fixing "vague" must never mean inflating.** Pull real specifics from
   `master-data.md`; if none exist, leave the claim modest and say so in the report.
   Never resolve vagueness by inventing a number.
5. Compile-check the edit using whichever of these is found first on the system:
   `latexmk`, then `pdflatex`, then `tectonic`.
   - If none are found, skip this step and note in your final report that
     compilation was not verified.
   - If found, compile `cv.tex`. On failure, run `git checkout -- cv.tex` to revert,
     report the compile error, and stop — do not commit.
6. Commit: `git add cv.tex && git commit -m "Sanity check: fix AI-writing smells"`.
7. Re-run `python3 check-cv-text.py cv.tex` to confirm the findings you intended to fix
   are gone and that your edits introduced no new ones.
8. Report to the user exactly what was found and what was changed, bullet by bullet, so
   nothing is altered without them seeing why. Separate the findings you fixed from the
   ones you judged acceptable, and say why for each of the latter.

## Error handling

- Dirty working tree at step 1 → stop, do not edit.
- `check-cv-text.py` missing or erroring → say so explicitly in the report, then do
  Pass 2 by hand. Never silently skip Pass 1.
- Compile failure at step 5 → revert, report, stop before committing.
- Nothing found by either pass → report that the CV reads fine, make no changes, no
  commit.
