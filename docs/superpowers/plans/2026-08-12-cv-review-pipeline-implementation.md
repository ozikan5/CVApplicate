# CV Review Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the four Claude Code skills (`cv-review`, `cv-new-industry`, `cv-log-outcome`, `cv-sanity-check`) and the placeholder repo content (`cv.tex`, `master-data.md`, `applications/log.yaml`) described in `docs/superpowers/specs/2026-08-12-cv-review-pipeline-design.md`, then validate each skill end-to-end.

**Architecture:** All four skills are self-contained Markdown instruction files under `.claude/skills/<name>/SKILL.md`, written directly against placeholder ("Jane Doe") content so the whole system is exercisable without any real personal data. Skills are written on `main` first so every industry branch inherits all four automatically; industry branches are then created by actually running `cv-new-industry`, and the other three skills are validated by actually running them and inspecting the resulting git state and files, then rolling back the throwaway validation commits.

**Tech Stack:** Git (branches as the version-control model), Claude Code Skills (Markdown + YAML frontmatter), LaTeX (CV content), YAML (application log).

---

### Task 1: Placeholder `cv.tex`

**Files:**
- Create: `cv.tex`

- [ ] **Step 1: Write the placeholder LaTeX CV**

```latex
\documentclass[10pt]{article}
\usepackage[margin=0.75in]{geometry}
\usepackage{enumitem}
\usepackage{titlesec}
\usepackage{hyperref}

\pagestyle{empty}
\setlist[itemize]{leftmargin=*, itemsep=1pt, topsep=2pt}
\titleformat{\section}{\large\bfseries}{}{0em}{}[\titlerule]
\titlespacing{\section}{0pt}{8pt}{4pt}

\begin{document}

\begin{center}
    {\LARGE \textbf{Jane Doe}} \\
    \vspace{2pt}
    jane.doe@example.edu \quad | \quad (555) 123-4567 \quad | \quad
    \href{https://linkedin.com/in/janedoe}{linkedin.com/in/janedoe} \quad | \quad
    \href{https://github.com/janedoe}{github.com/janedoe}
\end{center}

\section*{Education}
\textbf{Example University} \hfill Expected May 2027 \\
B.S. in Computer Science, GPA: 3.8/4.0 \\
Relevant coursework: Data Structures \& Algorithms, Operating Systems, Machine Learning

\section*{Experience}
\textbf{Software Engineering Intern} -- Example Corp \hfill Jun 2025 -- Aug 2025
\begin{itemize}
    \item Built a caching layer for the internal analytics API, reducing average query latency from 800ms to 150ms
    \item Wrote integration tests covering 40 previously-untested API endpoints, raising backend test coverage from 55\% to 82\%
    \item Presented findings from a performance audit to the engineering team, leading to adoption of a new database indexing strategy
\end{itemize}

\textbf{Research Assistant} -- Example University AI Lab \hfill Jan 2025 -- Present
\begin{itemize}
    \item Implemented a data preprocessing pipeline for a 200k-sample text classification dataset, cutting preparation time from 3 hours to 20 minutes
    \item Co-authored a workshop paper on few-shot learning evaluation methodology
\end{itemize}

\section*{Projects}
\textbf{Course Scheduler} -- Personal Project
\begin{itemize}
    \item Built a constraint-solver-based scheduling tool in Python that generates conflict-free course schedules from a student's requirement list
    \item Deployed as a web app used by approximately 150 students in one academic term
\end{itemize}

\section*{Skills}
\textbf{Languages:} Python, Java, C++, SQL \\
\textbf{Tools/Frameworks:} PyTorch, React, Docker, Git \\
\textbf{Other:} Data structures \& algorithms, distributed systems fundamentals

\end{document}
```

- [ ] **Step 2: Verify it's on `main` and the tree is otherwise clean**

Run: `git status --short && git branch --show-current`
Expected: `?? cv.tex` and current branch is `main`.

- [ ] **Step 3: Commit**

```bash
git add cv.tex
git commit -m "Add placeholder LaTeX CV"
```

---

### Task 2: Placeholder `master-data.md`

**Files:**
- Create: `master-data.md`

- [ ] **Step 1: Write the source-of-truth experience bank**

