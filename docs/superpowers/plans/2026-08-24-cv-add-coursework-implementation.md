# cv-add-coursework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a sixth Claude Code skill, `cv-add-coursework`, that reads a transcript
plus a job description, verifies which JD-named coursework the user has genuinely
taken (via judgment-based matching and a real web-search against the official course
description), and enriches `master-data.md`'s `Coursework:` line with grounded detail
— never touching `cv.tex`.

**Architecture:** A single self-contained Markdown instruction file at
`plugins/cvapplicate/skills/cv-add-coursework/SKILL.md`, written and validated on
`main` in `CVApplicate`, following
`docs/superpowers/specs/2026-08-23-cv-add-coursework-design.md`. Validated by running
it against a throwaway fixture (a fake transcript using real, publicly-documented
university course numbers, since the skill's core mechanism — a live web search
against a real course catalog — can't be exercised against the template's fictional
"Example University" placeholder data) and inspecting the resulting `master-data.md`
edit, then discarding the fixture. Unlike `cv-application-skills` (read-only, nothing
to sync into a personal fork's file tree), this skill both writes a file and, once
installed via the plugin mechanism, needs no separate "copy into your fork" step —
that mechanism was retired when `CVApplicate` became a real installable plugin.

**Tech Stack:** Claude Code Skills (Markdown + YAML frontmatter). No application code.

**Spec:** `docs/superpowers/specs/2026-08-23-cv-add-coursework-design.md`

## Global Constraints

- JD-driven scope only — never enrich coursework the current JD doesn't ask for.
- Never edit `cv.tex`. This skill's only write target is `master-data.md` on `main`.
- Match JD topics to transcript courses by judgment, not string-matching.
- Scope every claim to what the official course description actually verifies — never
  claim a JD's full phrase if only part of it is supported.
- Batch every unresolved/ambiguous course into one round of questions at the end of
  the run — never interrupt per-course, never guess.
- No new lookup infrastructure (no scraper, no cached catalog store) — ordinary web
  search is sufficient.
- The transcript itself never gets copied into the repo or committed; only course
  numbers/titles derived from it leave the local session, as search query terms.

---

## File Structure

```
CVApplicate/                                         (~/Desktop/CVApplicate)
├── plugins/cvapplicate/
│   ├── .claude-plugin/plugin.json                    [modify: version + description]
│   └── skills/cv-add-coursework/SKILL.md             [create]
├── .claude-plugin/marketplace.json                   [modify: description]
└── README.md                                         [modify: skills table, Daily use, 3× "five"→"six"]
```

---

## Task 1: Write the `cv-add-coursework` skill and bump the plugin version

**Files:**
- Create: `plugins/cvapplicate/skills/cv-add-coursework/SKILL.md`
- Modify: `plugins/cvapplicate/.claude-plugin/plugin.json`

- [ ] **Step 1: Confirm starting state**

Run: `cd ~/Desktop/CVApplicate && git status --short && git branch --show-current`
Expected: current branch is `main`; the only output is the known stray untracked
items (`.claude/` and `docs/superpowers/plans/2026-08-14-job-postings-fetcher-implementation.md`)
left over from earlier unrelated work — don't touch them. No other uncommitted
changes should be present (the previous task already committed the spec file).

- [ ] **Step 2: Write the skill**

Create `plugins/cvapplicate/skills/cv-add-coursework/SKILL.md`:

```markdown
---
name: cv-add-coursework
description: Given a transcript and a job description, verify which JD-named coursework the user has actually taken, look up the official course description, and enrich master-data.md's Coursework line with grounded detail. Use when a job description names specific coursework (e.g. "Operating Systems," "Linear Algebra," "Relational Databases") that master-data.md doesn't yet reflect accurately.
---

# CV Add Coursework

Given a transcript and a job description, verifies which JD-named coursework the
user has genuinely taken, looks up the official course description, and enriches
`master-data.md`'s `Coursework:` line with grounded, verified detail.

## When to use

A job description names specific coursework as a qualification (e.g. "Relational
Databases," "Linear Algebra & Numerical Methods," "Operating Systems
memory/resource management") and `master-data.md`'s `Coursework:` line doesn't yet
reflect it accurately. This is separate from `cv-review`: it only ever touches
`master-data.md` on `main`, never `cv.tex` — run `cv-review` afterward to pull the
newly-enriched coursework onto a specific branch's CV.

## Inputs needed

1. **A transcript** — file path to a PDF, or the user pastes the course list as
   text.
2. **A job description** — pasted text, or a URL to fetch. If a URL is given, try
   fetching it first; if the fetch fails or returns unusable content, ask the user
   to paste the text instead.

No industry/branch input is needed. This skill only ever touches `master-data.md`
on `main`, so whichever branch is currently checked out doesn't matter and never
gets switched away from without switching back.

## Procedure

1. Run `git status` to confirm the working tree is clean. If not, stop and tell the
   user what's uncommitted.
2. Run `git checkout main`.
3. Read the transcript in full and extract every course (department, number,
   title, term, grade). No web calls yet.
4. Read the JD and extract topic/skill phrases that plausibly map to coursework —
   the underlying concepts, not just literal course titles (e.g. "Distributed
   Systems" or "Linear Algebra & Numerical Methods" name topics a course might
   cover under an entirely different title).
5. Read `master-data.md`'s current `Coursework:` line.
6. Match JD topics against transcript courses using judgment, not string-matching.
   - Skip any match already fully represented with topic detail in
     `master-data.md`.
   - Drop any JD topic with no plausible transcript match at all — this is a gap
     to report later, not a reason to search harder for a stretch.
7. For each remaining candidate, web-search the official university course
   description (department site or course catalog first; a syllabus PDF as a
   fallback if the department page doesn't turn one up).
8. **Scope every claim to what the description actually verifies, not to the JD's
   full phrase.** If a JD phrase has multiple parts and the official description
   only supports some of them, claim only the supported subset — never the JD's
   complete wording just because it's convenient.
9. Anything not confidently matched or found — an ambiguous transcript entry, no
   official description locatable, a description that doesn't clearly cover the
   JD topic — gets held back, not guessed. Collect every such case.
10. If step 9 produced any held-back cases, ask the user about all of them in a
    single batched message, and wait for a response before continuing. Never
    interrupt per-course.
11. Edit `master-data.md`'s `Coursework:` line, extending it with parenthetical
    topic detail for each newly-verified course, matching the file's existing
    parenthetical style (e.g. `Discrete Math (Graph Theory, Combinatorics,
    Bayesian Probability)`).
12. Commit: `git add master-data.md && git commit -m "Add coursework detail for <Company> JD from transcript"`.
13. Report to the user: which courses were added (with the verified detail and
    its source), which JD-named topics were already covered, which JD-named
    topics had no transcript match at all (a gap, stated plainly), and a
    reminder to run `cv-review` next if they want this reflected on a specific
    branch's `cv.tex`.

## Error handling

- Dirty working tree at step 1 → stop, do not check out `main`.
- JD URL unreachable → ask the user to paste the text.
- Transcript unreadable or not provided → ask the user to provide it; do not
  proceed without it.
- No JD-relevant courses found on the transcript at all → report that plainly,
  make no edit, no commit.
- Web lookup down entirely, or no official description locatable for a given
  course → treat as unmatched (step 9); batch into the end-of-run questions,
  never guess a description from the course title alone.
- A JD topic only partially verified → claim only the verified subset (step 8);
  note the unclaimed remainder as a gap in the final report, not a silent
  omission.
- `master-data.md` showing up as modified on an industry branch afterward →
  wrong place; revert it there and redo the edit on `main`.

## Privacy

The transcript itself (grades, GPA, full course history) is read transiently for
this run and never copied into the repo or committed — only course numbers/titles
derived from it ever leave the local session, and only as web-search query terms,
never grades or other transcript content.
```

- [ ] **Step 3: Verify frontmatter parses**

Run: `cd ~/Desktop/CVApplicate && python3 -c "import yaml; text=open('plugins/cvapplicate/skills/cv-add-coursework/SKILL.md').read(); fm=text.split('---')[1]; print(yaml.safe_load(fm))"`
Expected: prints `{'name': 'cv-add-coursework', 'description': '...'}` with no
errors.

- [ ] **Step 4: Bump the plugin version and description**

Read `plugins/cvapplicate/.claude-plugin/plugin.json`. It currently reads:

```json
{
  "name": "cvapplicate",
  "description": "Turns 'paste my CV and a JD into an AI' into a repeatable, git-backed pipeline: score a CV against a job description, fix the weakest points, catch AI-writing smells, rank application-form skill keywords, and log every application's outcome.",
  "version": "1.0.1",
  "author": {
    "name": "Ozan Kan",
    "url": "https://github.com/ozikan5"
  }
}
```

Replace it with:

```json
{
  "name": "cvapplicate",
  "description": "Turns 'paste my CV and a JD into an AI' into a repeatable, git-backed pipeline: score a CV against a job description, fix the weakest points, catch AI-writing smells, rank application-form skill keywords, verify and enrich coursework from a transcript, and log every application's outcome.",
  "version": "1.1.0",
  "author": {
    "name": "Ozan Kan",
    "url": "https://github.com/ozikan5"
  }
}
```

(A new skill is a minor feature addition, not a patch — hence 1.0.1 → 1.1.0, not
1.0.2. The prior version bump, 1.0.0 → 1.0.1, accompanied a behavior-only change
to an existing skill, which is why it was a patch bump.)

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/CVApplicate
git add plugins/cvapplicate/skills/cv-add-coursework/SKILL.md plugins/cvapplicate/.claude-plugin/plugin.json
git commit -m "Add cv-add-coursework skill"
```

---

## Task 2: Validate end-to-end against a real course-lookup fixture

**Files:** none permanently changed. `master-data.md` gets temporarily edited during
this task and reverted at the end (Step 8); a scratch transcript file is created and
deleted (Steps 2 and 9). Nothing here is committed.

This skill's core mechanism — verifying a claim against a real, currently-published
course description — cannot be exercised against the template's fictional "Example
University" (it has no real web presence to search). This task temporarily
substitutes a real, well-documented university for the validation run only, using
publicly-published course numbers (not personal transcript data — course catalog
entries are public information), then reverts everything.

- [ ] **Step 1: Confirm clean state before starting**

Run: `cd ~/Desktop/CVApplicate && git status --short`
Expected: only the known stray untracked items from Task 1 Step 1 — nothing else.

- [ ] **Step 2: Create the scratch transcript fixture**

Create `test-transcript.txt` (repo root, untracked — never `git add` this):

```
Northwestern University — Test Transcript
(Validation fixture for cv-add-coursework — not committed, not real personal data)

COMP_SCI 214 — Data Structures & Algorithms — Grade A
COMP_SCI 343 — Operating Systems — Grade A
COMP_SCI 339 — Intro to Databases — Grade A
ARTHIST 101 — Introduction to Art History — Grade B+
```

(Real Northwestern course numbers are used deliberately, so the skill's web-search
step has genuine, currently-published official descriptions to find. This is a
throwaway file, not permanent template content.)

- [ ] **Step 3: Temporarily point `master-data.md` at the same university**

The skill needs to know which university's course catalog to search — it reads that
from `master-data.md`'s Education section. Open `master-data.md` and find:

```markdown
**Example University** — B.S. in Computer Science, Expected May 2027
- GPA: 3.8/4.0
- Relevant coursework: Data Structures & Algorithms, Operating Systems, Machine Learning
```

Temporarily change the first line to:

```markdown
**Northwestern University** — B.S. in Computer Science, Expected May 2027
```

Run: `git status --short`
Expected: `M master-data.md` (one line changed), plus the untracked
`test-transcript.txt` from Step 2 and the known stray items from Step 1.

- [ ] **Step 4: Run `cv-add-coursework` with a JD that exercises every path**

Follow `plugins/cvapplicate/skills/cv-add-coursework/SKILL.md` exactly, with:

- **Transcript:** `test-transcript.txt` from Step 2.
- **Job description:**

```
Software Engineer Intern — TestCo

Qualifications:
- Coursework or experience in: Data Structures & Algorithms, Operating Systems
  (memory/resource management), Relational Databases, Distributed Systems.
```

This JD is deliberately built to exercise three distinct outcomes in one run:
- **Data Structures & Algorithms** and **Operating Systems** should both resolve —
  real courses, real official descriptions available.
- **Relational Databases** should resolve via `COMP_SCI 339: Intro to Databases`,
  whose official description covers the relational model (a title-vs-topic mismatch,
  exercising the judgment-based matching in Procedure step 6).
- **Distributed Systems** has no matching course anywhere on the fixture transcript
  and must NOT be fabricated — it should surface as a gap in the final report
  (Procedure step 13), not as an invented `master-data.md` entry.

- [ ] **Step 5: Verify the `master-data.md` edit**

Run: `cd ~/Desktop/CVApplicate && git diff master-data.md`
Expected, all of the following:
- The `Coursework:` (or "Relevant coursework:") line now includes an entry for
  **Data Structures & Algorithms**.
- It includes an entry for **Operating Systems** with a parenthetical mentioning
  memory management and/or scheduling/resource management — the official
  `COMP_SCI 343` description covers exactly this (confirmed via a Northwestern
  McCormick Engineering course-description page during this project's design work).
- It includes an entry for a databases course (however the skill titles it — "Database
  Systems" or "Intro to Databases" are both acceptable) with a parenthetical
  mentioning the relational model — the official `COMP_SCI 339` description covers
  this.
- **"Distributed Systems" does NOT appear anywhere in the diff.** If it does, the
  skill fabricated a claim with no transcript backing — this is a failure; fix the
  skill's Procedure section (most likely step 6's matching logic or step 8's
  scoping-down behavior) before proceeding.
- **ARTHIST 101 / Art History does NOT appear anywhere in the diff.** If it does,
  the skill added JD-irrelevant coursework — a scope failure; fix the skill's step 6
  ("drop any JD topic with no plausible transcript match") before proceeding.

- [ ] **Step 6: Verify the gap was reported**

Check the skill's chat output from Step 4 against Procedure step 13's requirements:
- **Distributed Systems** is explicitly named as a gap with no transcript match.
- Each added course names where its detail came from (e.g. "per the official
  Northwestern course description").
- A reminder to run `cv-review` next appears.

Expected: all three present. If the gap isn't stated plainly, fix the skill's step
13 wording before proceeding.

- [ ] **Step 7: Confirm no other file was touched**

Run: `git status --short`
Expected: `M master-data.md`, `?? test-transcript.txt`, plus the known stray items
from Task 1 Step 1. In particular, `cv.tex` must NOT appear as modified — if it
does, the skill violated its core "never touches cv.tex" constraint; this is a
failure requiring a fix to the skill before proceeding.

- [ ] **Step 8: Revert the `master-data.md` edit**

Run: `git checkout -- master-data.md && git diff --stat master-data.md`
Expected: no output from the `diff --stat` (file back to its committed state).

- [ ] **Step 9: Remove the scratch transcript**

Run: `rm test-transcript.txt && git status --short`
Expected: back to only the known stray items from Task 1 Step 1 — nothing else.

---

## Task 3: Document the skill in README.md and marketplace.json

**Files:**
- Modify: `README.md`
- Modify: `.claude-plugin/marketplace.json`

- [ ] **Step 1: Update the marketplace description**

In `.claude-plugin/marketplace.json`, find:

```json
      "description": "Five CV-editing skills: score/fix a CV against a job description, branch new industry variants, catch AI-writing smells, rank application-form skill keywords, and log outcomes."
```

Replace with:

```json
      "description": "Six CV-editing skills: score/fix a CV against a job description, branch new industry variants, catch AI-writing smells, rank application-form skill keywords, verify and enrich coursework from a transcript, and log outcomes."
```

- [ ] **Step 2: Update the three "five skills" mentions in README.md**

In `README.md`, find and replace each of these three lines individually (they are
not adjacent):

Find: `weak points, and submit — this packages that loop into five skills, backed by`
Replace: `weak points, and submit — this packages that loop into six skills, backed by`

Find: `│   └── skills/                       The five skills below`
Replace: `│   └── skills/                       The six skills below`

Find: `This installs the five skills once, available in any directory. When this repo's skills`
Replace: `This installs the six skills once, available in any directory. When this repo's skills`

- [ ] **Step 3: Add a row to the skills table**

In `README.md`, find:

```markdown
| **cv-application-skills** | Ranks the top skill keywords for a job application's Skills field, from a JD |
```

Add immediately after it:

```markdown
| **cv-add-coursework** | Verifies JD-named coursework against a transcript and enriches `master-data.md` with the official course description |
```

- [ ] **Step 4: Add a "Daily use" section**

In `README.md`, find the `## Reviewing your CV against a job posting` heading. Add
a new section immediately before it (so it reads as the natural first step for a JD
that names specific coursework, ahead of the `cv-review` pass that would pull the
result onto a branch's `cv.tex`):

~~~markdown
## Verifying coursework against a transcript

```
Run cv-add-coursework with my transcript at <path>, for this JD: <paste or URL>
```

When a job description names specific coursework (e.g. "Operating Systems," "Linear
Algebra," "Relational Databases") that your `master-data.md` doesn't yet reflect
accurately, this cross-references the JD's asks against your actual transcript,
looks up each course's official description, and enriches the `Coursework:` line
with verified detail — never inventing a course, and never scoping a claim past
what the official description actually supports. Anything ambiguous or
unverifiable gets batched into one round of questions at the end, rather than
guessed. Run `cv-review` afterward to pull the newly-verified coursework onto a
specific branch's `cv.tex`.

~~~

- [ ] **Step 5: Update the Status section**

Find:

```markdown
All five skills are implemented and validated end-to-end as skills; the plugin/marketplace
```

Replace with:

```markdown
All six skills are implemented and validated end-to-end as skills; the plugin/marketplace
```

- [ ] **Step 6: Verify placement and every replacement landed**

Run: `cd ~/Desktop/CVApplicate && grep -n "five\|six" README.md .claude-plugin/marketplace.json`
Expected: every remaining `five`/`Five` hit is inside
`docs/superpowers/plans/2026-08-12-cv-review-pipeline-implementation.md`-style
historical records only (none in `README.md` or `marketplace.json` — if `grep` is
run exactly as above, those files are the only ones searched, so any hit at all in
this output is a mistake to fix); every `six`/`Six` hit lands in the four `README.md`
spots plus the one `marketplace.json` spot from Steps 1-2 and 5.

- [ ] **Step 7: Commit**

```bash
cd ~/Desktop/CVApplicate
git add README.md .claude-plugin/marketplace.json
git commit -m "Document cv-add-coursework in README"
```

---

## Notes on what's intentionally out of scope

- **No sync into `~/Desktop/CV-personal`.** Unlike the pre-plugin era (see the
  `cv-application-skills` implementation plan's Task 4), skills are no longer
  copied file-by-file into a personal fork — `CV-personal` picks up this skill via
  `/plugin update cvapplicate`, run by the user whenever they're ready. There is
  nothing for this plan to do there.
- **`CV-personal`'s own `README.md`** still says "five skills" by name. That's the
  user's own fork's prose documentation, not part of this plugin's implementation —
  out of scope here, same as it wasn't touched in prior skill additions in this
  plan's precedent.
