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
7. Commit: `git add cv.tex && git commit -m "Adapt CV for <industry>"`.
8. Switch back to `main`: `git checkout main`.
9. Report to the user: branch name, and a short summary of what was emphasized or
   reordered for this industry.

## Error handling

- Dirty working tree at step 1 → stop, do not create the branch.
- Branch already exists at step 3 → stop, tell the user, do not overwrite.
