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

Read every bullet in `cv.tex` and flag:
- **Buzzword overuse** — words like "spearheaded", "leveraged", "orchestrated",
  "utilized" appearing more than once or twice across the whole document
- **Repetitive sentence/verb openings** — multiple bullets starting with the same
  word or grammatical construction
- **Em-dash overuse** — more em dashes than a human resume would typically use
- **Generic filler phrases** — "responsible for", "worked on", "helped with" without
  a concrete outcome attached
- **Unnatural cadence** — bullets that all have near-identical sentence structure
  and length, reading as templated rather than varied
- **Inconsistent tense** — mixing past and present tense for equivalent
  (e.g. all-past-role) entries
- **Vague or unverifiable claims** — impact statements with no metric, scope, or
  concrete detail behind them
- **Unnaturally uniform bullet lengths** — every bullet being suspiciously close to
  the same character count

## Procedure

1. Run `git status` to confirm the working tree is clean. If not, stop and tell the
   user what's uncommitted.
2. Read `cv.tex` in full.
3. Identify every instance of the patterns above, with the specific bullet/line
   affected.
4. Edit `cv.tex` to fix each one — vary word choice, add concrete specifics where a
   claim is vague, fix tense consistency, vary sentence structure.
5. Compile-check the edit using whichever of these is found first on the system:
   `latexmk`, then `pdflatex`, then `tectonic`.
   - If none are found, skip this step and note in your final report that
     compilation was not verified.
   - If found, compile `cv.tex`. On failure, run `git checkout -- cv.tex` to revert,
     report the compile error, and stop — do not commit.
6. Commit: `git add cv.tex && git commit -m "Sanity check: fix AI-writing smells"`.
7. Report to the user exactly what was found and what was changed, bullet by bullet,
   so nothing is altered without them seeing why.

## Error handling

- Dirty working tree at step 1 → stop, do not edit.
- Compile failure at step 5 → revert, report, stop before committing.
- Nothing found → report that the CV reads fine, make no changes, no commit.
