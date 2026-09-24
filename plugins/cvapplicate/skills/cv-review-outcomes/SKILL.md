---
name: cv-review-outcomes
description: Walk through the outcome proposals cv-check-mail found in your recruiting mail, confirm or reject each, and record the confirmed ones in applications/log.yaml in one commit. Use when the user wants to review or apply pending application outcomes.
---

# CV Review Outcomes

The only step in the mail flow that writes the application log. Nothing reaches
`applications/log.yaml` without the user saying yes.

## Inputs needed

None. Proposals come from `outcomes.pending.yaml`.

## Procedure

1. Run `git status --porcelain --untracked-files=no`. If it prints anything, stop and
   say what is uncommitted. Note the current branch so you can return to it.
2. `git checkout main` — the application log lives only on `main`.
3. Run `python3 pipeline.py review` and read the JSON. If there are no proposals, say
   so and stop.
4. Present the proposals one at a time. For each, show: the company and role (or the
   candidate applications, if ambiguous), `current_outcome` → `proposed_outcome`, the
   `received` date, the sender and subject, and the `evidence` quote verbatim. Show
   the **default answer** from `default_answer`, and say why when it is no — low
   confidence, `regresses`, ambiguous, or `application_missing` (the id it names is not
   in the log — perhaps removed since, perhaps mis-matched from the email).
5. Take the user's answer to **that proposal**. Every proposal needs its own answer:
   if the user says "yes to all" or similar, explain that each one is confirmed
   individually and ask about the current one.
   - **yes** — accept as proposed. This overrides a default of no, including one due to
     `regresses`; the user decides. A proposal that is ambiguous or
     `application_missing` cannot be accepted with a plain yes: ask which application
     it concerns — from its `candidates`, or, when those are empty, from the entries in
     `applications/log.yaml` — then treat the answer as an **edit**.
   - **no** — discard the proposal.
   - **edit** — change the outcome, or pick the application. The `received` date still
     becomes `outcome_date`. `regresses` was computed for the original proposal, so
     re-check the edited one: read the chosen application's current `outcome` in
     `applications/log.yaml`, and if the new outcome moves it backwards (an earlier
     stage in `pending < assessment < interview < offer`, or anything after `rejected`
     or `offer`), say so and ask the user to confirm again.
   Never accept a proposal on the user's behalf.
6. When several accepted proposals concern the same application, keep only the
   furthest-forward stage (`pending < assessment < interview < offer`, with `rejected`
   final) and tell the user which were superseded. If the furthest-forward one is not
   also the latest by `received` date — say, a rejection followed by a later interview
   invitation — do not resolve it yourself: show both with their dates and ask which
   to record.
7. For each accepted proposal, set that entry's `outcome` and set `outcome_date` to
   the proposal's **`received` date, not today**, as `YYYY-MM-DD` — the email date is
   when the outcome actually happened. If `received` is null, ask the user for the
   date rather than using today.
8. Commit once: `git add applications/log.yaml && git commit -m "Log outcomes: <N> applications"`.
9. Remove every handled proposal — accepted, edited or discarded — from
   `outcomes.pending.yaml`. Keep the `seen` list intact and the layout `cv-check-mail`
   relies on: `proposals:` first, `seen:` last, and an empty list as a bare
   `proposals:` line, never `[]`.
10. `git checkout` the branch you started on, if it was not `main`.
11. Report what was recorded, what was discarded, and what remains pending.

## Error handling

- Dirty working tree → stop before any checkout.
- If the commit fails, leave `outcomes.pending.yaml` untouched so nothing is lost,
  then undo the uncommitted log edit with `git restore --staged --worktree
  applications/log.yaml` so `main` is clean again, return to the starting branch, and
  report the error. The proposals remain pending for the next run.
- Never edit an application entry's fields other than `outcome` and `outcome_date`.
