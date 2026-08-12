---
name: cv-log-outcome
description: Record the outcome of a job application (interview, offer, rejection, no response) in the application log. Use when the user reports hearing back from a company they applied to.
---

# CV Log Outcome

Updates an existing entry in `applications/log.yaml` with the result of an
application.

## Inputs needed

1. **Company and/or role** — used to find the matching entry. If omitted, use the
   most recently added entry (last item in the list).
2. **Outcome** — one of: `interview`, `rejected`, `offer`, `no_response`. If the user
   describes it in other words (e.g. "got an OA", "ghosted"), map it to the closest
   of these four and confirm with the user if it's not obvious.

## Procedure

1. Run `git status` to confirm the working tree is clean. If not, stop and tell the
   user what's uncommitted.
2. Run `git checkout main`.
3. Read `applications/log.yaml`.
4. Find matching entries by `company` (case-insensitive) and, if given, `role`.
   - No matches → tell the user, list the companies that do exist, stop.
   - Multiple matches → list them (company, role, date_applied, id) and ask the user
     which one they mean. Do not guess.
   - Exactly one match → proceed.
5. Update that entry's `outcome` field to the given value and `outcome_date` to
   today's date (`YYYY-MM-DD`).
6. Commit: `git add applications/log.yaml && git commit -m "Log outcome: <company> <role> -> <outcome>"`.
7. Report to the user which entry was updated and to what.

## Error handling

- Dirty working tree at step 1 → stop, do not switch branches.
- No match or ambiguous match at step 4 → stop and ask; never guess which entry to
  update.
