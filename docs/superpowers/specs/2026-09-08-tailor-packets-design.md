# Tailor Packets — Design

**Date:** 2026-09-08
**Status:** Approved, not yet implemented
**Phase:** B of the application-automation roadmap

## Problem

Phase A resolves a posting URL into a stored, scored posting. Everything after that
is still manual: you read `matches.local.yaml`, pick winners, run `cv-review` once per
posting, then fill the portal by hand.

`cv-review` cannot simply be run in a loop to close that gap, because it conflates
*tailored* with *applied*. Its step 9 commits `cv.tex` on the industry branch and its
step 12 appends a `log.yaml` entry with `date_applied` set to today. Batch-running it
would put a commit on `swe` and a logged application into your history for every
posting considered, including ones never submitted. The current log shows the cost of
that conflation already: 18 entries, every one `outcome: pending`.

`cv-review` also requires a clean working tree and runs `git checkout`, so it cannot
run while you have anything in progress.

## Goals

- Paste a posting URL into a queue; get back a submit-ready packet.
- Tailor without touching the industry branch, the working tree, or the application
  log.
- Commit and log exactly the CVs you actually send, preserving the `cv_commit`
  recoverability guarantee the README makes.
- Shape the packet as the Phase C Filler's input, so the browser work is an addition
  rather than a rewrite.
- Never spend a tailoring pass on a posting you are not eligible for.

## Non-goals

- **Filling or submitting the application.** That is Phase C. This phase ends at a
  packet on disk.