```markdown
# Master Data — Jane Doe

Source of truth for all CV content. Industry-specific `cv.tex` files on each branch
select, reorder, and reword a subset of this material — they do not duplicate it
independently. When a review skill improves a bullet's phrasing, the matching entry
here gets updated too.

## Education

**Example University** — B.S. in Computer Science, Expected May 2027
- GPA: 3.8/4.0
- Relevant coursework: Data Structures & Algorithms, Operating Systems, Machine Learning

## Experience

### Software Engineering Intern — Example Corp (Jun 2025 – Aug 2025)
- Built a caching layer for the internal analytics API, reducing average query
  latency from 800ms to 150ms
- Wrote integration tests covering 40 previously-untested API endpoints, raising
  backend test coverage from 55% to 82%
- Presented findings from a performance audit to the engineering team, leading to
  the adoption of a new database indexing strategy

### Research Assistant — Example University AI Lab (Jan 2025 – Present)
- Implemented a data preprocessing pipeline for a 200k-sample text classification
  dataset, cutting training set preparation time from 3 hours to 20 minutes
- Co-authored a workshop paper on few-shot learning evaluation methodology

## Projects

### Course Scheduler (Personal Project)
- Built a constraint-solver-based scheduling tool in Python that generates
  conflict-free course schedules from a student's requirement list
- Deployed as a web app used by ~150 students in one academic term

## Skills

- **Languages:** Python, Java, C++, SQL
- **Tools/Frameworks:** PyTorch, React, Docker, Git
- **Other:** Data structures & algorithms, distributed systems fundamentals
```

- [ ] **Step 2: Verify**

Run: `git status --short`
Expected: `?? master-data.md`

- [ ] **Step 3: Commit**

```bash
git add master-data.md
git commit -m "Add placeholder master-data.md"
```

---

### Task 3: Placeholder `applications/log.yaml`

**Files:**
- Create: `applications/log.yaml`

- [ ] **Step 1: Write the schema with one example entry**

```yaml
# Application history. See docs/superpowers/specs/2026-08-12-cv-review-pipeline-design.md
# for the full field reference. New entries are appended by the cv-review skill;
# outcome/outcome_date are updated by the cv-log-outcome skill.

- id: example-corp-swe-2026-08
  company: "Example Corp"
  role: "Software Engineer Intern"
  industry_branch: swe
  date_applied: 2026-08-12
  jd_source: pasted
  jd_url: null
  jd_summary: "Backend-focused SWE internship requiring Python, distributed systems familiarity, and experience with REST APIs."
  cv_commit: "0000000000000000000000000000000000000"
  base_quality_score:
    total: 82
    impact: 78
    competencies: 85
    presentation: 80
  jd_fit_score:
    total: 74
    keyword_match: 70
    experience_relevance: 80
    seniority_fit: 70
  weak_points_fixed:
    - "Bullet 3 in the Research Assistant entry lacked a quantified outcome"
    - "Skills section didn't surface REST API experience explicitly requested in the JD"
    - "Course Scheduler project bullet used passive voice"
  outcome: pending
  outcome_date: null
```

- [ ] **Step 2: Verify it's valid YAML**

Run: `python3 -c "import yaml; print(yaml.safe_load(open('applications/log.yaml')))"`
Expected: prints a Python list containing one dict, no errors. (If `python3`/`pyyaml`
isn't available, visually inspect indentation instead — every key under an entry must
align two spaces deeper than the `- id:` line.)

- [ ] **Step 3: Commit**

```bash
git add applications/log.yaml
git commit -m "Add applications log with example entry"
```

---

### Task 4: `cv-new-industry` skill

**Files:**
- Create: `.claude/skills/cv-new-industry/SKILL.md`

- [ ] **Step 1: Write the skill**

```markdown
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
```

- [ ] **Step 2: Verify frontmatter parses**

Run: `python3 -c "import yaml,re; text=open('.claude/skills/cv-new-industry/SKILL.md').read(); fm=text.split('---')[1]; print(yaml.safe_load(fm))"`
Expected: prints `{'name': 'cv-new-industry', 'description': '...'}` with no errors.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/cv-new-industry/SKILL.md
git commit -m "Add cv-new-industry skill"
```

---

### Task 5: `cv-review` skill

**Files:**
- Create: `.claude/skills/cv-review/SKILL.md`

- [ ] **Step 1: Write the skill**

```markdown
---
name: cv-review
description: Score a CV against a specific job description, fix the weakest points, and log the application. Use when the user wants to check their CV's fit for a job posting before applying, or asks to "review my CV against this JD".
---

# CV Review

Scores a CV two ways — general quality and fit to a specific job — fixes the three
weakest points found across both scores, re-checks, and logs the application.

