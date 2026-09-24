# Postman — Design

**Date:** 2026-09-24
**Status:** Approved, not yet implemented
**Phase:** D of the application-automation roadmap

## Problem

`applications/log.yaml` records 17 real applications, and not one has an outcome
other than `pending`. Outcomes arrive by email — rejections, assessment invites,
interview invites — and recording them means reading the inbox and running
`cv-log-outcome` by hand for each one. It has never happened, so the log cannot yet
answer the question it was built for: which CV versions got past the first screen.

## Goals

- Read recruiting mail nightly and propose an outcome for each application it
  concerns, with the evidence that justifies it.
- Never change the mailbox. Never write the application log without the user's
  confirmation.
- Keep the Gmail credential out of the model's context entirely.
- Handle companies with several applications without guessing between them.
- Backfill: the first run covers every application since the earliest
  `date_applied`.

## Non-goals

- **Automatic outcome commits.** Considered and rejected: see
  [The honesty line](#the-honesty-line).
- **Treating application-received receipts as evidence of submission.** Useful, but
  declined for this phase.
- **Proposing `no_response` after a silence window.** Also declined. `no_response`
  stays available for hand-logging.
- **Replying to, labelling, archiving or deleting mail.** The Postman is read-only.

## The honesty line

Phase B established that the unattended path cannot write git history: neither
runner holds a commit grant, so no scheduled run can claim an application the user
did not make. Updating `outcome` means committing `applications/log.yaml` on
`main`, so an auto-committing Postman would be the first component to break that
rule.

The risk is misclassification. "Thank you for your interest — we'd like to invite
you to a coding assessment" and "Thank you for your interest — unfortunately…" open
identically, and a wrong `rejected` is the costly error: the user stops thinking
about an application that is still alive.

So the nightly run **proposes**, and the user **confirms** in one interactive pass.
They never read mail, and nothing reaches the log without a yes.

## Vocabulary

`pending < assessment < interview < offer`, with `rejected` reachable from any of
them, plus `no_response` for hand-logging.

`assessment` is new. Online assessments are the most common first response for
quant and big-tech internships, and folding them into `interview` — as
`cv-log-outcome` currently does — erases the distinction between receiving an OA and
passing one. `cv-log-outcome` is updated to accept it, so hand-logging and the
Postman share one vocabulary.

## Architecture

```
NIGHTLY (unattended, no git writes)                YOU (interactive)
postman.sh
  └─ cv-check-mail (skill)
       ├─ python3 pipeline.py mail     ← IMAP, read-only; credential stays here
       │     connect → EXAMINE the \All folder
       │     SEARCH SINCE <earliest date_applied>
       │     FETCH BODY.PEEK[…]         (messages stay unread)
       │     prefilter → only ATS / applied-company mail
       │     drop already-seen Message-IDs
       │     → JSON on stdout
       ├─ model classifies each candidate
       └─ writes outcomes.pending.yaml  ─────────►  cv-review-outcomes (skill)
                                                     yes / no / edit each
                                                     → applications/log.yaml
                                                     → one commit on main
```

### Why Python fetches and the model classifies

Two alternatives were considered and rejected:

- **Fully deterministic classification** by keyword. Phrasing is exactly what the
  eligibility gate showed regexes misjudge — "unfortunately, the portal was down,
  please resubmit" reads as a rejection — and a wrong `rejected` is the costly error.
- **The model reading mail directly through a Gmail connector.** The model would
  search the inbox itself and see far more of it, unattended runs would have to carry
  connector auth, and scoping would rest on the connector rather than on code under
  test.

The split chosen is the gate's: deterministic where testable, judgment where not.
Python holds the credential and narrows the mailbox to a few relevant messages; the
model sees only those, trimmed.

### Files

```
job_fetcher/mailbox.py        the only code that touches IMAP
job_fetcher/outcomes.py       prefilter, company matching, stage ordering, pending file
pipeline.py                   gains a `mail` subcommand
postman.sh                    nightly runner
launchd/com.cvapplicate.postman.plist.example
plugins/cvapplicate/skills/cv-check-mail/SKILL.md       unattended: proposes
plugins/cvapplicate/skills/cv-review-outcomes/SKILL.md  interactive: confirms, commits
plugins/cvapplicate/skills/cv-log-outcome/SKILL.md      gains `assessment`
outcomes.pending.yaml         gitignored; proposals + seen Message-IDs
```

`mail` is a subcommand of the existing `pipeline.py` rather than a new script, so
every runner keeps the single narrow grant `Bash(python3 pipeline.py:*)` and no new
executable surface appears.

## Mail access

### Read-only by construction

The credential is the existing Gmail app password in `.env` (`SMTP_USER`,
`SMTP_APP_PASSWORD`), reused over IMAP (`IMAP_HOST`, default `imap.gmail.com`). An
app password grants full mailbox access — read, send, delete — so the credential
itself offers no protection. Read-only is enforced by the code:

- The mailbox is opened with `select(folder, readonly=True)`, which issues `EXAMINE`.
- Every fetch uses `BODY.PEEK[…]`. A plain `BODY[]` fetch sets `\Seen` and marks the
  message read.
- `mailbox.py` never issues `STORE`, `COPY`, `MOVE`, `EXPUNGE`, `APPEND`, `DELETE` or
  `CREATE`.

This is enforced by a test, not by a comment: a recording fake connection fails the
suite on any of those commands, or on any fetch lacking `PEEK`.

### Which folder

`[Gmail]/All Mail`, not `INBOX`. Recruiting mail often lands in a category tab or is
archived by a filter, and an `INBOX`-only search misses precisely the rejection a
filter tidied away. Messages from the user's own address are excluded.

The folder is resolved by its IMAP `\All` special-use attribute, **not its name**:
Gmail localizes folder names in some interface languages, so on a Turkish-language
account "All Mail" is not called "All Mail". If no `\All` folder is found, fall back
to `INBOX` and warn loudly.

### The SINCE date

IMAP requires English month abbreviations (`SINCE 14-Aug-2026`). `strftime("%b")` is
locale-dependent and on a Turkish locale yields `Ağu`, which the server rejects. Month
names come from a fixed English table.

Both of these pass every test on an English machine and fail on the user's.

### What leaves `mailbox.py`

Per message: `Message-ID`, sender, date, subject, and the first 1,500 characters of
the body — `text/plain` preferred, HTML stripped through `htmltext`, encoded headers
(`=?UTF-8?…`) decoded. Nothing else, and never the credential.

## Matching

### Prefilter (deterministic, `outcomes.py`)

A message is a candidate when its sender domain is a known ATS (Greenhouse, Lever,
Workday, Ashby, SmartRecruiters, iCIMS, Taleo) or assessment platform (HackerRank,
CodeSignal, HireVue), **or** when a company alias from the log appears as a whole
word in its sender or subject.

Aliases are derived from the log's `company` field: "Chicago Trading Company (CTC)"
yields `chicago trading company` and `ctc`. Whole-word matching is load-bearing
because the aliases are short — `ctc` must not match inside `ctcarrier.com`.

Assessment platforms are why the prefilter cannot stop at company names: a HackerRank
invite comes from `hackerrank.com` and names the employer only in the body. Platform
mail passes through and the model identifies the company.

### Candidates and ambiguity

The prefilter attaches **every** application at a matching company as a candidate.
Seven of the seventeen applications share a company with another (Microsoft ×3, Jane
Street ×2, TikTok ×2), so a Microsoft rejection arrives carrying three.

The model narrows the list when the mail names the role or a requisition number, and
**otherwise leaves it open**. It must never guess which of several applications a
message concerns; the user picks at confirm time.

### Stages only move forward

A proposal that would move an application backward — an old assessment email arriving
after an interview is logged — is marked `regresses: true`, and its default answer at
confirm time is no.

## The pending file

`outcomes.pending.yaml`, gitignored:

```yaml
seen:               # every Message-ID processed, including non-outcomes
  - "<abc123@mail.citadel.com>"
proposals:
  - message_id: "<abc123@mail.citadel.com>"
    received: 2026-09-02
    from: "Citadel Recruiting <no-reply@citadel.com>"
    subject: "Your Citadel Application"
    proposed_outcome: rejected
    application_id: citadel-swe-2026-08    # null when ambiguous
    candidates: []                          # filled when ambiguous
    evidence: "Unfortunately, we will not be moving forward with your application"
    confidence: high                        # high | medium | low
    regresses: false
```

A message judged not to be an outcome — a receipt, a newsletter — goes into `seen`
only, so it is never reprocessed. Proposals and `seen` are written in **one edit**: if
a run dies midway, no message is marked seen without its proposal also being
recorded.

A message with no `Message-ID` falls back to a hash of sender, date and subject.

## Confirming

`cv-review-outcomes`, interactive only:

1. Require a clean working tree; check out `main`.
2. Present each proposal with its evidence and a **default answer**. The default is
   yes only when `confidence` is `high`, `regresses` is false and exactly one
   application matches; otherwise it is no, so a low-confidence, regressing or
   ambiguous proposal can never be accepted by just pressing through. The user answers
   yes, no, or edit — pick one of the candidates, or change the outcome.
3. Write confirmed outcomes to `applications/log.yaml` with **`outcome_date` set to
   the email's date, not today**. `cv-log-outcome` uses today, which is right only when
   logging the same day; across a six-week backfill the email date is the true one.
4. When several confirmed proposals concern one application, keep the
   furthest-forward stage.
5. Make **one commit** for the whole pass. Remove handled proposals; keep `seen`.

It never confirms anything on its own. An ambiguous proposal cannot be applied until
the user picks the application.

## Permission scope

`postman.sh`:

```
Read Edit(/outcomes.pending.yaml) Bash(python3 pipeline.py:*)
```

The leading `/` anchors the rule to the working directory: an unanchored allow rule
matches only at a literal depth from wherever the session starts, which is fragile for
a scheduled job. `Edit` rules also govern the Write tool, so this permits creating the
file on the first run.

No `Edit` on `applications/log.yaml` and no git write, so the unattended path cannot
change the log even if the skill misbehaves. Only `cv-review-outcomes`, which is
interactive, commits.

## Error handling

- **IMAP disabled or authentication failure** — exit 2 with the actionable fix (Gmail
  → Settings → Forwarding and POP/IMAP → Enable IMAP), nothing written.
- **Network failure or timeout** — exit 4, nothing written, retried next night.
  `socket.timeout` is caught explicitly: on Python 3.9 it is not a `TimeoutError`
  subclass, the defect that was Phase A's Critical.
- **Missing credentials in `.env`** — exit 2.
- **No `\All` folder** — fall back to `INBOX`, warn.
- **Unparseable message** — mark seen with a note; never retried forever, never fatal.
- **Large backfill** — capped at 200 candidates per run to bound cost; the remainder
  carries over and the report states how many.
- **Proposal for an application since removed from the log** — skipped at confirm
  time with a note.

## Testing

Offline and fixture-based.

`mailbox.py`:
- **the read-only invariant** — a recording fake connection fails on any
  state-changing command or any fetch without `PEEK`. The most important test here.
- folder resolution by `\All`, including a fixture with a localized folder name
- `SINCE` formatting under a non-English locale
- RFC 2047 encoded headers; multipart bodies, plain text preferred and HTML stripped;
  truncation; exclusion of the user's own address

`outcomes.py`:
- prefilter: ATS domains, assessment platforms, whole-word aliases, and the negative
  case — `ctc` does not match `ctcarrier.com`
- alias derivation from a parenthesized acronym
- a Microsoft message yields all three candidates
- stage ordering and the regression flag
- pending-file round-trip, `seen` dedup, and the `Message-ID` fallback

`pipeline.py mail`:
- the JSON contract and exit codes
- **the app password never appears in stdout or stderr**, asserted explicitly

### Fixtures come from real mail

This project has been burned three times by fixtures friendlier than real input:
Greenhouse's entity-escaped HTML, the gate against whitespace-collapsed HTML, and
location matching against "San Francisco, CA". Parsing mail — encodings, multipart
layouts, platform templates — is the same risk in a new place.

So fixtures are derived from real recruiting emails the user exports as `.eml`, kept
outside both repositories. Committed fixtures are trimmed, with the user's name,
address, phone, candidate IDs and tokenized links replaced, and each is shown to the
user before it enters `CVApplicate`, which is a public repository.

The validation that remains after that is the first real run on the user's machine,
reviewed proposal by proposal in `cv-review-outcomes` — which is built to make a
misclassification cost a "no" rather than a wrong log entry.
