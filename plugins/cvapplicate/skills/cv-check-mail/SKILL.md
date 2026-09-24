---
name: cv-check-mail
description: Read recent recruiting mail and propose outcomes (assessment, interview, offer, rejected) for logged applications, writing proposals with evidence to outcomes.pending.yaml. Never changes the mailbox or the application log. Normally run nightly and unattended by postman.sh.
---

# CV Check Mail

Turns recruiting email into outcome **proposals**. It never decides an outcome:
`cv-review-outcomes` is where the user confirms, and it is the only step that writes
`applications/log.yaml`.

## Inputs needed

None. Everything comes from `python3 pipeline.py mail`.

## Procedure

1. Run `python3 pipeline.py mail` and read its exit code.
   - **2** — configuration or authentication problem. Report the message and stop.
   - **4** — the mail server was unreachable. Report it and stop; the next run retries.
   - **0** — continue.
2. Read the JSON. Report every string in `warnings` — in particular a fallback to
   INBOX means archived or filtered mail was not searched.
3. For each entry in `candidates`, decide what it is:
   - **`rejected`** — the employer is not proceeding.
   - **`assessment`** — an online assessment or coding challenge (HackerRank,
     CodeSignal, a take-home), including a reminder about one.
   - **`interview`** — an invitation to speak with a person: phone screen, technical
     interview, superday, final round.
   - **`offer`** — an offer of employment.
   - **not an outcome** — an application-received receipt, a newsletter, a job alert,
     marketing from a company's product, an event invitation.

   Judge from the `subject` and `body` together. "Thank you for your interest" opens
   rejections and invitations alike; read on. If the message is genuinely unclear,
   propose it with `confidence: low` rather than guessing a firm outcome.
4. Decide which application it concerns:
   - If `candidate_ids` has exactly one id, use it.
   - If it has several — the same company, more than one application — pick one only
     when the message names the role, team or requisition number of exactly one of
     them, using `applications` to see each one's `role`. Otherwise leave
     `application_id: null` and copy all of them into `candidates`. **Never guess
     between applications at the same company.**
   - If it is empty — typically assessment-platform mail — identify the employer from
     the `body` and match it against `applications`. If that employer has several
     applications, the rule above applies unchanged: pick one only when the message
     names the role, team or requisition number of exactly one; otherwise leave
     `application_id: null` and list every matching application in `candidates`. If
     you cannot identify the employer at all, leave `application_id: null` with an
     empty `candidates` list.
5. Assign `confidence`: `high` only when both the outcome and the application are
   unambiguous; `medium` when one of them needed judgement; `low` when you are unsure.
6. Record the run in `outcomes.pending.yaml` with **one** tool call, so a run that dies
   midway never marks a message seen without also recording its proposal.

   The file keeps `proposals:` first and `seen:` **last**, so both lists can grow in one
   small edit without rewriting the file:
   ```yaml
   proposals:
     - message_id: '<abc123@mail.citadel.com>'
       received: 2026-09-02
       from: 'Citadel Recruiting <no-reply@citadel.com>'
       subject: 'Your Citadel Application'
       proposed_outcome: rejected
       application_id: citadel-swe-2026-08
       candidates: []
       evidence: |-
         Unfortunately, we will not be moving forward with your application
       confidence: high
   seen:
     - '<abc123@mail.citadel.com>'
     - '<def456@greenhouse-mail.io>'
   ```
   - **If the file does not exist**, create it with Write in exactly that layout.
   - **If it exists**, Read it, then make one Edit whose `old_string` is the line
     `seen:` and whose `new_string` is your new proposal entries, then `seen:`, then
     your new seen ids. That appends the proposals to the end of the proposals list and
     the ids to the top of the seen list. Do not rewrite or reorder existing entries,
     and never remove any — `cv-review-outcomes` owns removal.
   - An empty list is a bare `proposals:` or `seen:` line, never `[]`. If you find
     `[]` in the file, Write the whole file back instead, in the layout above, with
     every existing entry kept — still one tool call.
   - `seen` gets every candidate's `message_id` — outcomes and non-outcomes alike, so
     nothing is ever reprocessed.
   - Write `message_id`, `from` and `subject` in single quotes, doubling any `'` inside.
     Write `received` unquoted as `YYYY-MM-DD`, or `null` if the candidate had none.
   - `evidence` is a **verbatim** quote from the message body, the shortest one that
     justifies the outcome, written as the `|-` block shown. Never paraphrase it: the
     user confirms against it.
   - Afterwards, run `python3 pipeline.py review`. If it exits non-zero, the file no
     longer parses: fix only the entries you just added, run it again, and report
     loudly if it still fails.
7. If `remaining` is greater than zero, say so: that many more candidates wait for the
   next run.
8. Report: how many messages were examined, how many proposals were written by outcome
   type, how many were ambiguous, and any warnings.

## Error handling

- Never edit `applications/log.yaml`. Never run any `git` command. Never compute
  `regresses` or a default answer — `pipeline.py review` does that at confirm time.
- If writing `outcomes.pending.yaml` fails, say so plainly: those messages were not
  marked seen and will be offered again next run, which is safe.
- Never include the contents of `.env`, or any credential, in a report.

## Permission scope

```
Read Edit(/outcomes.pending.yaml) Bash(python3 pipeline.py:*)
```

No git grant and no `Edit` on `applications/log.yaml`, so this skill cannot change the
application log even if it misbehaves.