- **Nightly discovery → tailoring.** Deliberately dropped, see
  [Deferred](#deferred-and-open-items).
- **Changing the `log.yaml` schema.** Entries written here match the existing shape
  exactly.
- **Editing `master-data.md`.** `cv-review` backports improved wording; this phase
  does not.

## Prerequisite: the eligibility gate

Scoring currently treats seniority as 20% of a weighted total, so a hard disqualifier
becomes a soft penalty. A live example from validating Phase A: NVIDIA's Infiniband
Network Software Engineer requires "4+ years of experience as Software Engineer", is
full-time, and is located in Raanana, Israel. Scored against a 2028-graduation
internship seeker it returned **61/100** — keyword match 78, seniority fit 30 —
because a keyword-rich JD cannot be dragged below the middle band by one 20% factor.
A posting that cannot be accepted should not produce a score at all.

This matters doubly for Phase B: the Tailor spends a full tailoring pass and a LaTeX
compile on whatever it selects.

### `profile.local.yaml`

Copied from `profile.example.yaml`, gitignored like every other `*.local.yaml`:

```yaml
seeking: internship          # internship | new-grad | full-time
graduation: 2028-06
locations: ["United States", "Remote (US)"]
max_years_experience_required: 1
work_authorization: cpt-opt  # cpt-opt | citizen-or-pr | unrestricted; omit to disable
```

### Gate rules

A posting is **ineligible** when any of these holds. Each records a reason string:

- the JD states a minimum years-of-experience above `max_years_experience_required`
- `seeking` is `internship` and the JD is plainly a full-time non-internship role
- no stated location matches `locations`
- the JD names a work-authorization requirement the `work_authorization` value cannot
  satisfy (see below)

Ineligible postings are recorded in `matches.local.yaml` with `eligible: false` and a
`reasons` list, **no score fields**, and are marked `scored: true` so they are not
reprocessed. Judgment calls stay soft: when a requirement is ambiguous ("or equivalent
experience", an unstated location), the posting is treated as eligible and scored, and
the ambiguity is noted in the rationale. The gate exists to exclude the clear-cut
cases, not to guess.

### Work authorization, precisely

`work_authorization: cpt-opt` describes a student working on school-authorized
practical training. The naive implementation — disqualify anything containing
"sponsorship" — would be wrong and would silently discard a large share of open
internships, because **an F-1 student on CPT is already authorized to work for an
internship without employer sponsorship**. CPT is authorized by the school, not the
employer.

Disqualifying under `cpt-opt`:

- "must be a US citizen", "US citizenship required" (common for defense, government
  and cleared work)
- "US citizen or permanent resident only"
- "we do not hire candidates on CPT or OPT", "cannot accept CPT/OPT"
- an explicitly stated security clearance requirement

**Not** disqualifying under `cpt-opt`, and this is the load-bearing half of the rule:

- "must be authorized to work in the US without sponsorship" — CPT satisfies this for
  an internship
- "we are unable to provide visa sponsorship" — likewise, for an internship; it speaks
  to H-1B sponsorship, not practical training
- any mention of sponsorship with no stated restriction on CPT/OPT or citizenship

`citizen-or-pr` disqualifies nothing on authorization grounds. `unrestricted` and an
omitted key both disable the rule. When the phrasing does not clearly fall into the
disqualifying list, the ambiguity rule applies: the posting stays eligible and the
wording is noted.

#### The rule must require requirement-framing, and must exclude EEO boilerplate

Three real phrasings, taken from a live board on 2026-09-08, define the rule's edges.
All three become fixtures.

1. **Disqualifying, and only detectable via the CPT/OPT qualifier:**
   > "Unfortunately, we are not able to sponsor visas, including CPT/OPT or employ
   > corp-to-corp."

   "not able to sponsor visas" on its own is permissive per the rules above. It is the
   trailing "including CPT/OPT" that disqualifies. A rule keyed on "sponsor" gets the
   right answer here for the wrong reason, and the wrong answer everywhere else.

2. **Disqualifying, requirement-framed:**
   > "Clearance: Ability to hold or obtain a U.S. security clearance; U.S. citizenship
   > as required for cleared federal work."

3. **NOT disqualifying — and this is the trap that matters most:** an eligible Summer
   2027 software engineering internship in San Francisco whose only occurrence of the
   word "citizenship" is its equal-opportunity statement:
   > "…regardless of race, color, ancestry, religion, sex, national origin, sexual
   > orientation, age, citizenship, marital status, disability status, gender identity
   > or Veteran status."

   This is a non-discrimination statement — the opposite of a requirement — and
   near-identical language appears in most US postings. A naive rule matching
   "citizenship" disqualifies almost every posting the user is actually eligible for,
   while passing a test suite built only from cases 1 and 2.

The rule therefore has two obligations: a match must carry **requirement framing**
("must be", "required", "only", "not able to"), and any match inside a
**non-discrimination context** ("regardless of", "without regard to", "does not
discriminate", "equal opportunity") is discarded outright.

#### Where the judgment lives

Eligibility is judgment, not parsing, but it is not *only* judgment. The split:

- `job_fetcher/profile.py` returns one of `disqualified(reason)`, `ok`, or `ambiguous`
  for the authorization question, using patterns that demand requirement framing and
  discard non-discrimination context. This is deterministic and unit-testable against
  the three fixtures above.
- The scoring skill adjudicates `ambiguous`, and owns the softer questions a regex
  should not decide — whether a role is genuinely an internship, and whether a stated
  years-of-experience figure is a requirement or incidental prose.

Deterministic where it can be tested, model judgment where it cannot.

**A queued URL bypasses nothing.** The gate applies to queued postings too, but an
ineligible queued posting is reported to you with its reasons rather than silently
skipped, since you asked for it explicitly. It is not tailored.

## Architecture

### Entry points

```
QUEUE (you decided)                DISCOVERY (machine guessed)
queue.local.txt                    fetch-postings.py -> postings.local.yaml
   | one URL per line                    |
   v                                     v
resolve-posting.py (Phase A)       cv-score-postings (+ eligibility gate)
   v                                     |
cv-score-postings (+ gate)               v
   v                               matches.local.yaml  <- you read this
cv-tailor-packet                         |
   v                                     +--> you queue what you want
outbox/<company>-<role>/
   v
[Phase C: the Filler]
   v
cv-log-application                 <- you applied
```

Only the queue leads to tailoring. Discovery ends at `matches.local.yaml`, which you
read and selectively queue from.

### The queue is deliberately stateless

`queue.local.txt`: one URL per line, `#` comments, blank lines ignored. It holds no
status and is never rewritten by the tool — you own the file. Re-listing a URL is a
harmless no-op, because `resolve-posting.py` dedupes by posting id and the `packeted`
flag stops a second packet. Nothing to corrupt and nothing to clean up.

### Tailoring runs in a throwaway worktree

`cv-tailor-packet` runs `git worktree add .worktrees/tailor-<posting-id> <branch>`,
edits and compiles inside it, copies artifacts to the packet directory, then removes
the worktree and runs `git worktree prune`. Cleanup is unconditional — on success and
on every failure path — because a leftover worktree breaks the next run.

The working tree and current branch are never touched, matching the constraint
`cv-score-postings` already honours. `.worktrees/` is gitignored.

The branch tailored is `best_branch` from `matches.local.yaml`, overridable when you
queue a URL by hand.

### Files

```
profile.example.yaml -> profile.local.yaml    eligibility and intent
queue.local.txt                               gitignored; you append URLs
outbox/<company>-<role>/                      gitignored; the packets
job_fetcher/profile.py                        gate config + rule evaluation helpers
job_fetcher/tailor.py                         queue parsing, slugs, selection
tailor-packets.sh                             runner
launchd/…tailor-packets.plist.example         optional schedule for queue draining
plugins/cvapplicate/skills/cv-tailor-packet/SKILL.md
plugins/cvapplicate/skills/cv-log-application/SKILL.md
```

### State

`postings.local.yaml` gains a `packeted` flag beside `notified` and `scored` — same
pattern, same owner (`store.py`). No new state file; the runner knows what it has
already built without scanning the filesystem.

## The packet

One directory per posting, named `<company-slug>-<role-slug>`, suffixed with the
posting id on collision (two roles at one company):

```
outbox/nvidia-infiniband-network-software-engineer/
├── Ozan_Kan_CV_Nvidia.pdf   the upload
├── cv.tex                    tailored source; committed at apply time
├── PACKET.md                 for you: scores before/after, what changed, gaps
├── skills.txt                ranked keywords, copy-paste ready
├── jd.txt                    the resolved description
└── packet.yaml               machine-readable, for the Filler
```

`PACKET.md` and `packet.yaml` describe the same run for two different readers: you,
and Phase C. That is what makes "shaped as the Filler's input" concrete.

`jd.txt` is kept even though a posting is also stored in `postings.local.yaml`,
because the Filler needs the JD text to draft free-text answers and a posting can be
pulled from the web before you get to it. The packet is self-contained.

### `packet.yaml`

```yaml
posting_id: workday-nvidia-JR2007263
company: "Nvidia"
role: "Infiniband Network Software Engineer"
url: "https://…"
industry_branch: quant-trading
created: 2026-09-08
cv_pdf: Ozan_Kan_CV_Nvidia.pdf
cv_tex: cv.tex
compile: ok                      # ok | failed | skipped (no toolchain)
skills: ["C++", "…"]
base_quality_before: {total: 93, impact: 93, competencies: 93, presentation: 91}
base_quality_after:  {total: 95, impact: 95, competencies: 94, presentation: 93}
jd_fit_before: {total: 61, keyword_match: 78, experience_relevance: 60, seniority_fit: 30}
jd_fit_after:  {total: 72, keyword_match: 88, experience_relevance: 70, seniority_fit: 30}
weak_points_fixed: ["…"]
gaps: ["…"]
applied: false
```

`applied` makes the packet self-describing and prevents double-logging.

## The apply step

`cv-log-application` is the only thing in this phase that writes git history.

1. Confirm the working tree is clean; stop if not.
2. Check out the branch named in `packet.yaml`, copy the packet's `cv.tex` over
   `cv.tex`, commit `Apply: <company> <role>`, capture the SHA.
3. Return to `main` and append a `log.yaml` entry in the **existing schema**, with the
   real `date_applied`, that `cv_commit`, the post-tailoring score sets,
   `weak_points_fixed`, `outcome: pending`, `outcome_date: null`, `jd_source: url`
   and `jd_url` populated (both fields already exist; current entries use
   `pasted`/`null`).
4. Commit `log.yaml`.
5. Set `applied: true` in `packet.yaml`.
6. Report the entry id, the branch, and the `cv_commit`.

`git show <cv_commit>:cv.tex` therefore keeps working for every application you
actually send — and only those.

## Permission scope

`tailor-packets.sh` drains the queue by invoking three things in sequence —
`resolve-posting.py`, `cv-score-postings`, then `cv-tailor-packet` — so its grant is
the union of what those need. `Edit(matches.local.yaml)` is there for the scorer and
the eligibility gate, not the Tailor; `Edit(postings.local.yaml)` covers the `scored`
and `packeted` flags:

```
Read Write Edit(postings.local.yaml) Edit(matches.local.yaml)
Bash(python3 resolve-posting.py:*) Bash(git worktree:*) Bash(git show:*)
Bash(git for-each-ref:*) Bash(latexmk:*) Bash(pdflatex:*) Bash(tectonic:*)
```

**No `git add` and no `git commit`.** The tailoring path is therefore structurally
incapable of writing history or claiming an application — enforced by the grant, not
by the skill remembering. `cv-log-application` is interactive and gets commit
permission; it is never invoked by a scheduled run.

## Error handling

- **No LaTeX toolchain** — packet still produced with `cv.tex`, notes and scores;
  `compile: skipped`, and `PACKET.md` says so. Matches `cv-review`'s existing
  behaviour.
- **Compile failure** — keep the tailored `.tex` for inspection, write the LaTeX error
  into `PACKET.md`, set `compile: failed`. A broken packet must never look
  submit-ready.
- **Worktree cleanup** — unconditional, on every exit path, followed by
  `git worktree prune`.
- **Posting with no description** — never tailored; same rule the scorer applies.
- **Ineligible posting** — not tailored. Reported with reasons if queued; silently
  skipped if it came from discovery.
- **Unresolvable queue URL** — Phase A's exit codes 3/4/5 are recorded in the run
  report. The queue file is left untouched. A filled posting reports "no longer
  available" rather than retrying nightly forever.
- **Branch missing `cv.tex`** — skip that posting with a note.
- **Already packeted** — skip.
- **Guardrails are binding**, exactly as in `cv-review`. When the JD wants something
  that cannot be honestly claimed, the wording stays honest and it goes in `gaps`.

## Testing

The judgment lives in the skills; the selection and bookkeeping is Python with a real
unit surface. All fixture-based and offline, as in Phase A.

`job_fetcher/tailor.py`:
- queue parsing: comments, blank lines, duplicates, surrounding whitespace, a
  non-URL line
- packet slug generation: collisions, very long role titles, non-ASCII characters
- selection: excludes already-packeted and ineligible postings

There is deliberately no `tailor.local.yaml`. A queue-only Tailor has no score floor
and no per-run cap to configure, the packet directory is `outbox/` by convention, and
the PDF name already follows `cv-review`'s `First_Last_CV_Company` rule. A config file
holding nothing but those would be scope without a purpose.

`job_fetcher/profile.py`:
- config loading with defaults and a missing-file error message matching
  `config.py`'s style
- each gate rule in isolation: years-of-experience above the cap, a full-time role
  when seeking an internship, an unmatched location
- **the ambiguity rule**: "or equivalent experience" and an unstated location must
  come back eligible, not ineligible
- **work authorization, both directions.** Under `cpt-opt`: "must be a US citizen" and
  "we do not hire on CPT or OPT" are ineligible; "must be authorized to work without
  sponsorship" and "unable to provide visa sponsorship" are **eligible**. The second
  pair is the regression test that matters — a rule keyed on the word "sponsorship"
  passes the first pair and silently discards most open internships.
- the NVIDIA posting as a fixture, asserted ineligible with all three reasons — the
  regression test for the defect that motivated the gate

`job_fetcher/store.py`:
- `packeted` flag round-trip, and that omitting it preserves current behaviour

## Deferred and open items

**Nightly discovery → tailoring.** Considered and dropped. Discovery is where the
machine guesses, and the guess that motivated the eligibility gate is exactly the
kind it gets wrong; unattended tailoring would spend real money on those guesses.
Discovery ends at `matches.local.yaml` and you queue from it. Revisit once the
eligibility gate has enough real runs to trust its precision.

**The scorer's seniority weighting.** The gate excludes clear-cut ineligible
postings, but for eligible ones seniority is still 20% of a weighted total. Whether a
near-miss on seniority should also be a stronger signal is a separate question about
the rubric that `cv-review` and `cv-score-postings` share, and changing it would
reprice every historical score.

**The Python pipeline is still not plugin-distributed.** Carried from Phase A, and
this phase adds two more root-level modules and a runner, so the manual sync into a
data repo grows. Worth settling before Phase C.