## When to use

The user gives you a job description (pasted text or a URL) and wants their CV
evaluated and improved before they submit it, or explicitly invokes this skill.

## Inputs needed

Ask for anything missing before starting:
1. **Industry/branch** — which industry-specific CV to review (e.g. `swe`, `ai-ml`).
   If unclear, ask; do not guess.
2. **Job description** — pasted text, or a URL to fetch. If a URL is given, try
   fetching it first; if the fetch fails or returns unusable content, ask the user to
   paste the text instead.
3. **Company and role name** — for the application log entry.

## Procedure

1. Run `git status` to confirm the working tree is clean. If not, stop and tell the
   user what's uncommitted — do not proceed until it's clean.
2. Run `git checkout <industry-branch>`.
3. Read `cv.tex` and `master-data.md` in full.
4. **Score Base Quality /100** using this rubric:
   - Impact (40%): strong action verbs, specificity, quantified outcomes
   - Competencies (35%): skills/qualifications vs. general expectations for the field
   - Presentation (25%): active voice, no filler words, appropriate bullet length, no
     over-usage of any single word/phrase
   - Compute `total` as the weighted sum of the three category scores (each 0-100).
5. **Score JD Fit /100** using this rubric:
   - Required skills/keyword match (40%): does the CV surface the specific
     skills/tools the JD asks for?
   - Experience relevance (40%): do past roles/projects map to the JD's actual
     responsibilities?
   - Seniority/level fit (20%): does the CV read as the right level for this posting?
   - Compute `total` as the weighted sum.
6. Pool weaknesses from both layers and pick the worst 3 overall (not 3 from each).
7. Edit `cv.tex` directly to fix those 3 weaknesses. If a fix involves rephrasing an
   experience bullet, also update the matching entry in `master-data.md` so the
   improved phrasing is available for future CVs.
8. Compile-check the edit using whichever of these is found first on the system:
   `latexmk`, then `pdflatex`, then `tectonic` (check with e.g. `which latexmk`).
   - If none are found, skip this step and note in your final report that
     compilation was not verified.
   - If found, compile `cv.tex`. On failure, run `git checkout -- cv.tex` to revert
     the edit, report the compile error to the user, and stop — do not commit.
9. Commit the `cv.tex` (and `master-data.md`, if changed) on the industry branch:
   `git add cv.tex master-data.md && git commit -m "Review: <company> <role>"`
10. Re-score both layers against the fixed `cv.tex` (repeat steps 4-6). This is the
    final check — report the before/after scores. Do not block on any threshold; the
    user decides if it's ready.
11. Switch to `main`: `git checkout main`.
12. Append an entry to `applications/log.yaml` with this shape:
    ```yaml
    - id: <company-slug>-<industry>-<yyyy-mm>
      company: "<company>"
      role: "<role>"
      industry_branch: <industry>
      date_applied: <today, YYYY-MM-DD>
      jd_source: pasted        # or url
      jd_url: <url or null>
      jd_summary: "<1-2 sentence AI-generated summary of the JD's key requirements>"
      cv_commit: <sha from step 9>
      base_quality_score:
        total: <int>
        impact: <int>
        competencies: <int>
        presentation: <int>
      jd_fit_score:
        total: <int>
        keyword_match: <int>
        experience_relevance: <int>
        seniority_fit: <int>
      weak_points_fixed:
        - "<weakness 1>"
        - "<weakness 2>"
        - "<weakness 3>"
      outcome: pending
      outcome_date: null
    ```
13. Commit: `git add applications/log.yaml && git commit -m "Log application: <company> <role>"`
14. Switch back to the industry branch: `git checkout <industry-branch>`.
15. Report to the user: initial Base/JD Fit scores, the 3 weaknesses fixed and why,
    and the final re-scored numbers.

## Error handling

- Dirty working tree at step 1 → stop, do not switch branches.
- JD URL unreachable → ask the user to paste the text.
- Compile failure at step 8 → revert, report, stop before committing.
```

- [ ] **Step 2: Verify frontmatter parses**

Run: `python3 -c "import yaml; text=open('.claude/skills/cv-review/SKILL.md').read(); fm=text.split('---')[1]; print(yaml.safe_load(fm))"`
Expected: prints `{'name': 'cv-review', 'description': '...'}` with no errors.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/cv-review/SKILL.md
git commit -m "Add cv-review skill"
```

---

### Task 6: `cv-log-outcome` skill

