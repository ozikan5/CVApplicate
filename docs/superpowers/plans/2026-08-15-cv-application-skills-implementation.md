# cv-application-skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fifth Claude Code skill, `cv-application-skills`, that reads a job description plus `master-data.md`/`claims-guardrails.md` and reports a ranked list of the 10 skill keywords best suited for an application portal's free-text "Skills" field — read-only, no branch switching, no commits — then document it in the README and sync it into the personal fork at `~/Desktop/CV-personal`.

**Architecture:** A single self-contained Markdown instruction file at `.claude/skills/cv-application-skills/SKILL.md`, written and validated on `main` in `CVApplicate` (matching how the other four skills were built), following `docs/superpowers/specs/2026-08-15-cv-application-skills-design.md`. Validated by actually running it against the template's placeholder ("Jane Doe") `master-data.md` with a sample JD and inspecting the report — no git state changes to roll back, since the skill never writes anything. The finished skill and README changes are then copied into the personal fork the same way `check-cv-text.py` was synced earlier this session.

**Tech Stack:** Claude Code Skills (Markdown + YAML frontmatter). No application code.

---

## File Structure

```
CVApplicate/
├── .claude/skills/cv-application-skills/SKILL.md   # the skill itself
└── README.md                                        # new skills-table row + "Daily use" section

CV-personal/ (personal fork, synced after CVApplicate is done)
├── .claude/skills/cv-application-skills/SKILL.md   # copy of the above
└── README.md                                        # copy of the same doc changes
```

---

## Task 1: Write the `cv-application-skills` skill

**Files:**
- Create: `.claude/skills/cv-application-skills/SKILL.md` (in `~/Desktop/CVApplicate`)

- [ ] **Step 1: Confirm starting state**

