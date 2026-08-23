---
name: cv-add-coursework
description: Given a transcript and a job description, verify which JD-named coursework the user has actually taken, look up the official course description, and enrich master-data.md's coursework line with grounded detail. Use when a job description names specific coursework (e.g. "Operating Systems," "Linear Algebra," "Relational Databases") that master-data.md doesn't yet reflect accurately.
---

# CV Add Coursework

Given a transcript and a job description, verifies which JD-named coursework the
user has genuinely taken, looks up the official course description, and enriches
the coursework line in `master-data.md`'s Education section (labeled `Coursework:`
or `Relevant coursework:` depending on the fork) with grounded, verified detail.

## When to use

A job description names specific coursework as a qualification (e.g. "Relational
Databases," "Linear Algebra & Numerical Methods," "Operating Systems
memory/resource management") and `master-data.md`'s coursework line doesn't yet
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
on `main` — whichever branch is checked out when you start doesn't matter, since
the run checks out `main` and ends there (the same as `cv-log-outcome`).

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
5. Read `master-data.md`'s current coursework line.
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
11. Edit `master-data.md`'s coursework line, extending it with parenthetical
    topic detail for each newly-verified course, in the same style as other
    Education-section entries, e.g. `Discrete Math (Graph Theory, Combinatorics,
    Bayesian Probability)`.
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