**Files:**
- Create: `.claude/skills/cv-log-outcome/SKILL.md`

- [ ] **Step 1: Write the skill**

```markdown
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
```

- [ ] **Step 2: Verify frontmatter parses**

Run: `python3 -c "import yaml; text=open('.claude/skills/cv-log-outcome/SKILL.md').read(); fm=text.split('---')[1]; print(yaml.safe_load(fm))"`
Expected: prints `{'name': 'cv-log-outcome', 'description': '...'}` with no errors.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/cv-log-outcome/SKILL.md
git commit -m "Add cv-log-outcome skill"
```

---

### Task 7: `cv-sanity-check` skill

**Files:**
- Create: `.claude/skills/cv-sanity-check/SKILL.md`

- [ ] **Step 1: Write the skill**

```markdown
---
name: cv-sanity-check
description: Scan a CV for AI-writing smells (buzzword overuse, repetitive phrasing, unnatural cadence, vague claims) and fix them. Use when the user wants to make sure their CV doesn't read as AI-generated, independent of a specific job review.
---

# CV Sanity Check

Scans the current branch's `cv.tex` for patterns that read as AI-generated writing,
and fixes them.

## Inputs needed

None required. Defaults to the currently checked-out branch's `cv.tex`. If the user
names a specific industry branch, checkout that branch first (after confirming the
working tree is clean).

## What to look for

Read every bullet in `cv.tex` and flag:
- **Buzzword overuse** — words like "spearheaded", "leveraged", "orchestrated",
  "utilized" appearing more than once or twice across the whole document
- **Repetitive sentence/verb openings** — multiple bullets starting with the same
  word or grammatical construction
- **Em-dash overuse** — more em dashes than a human resume would typically use
- **Generic filler phrases** — "responsible for", "worked on", "helped with" without
  a concrete outcome attached
- **Unnatural cadence** — bullets that all have near-identical sentence structure
  and length, reading as templated rather than varied
- **Inconsistent tense** — mixing past and present tense for equivalent
  (e.g. all-past-role) entries
- **Vague or unverifiable claims** — impact statements with no metric, scope, or
  concrete detail behind them
- **Unnaturally uniform bullet lengths** — every bullet being suspiciously close to
  the same character count

## Procedure

1. Run `git status` to confirm the working tree is clean. If not, stop and tell the
   user what's uncommitted.
2. Read `cv.tex` in full.
3. Identify every instance of the patterns above, with the specific bullet/line
   affected.
4. Edit `cv.tex` to fix each one — vary word choice, add concrete specifics where a
   claim is vague, fix tense consistency, vary sentence structure.
5. Compile-check the edit using whichever of these is found first on the system:
   `latexmk`, then `pdflatex`, then `tectonic`.
   - If none are found, skip this step and note in your final report that
     compilation was not verified.
   - If found, compile `cv.tex`. On failure, run `git checkout -- cv.tex` to revert,
     report the compile error, and stop — do not commit.
6. Commit: `git add cv.tex && git commit -m "Sanity check: fix AI-writing smells"`.
7. Report to the user exactly what was found and what was changed, bullet by bullet,
   so nothing is altered without them seeing why.

## Error handling

- Dirty working tree at step 1 → stop, do not edit.
- Compile failure at step 5 → revert, report, stop before committing.
- Nothing found → report that the CV reads fine, make no changes, no commit.
```

- [ ] **Step 2: Verify frontmatter parses**

Run: `python3 -c "import yaml; text=open('.claude/skills/cv-sanity-check/SKILL.md').read(); fm=text.split('---')[1]; print(yaml.safe_load(fm))"`
Expected: prints `{'name': 'cv-sanity-check', 'description': '...'}` with no errors.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/cv-sanity-check/SKILL.md
git commit -m "Add cv-sanity-check skill"
```

---

### Task 8: Create the real industry branches (validates `cv-new-industry`)

**Files:**
- Modify: `cv.tex` (once per branch, on each new branch)

At this point `main` has `cv.tex`, `master-data.md`, `applications/log.yaml`, and all
four `SKILL.md` files, so every branch created from here on inherits all of them.

- [ ] **Step 1: Confirm starting state**

Run: `git branch --show-current && git status --short`
Expected: current branch is `main`, no uncommitted changes.

- [ ] **Step 2: Run `cv-new-industry` for `swe`**