Run: `cd ~/Desktop/CVApplicate && git status --short && git branch --show-current`
Expected: current branch is `main`; no unexpected uncommitted changes (untracked
`.claude/worktrees/` and a stray `docs/superpowers/plans/2026-08-14-job-postings-fetcher-implementation.md` from earlier unrelated work are fine to see — don't touch them).

- [ ] **Step 2: Write the skill**

Create `.claude/skills/cv-application-skills/SKILL.md`:

```markdown
---
name: cv-application-skills
description: Generate a ranked list of skill keywords for an application portal's free-text "Skills" field, tailored to a specific job description and grounded in master-data.md. Use when the user needs to fill in a "top skills" field on a job application, separate from the CV document itself.
---

# CV Application Skills

Given a job description, produces a ranked list of the 10 skill keywords best suited
for an application portal's free-text "Skills" field — a field that exists on many
application forms independent of whatever resume gets uploaded (Workday-style tag
pickers, "list your top skills" boxes).

## When to use

The user wants a list of skill keywords to paste into a job application's Skills
field, or explicitly invokes this skill. This is separate from `cv-review`: no CV
editing, no scoring, no logging — just a tailored keyword list, read-only.

## Inputs needed

1. **Job description** — pasted text, or a URL to fetch. If a URL is given, try
   fetching it first; if the fetch fails or returns unusable content, ask the user to
   paste the text instead.
2. **Count** (optional) — defaults to 10. Only ask if the user specifies a different
   number.

No industry/branch input is needed. This skill reads `master-data.md` directly,
which holds the full experience bank across every branch, so whichever branch is
currently checked out doesn't matter and never gets switched.

## Procedure

1. Read `master-data.md` (full experience bank) and `claims-guardrails.md` (binding
   constraints on how any claim may be phrased/scoped) in full. If
   `claims-guardrails.md` is missing, proceed but say so in the report and be
   conservative about what counts as "grounded."
2. Extract the JD's explicit skill, technology, and competency terms.
3. Cross-reference those terms — and general relevant competencies — against
   everything demonstrated in `master-data.md`, not just its dedicated Skills
   section. A skill evidenced only in an Experience or Project bullet still counts.
4. Rank candidates and select the top N (10 by default). When a skill is genuinely
   grounded, prefer phrasing it the way the JD itself phrases it — this is a
   tie-breaker on wording, never a reason to stretch a claim past what step 5 allows.
5. Never include a skill not grounded in `master-data.md`, and never phrase one in a
   way `claims-guardrails.md` prohibits (e.g. don't suggest "Kubernetes" if the only
   grounding is "used Docker once" — that's not the same skill).
6. Identify JD-emphasized skills that have no grounded support in `master-data.md` at
   all. If fewer than N skills are honestly supportable, return however many are and
   say so — never pad the list with weak or ungrounded entries to hit the count.

## Output

Report directly to the user, nothing written to any file:
- The N skills, each with a one-line reason tying it to specific grounded experience.
- A short **gaps** note: JD-emphasized skills excluded because there's no grounded
  support for them, stated plainly.

## Error handling

- `master-data.md` missing → stop, tell the user it's required before this or any
  other review skill can run.
- `claims-guardrails.md` missing → proceed, note it in the report, be conservative.
- JD URL unreachable → ask the user to paste the text.
- Fewer than N genuinely grounded, JD-relevant skills exist → return what's honestly
  supportable and say so.
```

- [ ] **Step 3: Verify frontmatter parses**

Run: `python3 -c "import yaml; text=open('.claude/skills/cv-application-skills/SKILL.md').read(); fm=text.split('---')[1]; print(yaml.safe_load(fm))"`
Expected: prints `{'name': 'cv-application-skills', 'description': '...'}` with no
errors.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/cv-application-skills/SKILL.md
git commit -m "Add cv-application-skills skill"
```

---

## Task 2: Validate end-to-end against the placeholder CV

**Files:** none permanently changed — this skill never writes to any file, so unlike
the other skills' validation tasks, there's no git state to roll back afterward.

- [ ] **Step 1: Temporarily stage a guardrails file for the test**

The template ships `claims-guardrails.example.md` but not `claims-guardrails.md`
(the latter is meant to be created by a user forking the repo). To validate the
happy path (guardrails present) rather than only the fallback path, copy it in for
the duration of this task:

Run: `cd ~/Desktop/CVApplicate && cp claims-guardrails.example.md claims-guardrails.md && git status --short`
Expected: `?? claims-guardrails.md` (untracked, not yet committed to anything — this
stays untracked for the whole task and gets deleted at the end).

- [ ] **Step 2: Run `cv-application-skills` with a sample job description**

Follow `.claude/skills/cv-application-skills/SKILL.md` exactly, with this input
(same sample JD used to validate `cv-review` in the original pipeline, for
consistency):

```
Software Engineer Intern — TestCo

We're looking for a Software Engineer Intern to join our backend team. You'll
work on our REST API services, contribute to our Python microservices, and
collaborate with senior engineers on distributed systems challenges.

Requirements:
- Currently pursuing a B.S./M.S. in Computer Science or related field
- Proficient in Python; familiarity with Java or C++ a plus
- Understanding of REST APIs and basic distributed systems concepts
- Experience with Git and collaborative development workflows
- Strong communication skills
```

- [ ] **Step 3: Verify the report structure**

Check the skill's output from Step 2 against these requirements:
- Exactly 10 skills listed (or fewer, with an explicit note saying why, per the
  Error handling section — either is acceptable, but if fewer than 10, the note must
  be present).
- Each of the 10 (or fewer) skills has a one-line reason citing something specific
  from `master-data.md` (not a generic restatement of the JD).
- A **gaps** section is present, naming at least one JD-emphasized term Jane Doe's
  placeholder data doesn't support (e.g. "microservices" — nothing in `master-data.md`
  uses that word or describes a multi-service architecture).
- "Python," "distributed systems," and "Git" appear in the list — all three are
  explicitly grounded in `master-data.md`'s Skills section, and all three are
  explicitly named in the sample JD, so their absence would indicate a bug in the
  skill's cross-referencing logic, not a legitimate judgment call.
- Nothing resembling "Kubernetes," "microservices," or other terms absent from
  `master-data.md` appears in the 10 (they may appear in the gaps note — that's
  correct; they must not appear in the recommended list itself).

Expected: all of the above hold. If any fail, the skill's Procedure section needs a
fix before proceeding — do not move on to Task 3 with a broken skill.

- [ ] **Step 4: Confirm no file was written**

Run: `git status --short`
Expected: still only `?? claims-guardrails.md` (the file staged in Step 1) — nothing
else appears as modified or new. If anything else shows up, the skill wrote
something it shouldn't have; investigate before proceeding.

- [ ] **Step 5: Remove the temporary guardrails file**

Run: `rm claims-guardrails.md && git status --short`
Expected: clean output (nothing shown) — back to the pre-Task-2 state.

---

## Task 3: Document the skill in README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a row to the skills table**

In `README.md`, find:

```markdown
| **cv-sanity-check** | Finds and fixes writing that reads as AI-generated |
```

Add immediately after it:

```markdown
| **cv-application-skills** | Ranks the top skill keywords for a job application's Skills field, from a JD |
```

- [ ] **Step 2: Add a "Daily use" section**

In `README.md`, find the `## Recording what happened` section (it ends right before
the `---` that precedes `# Guardrails`). Add a new section immediately before that
`---`. The exact text to insert (including its own triple-backtick fence around the
`Run cv-application-skills...` example, matching the style of the sibling sections
like `## Recording what happened` above it) is:

