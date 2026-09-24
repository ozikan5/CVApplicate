---
name: cv-log-application
description: Record that you actually submitted an application from an outbox packet - commits that packet's cv.tex to the industry branch and appends the log entry with the real submission date. Use when the user says they have applied.
---

# CV Log Application

The only step in the packet flow that writes git history. It runs when you have
actually submitted an application, which is what keeps `applications/log.yaml` honest:
tailoring a CV is not applying with it.

## Inputs needed

1. **Which packet** — a company name, role, or `outbox/` directory. If ambiguous,
   list the candidates with their `created` dates and ask; never guess.

## Procedure

1. Run `git status`. If the working tree is not clean, stop and say what is
   uncommitted.
2. Read the packet's `packet.yaml`. If `applied` is already `true`, report the
   existing log entry id and stop — this application is already recorded. If
   `filled` is set but the user has not said they submitted, confirm they actually
   did: `cv-fill-application` only prefills the form, and a filled form is not a
   submitted one.
3. If `compile` is `failed` or `skipped`, warn the user that no verified PDF was
   produced and confirm they still want to record the application before continuing.
4. `git checkout <industry_branch>` from `packet.yaml`.
5. Copy the packet's `cv.tex` over the branch's `cv.tex`.
6. Commit that file only:
   `git add cv.tex && git commit -m "Apply: <company> <role>"`
   Capture the SHA with `git rev-parse HEAD`.
7. `git checkout main`.
8. Append one entry to `applications/log.yaml`, matching the existing schema exactly:
   ```yaml
   - id: <company-slug>-<industry>-<yyyy-mm>
     company: "<company>"
     role: "<role>"
     industry_branch: <branch>
     date_applied: <today>
     jd_source: url
     jd_url: "<packet url>"
     jd_summary: "<two or three sentences on what the posting actually asks for>"
     cv_commit: "<sha from step 6>"
     base_quality_score: <base_quality_after from packet.yaml>
     jd_fit_score: <jd_fit_after from packet.yaml>
     weak_points_fixed: <from packet.yaml, plus any gaps as GAP entries>
     outcome: pending
     outcome_date: null
   ```
   Use the **after** scores: they describe the CV that was actually sent.
9. Commit: `git add applications/log.yaml && git commit -m "Log application: <company> <role>"`.
10. Set `applied: true` in the packet's `packet.yaml`.
11. Report the entry id, the branch, the `cv_commit`, and that
    `git show <cv_commit>:cv.tex` will recover the exact CV sent.

## Error handling

- Dirty working tree at step 1 → stop before any checkout.
- Ambiguous packet → list candidates and ask.
- `applied: true` already → stop; do not write a second entry.
- Packet missing `cv.tex` → stop; there is nothing to commit.
- If the run fails after step 6 but before step 9, the branch has a commit with no log
  entry. Say so explicitly and name the SHA so it can be logged or reverted by hand —
  never leave the user to discover the mismatch later.