Follow `.claude/skills/cv-new-industry/SKILL.md` exactly, using `swe` as the industry
name. This means: checkout `main`, confirm `swe` doesn't already exist, create branch
`swe`, adapt `cv.tex` to emphasize backend/software-engineering-relevant bullets from
`master-data.md`, commit on `swe`, then return to `main`.

- [ ] **Step 3: Verify the `swe` branch**

Run: `git log swe --oneline -1 && git diff main swe -- cv.tex | head -20`
Expected: one commit on `swe` beyond `main`'s tip, and a non-empty diff showing
`cv.tex` was adapted (not byte-identical to `main`'s version).

- [ ] **Step 4: Run `cv-new-industry` for `ai-ml`**

Same as Step 2, with industry name `ai-ml`, emphasizing ML/AI-relevant bullets.

- [ ] **Step 5: Verify the `ai-ml` branch**

Run: `git log ai-ml --oneline -1 && git diff main ai-ml -- cv.tex | head -20`
Expected: one commit beyond `main`'s tip, non-empty diff.

- [ ] **Step 6: Run `cv-new-industry` for `quant-trading`**

Same as Step 2, with industry name `quant-trading`, emphasizing quantitative/
algorithmic bullets.

- [ ] **Step 7: Verify the `quant-trading` branch**

Run: `git log quant-trading --oneline -1 && git diff main quant-trading -- cv.tex | head -20`
Expected: one commit beyond `main`'s tip, non-empty diff.

- [ ] **Step 8: Run `cv-new-industry` for `data-science`**

Same as Step 2, with industry name `data-science`, emphasizing data-analysis-relevant
bullets.

- [ ] **Step 9: Verify the `data-science` branch and final state**

Run: `git log data-science --oneline -1 && git branch --show-current`
Expected: one commit beyond `main`'s tip; current branch is `main` (each run of the
skill returns to `main` in its final step).

No separate commit step here — each `cv-new-industry` run already committed on its
own branch per the skill's own procedure.

---

### Task 9: Validate `cv-review` end-to-end, then roll back the test data

**Files:**
- Modify (temporarily, then reverted): `swe` branch's `cv.tex`
- Modify (temporarily, then reverted): `applications/log.yaml`

- [ ] **Step 1: Record rollback points**

Run: `git rev-parse main swe`
Save both SHAs shown — call them `MAIN_BEFORE` and `SWE_BEFORE`. These are the commits
to reset back to after validation.

- [ ] **Step 2: Run `cv-review` with a sample job description**

Follow `.claude/skills/cv-review/SKILL.md` exactly, with these inputs:
- Industry/branch: `swe`
- Company: `TestCo`
- Role: `Software Engineer Intern`
- Job description (pasted text):
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

- [ ] **Step 3: Verify the scoring and commit structure**

Run: `git log swe --oneline -3 && git log main --oneline -2`
Expected: `swe` has a new "Review: TestCo Software Engineer Intern" commit beyond
`SWE_BEFORE`; `main` has a new "Log application: TestCo Software Engineer Intern"
commit beyond `MAIN_BEFORE`; current branch is back on `swe`.

- [ ] **Step 4: Verify the log entry structure**

Run: `git show main:applications/log.yaml | python3 -c "import yaml,sys; d=yaml.safe_load(sys.stdin); e=d[-1]; assert e['company']=='TestCo'; assert 0<=e['base_quality_score']['total']<=100; assert 0<=e['jd_fit_score']['total']<=100; assert len(e['weak_points_fixed'])==3; print('OK', e['id'])"`
Expected: prints `OK <id>` with no assertion errors.

- [ ] **Step 5: Confirm the report to the user included both score sets**

Check the skill's final report (from Step 2) named an initial Base Quality score,
an initial JD Fit score, the 3 weaknesses fixed, and final re-scored numbers.
Expected: all four elements present in what was reported.

- [ ] **Step 6: Roll back the validation commits**

This test data isn't meant to ship in the template — only the single curated example
entry from Task 3 should remain in `applications/log.yaml`.

```bash
git checkout main
git reset --hard MAIN_BEFORE   # use the actual SHA recorded in Step 1
git checkout swe
git reset --hard SWE_BEFORE    # use the actual SHA recorded in Step 1
```

- [ ] **Step 7: Verify rollback**

Run: `git log main --oneline -1 && git log swe --oneline -1 && git show main:applications/log.yaml | grep -c "^- id:"`
Expected: both branches' tip commits match the pre-validation SHAs from Step 1, and
the log file contains exactly `1` entry.

---