~~~markdown
## Filling in an application's "Skills" field

```
Run cv-application-skills for this JD: <paste or URL>
```

Many application portals ask for a separate list of skill keywords, independent of
whatever CV you upload. This reads `master-data.md` and reports the 10 best-fitting
ones for the posting, each with the specific experience it's grounded in, plus a gap
note for anything the JD emphasizes that your experience doesn't support. Nothing
gets written anywhere — copy the list into the application yourself.
~~~

- [ ] **Step 3: Verify placement**

Run: `grep -n "^#\|^## " README.md`
Expected: `cv-application-skills` row appears in the skills table listing, and the
new `## Filling in an application's "Skills" field` heading appears between
`## Recording what happened` and `# Guardrails`, at the same heading level as its
sibling `## Recording what happened`/`## Checking it doesn't read as AI-written`
sections.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Document cv-application-skills in README"
```

---

## Task 4: Sync into the personal fork

**Files:**
- Create: `~/Desktop/CV-personal/.claude/skills/cv-application-skills/SKILL.md`
- Modify: `~/Desktop/CV-personal/README.md`

- [ ] **Step 1: Confirm the personal fork's branch and clean state**

Run: `cd ~/Desktop/CV-personal && git branch --show-current && git status --short`
Expected: currently on `main` (this skill file and the README are both main-only
content, same category as `check-cv-text.py`/`claims-guardrails.example.md` synced
earlier — not per-industry-branch content); no unexpected uncommitted changes.

If not on `main`, run: `git checkout main` first (confirm the tree is clean before
switching, per this repo's standing rule of never switching branches with
uncommitted changes).

- [ ] **Step 2: Copy the skill file**

```bash
mkdir -p ~/Desktop/CV-personal/.claude/skills/cv-application-skills
cp ~/Desktop/CVApplicate/.claude/skills/cv-application-skills/SKILL.md \
   ~/Desktop/CV-personal/.claude/skills/cv-application-skills/SKILL.md
```

- [ ] **Step 3: Apply the same README changes**

Read `~/Desktop/CV-personal/README.md` and apply the identical two edits from Task 3
(Steps 1-2) — the skills-table row and the "Daily use" section — at the same
locations. (The personal fork's README diverged slightly from the template's over
the course of this session, so re-read it fresh rather than assuming line numbers
match; find the same anchor text — `cv-sanity-check` table row, and the
`## Recording what happened` section — instead.)

- [ ] **Step 4: Verify**

Run: `cd ~/Desktop/CV-personal && diff ~/Desktop/CVApplicate/.claude/skills/cv-application-skills/SKILL.md .claude/skills/cv-application-skills/SKILL.md && echo "identical"`
Expected: prints `identical` with no diff output above it.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/cv-application-skills/SKILL.md README.md
git commit -m "Add cv-application-skills skill (synced from CVApplicate)"
```
