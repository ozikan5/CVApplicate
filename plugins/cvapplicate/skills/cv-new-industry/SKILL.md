---
name: cv-new-industry
description: Create a new industry-specific CV branch from main, with a first-pass adaptation using master-data.md. Use when the user wants to start targeting a new field (e.g. "I want to start applying to consulting roles").
---

# CV New Industry

Branches a new industry-specific CV variant off `main` and does a first-pass
adaptation of its content.

## Inputs needed

**Industry name** — a short, lowercase, hyphenated slug (e.g. `consulting`,
`quant-trading`). If the user gives a longer phrase, slugify it and confirm with them
before proceeding.

## Procedure

1. Run `git status` to confirm the working tree is clean. If not, stop and tell the
   user what's uncommitted.
2. Run `git checkout main`.
3. Check the branch doesn't already exist: `git branch --list <industry>`. If it
   exists, tell the user and stop rather than overwriting it.
4. Create and switch to the branch: `git checkout -b <industry>`.
5. Read `master-data.md` in full and the current `cv.tex`.
6. Adapt `cv.tex` for `<industry>`: select, reorder, and reword bullets from
   `master-data.md` to emphasize what's most relevant to that field. Keep the same
   LaTeX structure/formatting as the base template — only the content selection and
   ordering changes.
7. Compile-check the edit using whichever of these is found first on the system:
   `latexmk`, then `pdflatex`, then `tectonic` (check with e.g. `which latexmk`).
   - If none are found, skip this step and steps 9-10 below, and note in the final
     report that compilation was not verified, so no PDF was produced.
   - If found, compile `cv.tex`. On failure, fix the LaTeX error before continuing —
     do not commit broken LaTeX.
8. Commit: `git add cv.tex && git commit -m "Adapt CV for <industry>"`.
9. Rename the compiled PDF to `First_Last_CV_Industry.pdf` before delivering it —
    First/Last from the name in `cv.tex`'s header (or `master-data.md`'s Contact
    section), Industry the single-word `<industry>` slug from this run (e.g.
    `Consulting`, capitalized; if it's hyphenated like `quant-trading`, collapse it
    to one word, e.g. `QuantTrading`). Deliver that file to the user as a
    downloadable file.
10. Clean build artifacts (e.g. `latexmk -c`) and remove the generated PDF from
    the working tree — it's a build artifact regenerated on demand, not tracked in git.
11. Switch back to `main`: `git checkout main`.
12. Report to the user: branch name, a short summary of what was emphasized or
    reordered for this industry, and confirmation the PDF was delivered (or why not,
    per step 7).

## Error handling

- Dirty working tree at step 1 → stop, do not create the branch.
- Branch already exists at step 3 → stop, tell the user, do not overwrite.
- Compile failure at step 7 → fix the LaTeX before committing; if it can't be fixed,
  report the error and stop rather than committing broken LaTeX.