### Task 10: `cv-log-outcome` skill (write) — already done in Task 6

This task intentionally left as a pointer: `cv-log-outcome` was written in Task 6.
This task only validates it.

**Files:**
- Modify (temporarily, then reverted): `applications/log.yaml`

- [ ] **Step 1: Record rollback point**

Run: `git rev-parse main`
Save the SHA — call it `MAIN_BEFORE_2`.

- [ ] **Step 2: Run `cv-log-outcome`**

Follow `.claude/skills/cv-log-outcome/SKILL.md` exactly, with:
- Company: `Example Corp`
- Outcome: `interview`

- [ ] **Step 3: Verify the update**

Run: `git show main:applications/log.yaml | python3 -c "import yaml,sys; d=yaml.safe_load(sys.stdin); e=d[0]; assert e['outcome']=='interview'; assert e['outcome_date'] is not None; print('OK', e['outcome_date'])"`
Expected: prints `OK <today's date>` with no assertion errors.

- [ ] **Step 4: Verify exactly one commit was added**

Run: `git log main --oneline -1`
Expected: message starts with "Log outcome: Example Corp".

- [ ] **Step 5: Roll back**

The shipped template's example entry should stay in its original illustrative
`pending`/`null` state.

```bash
git checkout main
git reset --hard MAIN_BEFORE_2   # use the actual SHA recorded in Step 1
```

- [ ] **Step 6: Verify rollback**

Run: `git show main:applications/log.yaml | python3 -c "import yaml,sys; d=yaml.safe_load(sys.stdin); e=d[0]; assert e['outcome']=='pending'; assert e['outcome_date'] is None; print('OK')"`
Expected: prints `OK` with no assertion errors.

---

### Task 11: Validate `cv-sanity-check` on a scratch branch, then delete it

**Files:**
- Create (temporarily, then deleted): scratch branch `test-sanity-check`

- [ ] **Step 1: Create a scratch branch with planted AI-smell text**

```bash
git checkout main
git checkout -b test-sanity-check
```

- [ ] **Step 2: Plant an obviously AI-smelling bullet**

Edit `cv.tex` on this branch: in the "Software Engineering Intern" entry, change the
first bullet to:

```latex
\item Leveraged cutting-edge technologies to spearhead a transformative caching solution
\item Leveraged agile methodologies to spearhead comprehensive testing initiatives
```

(Two bullets, both opening with "Leveraged... to spearhead...", intentionally
repetitive and vague — no metrics, identical sentence structure.)

Commit it: `git add cv.tex && git commit -m "Plant AI-smell test fixture"`

- [ ] **Step 3: Run `cv-sanity-check`**

Follow `.claude/skills/cv-sanity-check/SKILL.md` exactly, with no additional input
(defaults to the current branch, `test-sanity-check`).

- [ ] **Step 4: Verify it caught and fixed the planted issue**

Run: `git diff HEAD~1 HEAD -- cv.tex`
Expected: a non-empty diff touching the two planted bullets — the repeated
"Leveraged... to spearhead..." construction should no longer appear verbatim in both
bullets.

Run: `git log --oneline -1`
Expected: message starts with "Sanity check:".

- [ ] **Step 5: Delete the scratch branch**

```bash
git checkout main
git branch -D test-sanity-check
```

- [ ] **Step 6: Verify cleanup**

Run: `git branch --list test-sanity-check`
Expected: no output (branch no longer exists).

---

### Task 12: Update README status and push

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the Status section**

In `README.md`, replace:

```markdown
## Status

Design is finalized — see [`docs/superpowers/specs/`](docs/superpowers/specs/). Skills are
being implemented.
```

with:

```markdown
## Status

All four skills are implemented and validated end-to-end. See
[`docs/superpowers/specs/`](docs/superpowers/specs/) for the design and
[`docs/superpowers/plans/`](docs/superpowers/plans/) for how it was built.
```

- [ ] **Step 2: Verify final branch/file state before pushing**

Run: `git branch --show-current && git status --short && git branch --list`
Expected: current branch `main`, no uncommitted changes except the README edit about
to be committed, and branches `main`, `swe`, `ai-ml`, `quant-trading`, `data-science`
exist (no `test-sanity-check`).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Mark CV review pipeline skills as implemented"
```

- [ ] **Step 4: Push all branches to GitHub**

```bash
git push origin main
git push origin swe ai-ml quant-trading data-science
```

Expected: all five branches show up on `github.com/ozikan5/CVApplicate`.
