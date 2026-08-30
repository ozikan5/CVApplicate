# `cv-add-coursework` Skill — Design

**Date:** 2026-08-23
**Status:** Approved for planning

## Purpose

A job description sometimes names specific coursework as a qualification (e.g. NVIDIA's
"Relational Databases, Linear Algebra & Numerical Methods, Operating Systems
memory/resource management"). Today, closing that gap means manually cross-referencing a
transcript against a target JD, web-searching official course descriptions, and hand-editing
`master-data.md` — a multi-step process repeated by hand for the NVIDIA review on
2026-08-21/23. This skill turns that into a repeatable `cvapplicate` skill: given a
transcript and a JD, verify which JD-named coursework the user has actually taken, pull the
real topics from the university's official course description, and enrich
`master-data.md`'s `Coursework:` line with grounded detail — never inventing a course or a
topic that isn't independently verifiable.

## Non-goals

- **Not full-transcript enrichment.** Scope is JD-driven: only courses the current JD calls
  for get looked up and added. A course irrelevant to every JD reviewed so far stays out of
  `master-data.md` until some JD actually needs it — consistent with `master-data.md`'s
  existing "holds more than fits on any one CV, available when a JD calls for it" philosophy,
  applied at ingestion time rather than after the fact.
- **Never touches `cv.tex`.** This skill's output is `master-data.md` on `main`, full stop.
  Pulling newly-enriched coursework onto a specific industry branch's one-page `cv.tex` — and
  making the space-tradeoff decisions that requires — is `cv-review`'s job, run separately
  afterward. (Confirmed correct by the manual NVIDIA run: `master-data.md` stayed verbose
  with zero space pressure, while fitting new coursework onto the actual one-page CV required
  trimming a lower-priority existing item — a `cv-review`-style judgment call that doesn't
  belong here.)
- **No new tooling for course lookup.** Northwestern's official course-description pages are
  found via ordinary web search; no dedicated scraper or cached course-catalog store. The
  manual dry run confirmed this is sufficient — every course looked up (COMP_SCI 343, 339,
  214, 336, ELEC_ENG 373, GEN_ENG 205) resolved to an official McCormick Engineering course
  description on the first or second search.
- **Not a general "resync my transcript" tool.** If the user's coursework changes (a new
  semester, a retake), re-running this skill against a new JD picks up new courses as needed;
  there's no separate diffing/sync mechanism against a stored transcript snapshot.

## Inputs needed

1. **A transcript** — file path to a PDF, or the user pastes the course list as text.
2. **A job description** — pasted text or a URL (same fetch-then-ask-for-paste fallback as
   `cv-review`).

No industry/branch input — like `cv-application-skills`, this skill only ever touches
`main`, so whichever branch is currently checked out doesn't matter and never gets switched
away from without switching back.

## Procedure

1. Run `git status` to confirm the working tree is clean. If not, stop and tell the user
   what's uncommitted.
2. `git checkout main` (`master-data.md` is main-only, same rule every other skill follows).
3. Read the transcript in full and extract every course (department, number, title, term,
   grade). No web calls yet.
4. Read the JD and extract topic/skill phrases that plausibly map to coursework — not just
   exact course-title matches, but the underlying concepts (e.g. NVIDIA's "Distributed
   Systems" or "Linear Algebra & Numerical Methods" name topics, not literal course titles).
5. Read `master-data.md`'s current `Coursework:` line.
6. Match JD topics against transcript courses using judgment, not string-matching. The
   NVIDIA run needed exactly this kind of inference twice: "Operating Systems" matched
   directly, but "Distributed Systems" had no matching transcript course at all (correctly
   left unclaimed), while "Linear Algebra & Numerical Methods" partially matched
   `GEN_ENG 205: Engineering Analysis` (a course whose title contains neither word).
   - Skip any match already fully represented with topic detail in `master-data.md`.
   - Drop any JD topic with no plausible transcript match at all — this is a gap to report,
     not a reason to search harder for a stretch.
7. For each remaining candidate, web-search the official university course description
   (department site or course catalog first; course-syllabus PDFs as a fallback if the
   department page doesn't turn up).
8. **Scope every claim to what the description actually verifies, not to the JD's full
   phrase.** If a JD phrase has multiple parts and the official description only supports
   some of them, claim only the supported subset. (NVIDIA precedent: "Linear Algebra &
   Numerical Methods" got scoped down to "Linear Algebra" alone, because
   `GEN_ENG 205-1`'s verified content covers computational linear algebra but not numerical
   methods proper — that's `GEN_ENG 205-4`, a course not on the transcript.)
9. Anything not confidently matched or found — ambiguous transcript entry, no official
   description locatable, description doesn't clearly cover the JD topic — is held back, not
   guessed. Collect every such case.
10. If step 9 produced any held-back cases, ask the user about all of them in a single
    batched message (not one interruption per course), and wait for a response before
    continuing.
11. Edit `master-data.md`'s `Coursework:` line, extending it with parenthetical topic detail
    for each newly-verified course, matching the existing style already used for Discrete
    Math (e.g. `Operating Systems (memory/resource management, scheduling & resource
    management)`).
12. Commit: `git add master-data.md && git commit -m "Add coursework detail for <Company> JD from transcript"`.
13. Report to the user: which courses were added (with the verified detail pulled in and its
    source), which JD-named topics were already covered, which JD-named topics had no
    transcript match at all (a gap, stated plainly), and a reminder to run `cv-review` next
    if they want this reflected on a specific branch's `cv.tex`.

## Data flow summary

1. User provides a transcript (once, reusable across many future runs) and a JD.
2. Skill cross-references JD topics against transcript courses using judgment-based
   matching, not keyword-matching.
3. Skill verifies each match against the university's official, currently-published course
   description via web search.
4. Skill scopes each claim to exactly what's verified — never the JD's full phrase if only
   part of it holds up.
5. Skill batches every unresolved case into one round of questions, asked once, at the end.
6. Skill commits the enriched `Coursework:` line to `master-data.md` on `main`.
7. Separately, the user runs `cv-review` to pull the JD-relevant subset onto a specific
   branch's `cv.tex`, making whatever one-page space tradeoffs that requires.

## Error handling

- **Dirty working tree at step 1** → stop, do not check out `main`.
- **JD URL unreachable** → ask the user to paste the text.
- **Transcript unreadable or not provided** → ask the user to provide it (file path or
  pasted text); do not proceed without it.
- **No JD-relevant courses found on the transcript at all** → report that plainly, make no
  edit, no commit.
- **Web lookup down entirely, or no official description locatable for a given course** →
  treat as "unmatched" (step 9); batch into the end-of-run questions, never guess a
  description from the course title alone.
- **A JD topic only partially verified** → claim only the verified subset (step 8); note the
  unclaimed remainder as a gap in the final report, not a silent omission.
- **`master-data.md` showing up modified on an industry branch afterward** → same rule as
  every other skill: revert it there, redo the edit on `main`.

## Privacy

The transcript itself (grades, GPA, full course history) is read transiently for this run
and never copied into the repo or committed — only course numbers/titles derived from it
ever leave the local session, and only as web-search query terms (e.g. "Northwestern
COMP_SCI 343 course description"), never grades or other transcript content.

## Key decisions log

- **JD-driven scope, not full-transcript enrichment** — chosen over ingesting the whole
  transcript up front, so `master-data.md` only grows to hold what's actually been asked
  for, on the same "add it when a JD calls for it" philosophy already governing the rest of
  the file.
- **Extend the existing flat `Coursework:` line's parenthetical style**, rather than
  introducing a separate structured coursework section — smaller change to
  `master-data.md`'s shape, and `cv-review` already knows how to read this format.
- **Batch clarifying questions at the end of the run**, not interactively per-course — matches
  `cv-review`'s existing batching pattern for guardrail tensions and keeps the skill from
  becoming a long back-and-forth over one transcript.
- **Stops after `main`; never edits `cv.tex`** — keeps this skill's responsibility to
  "verify and record," leaving "select and fit onto one page" entirely to `cv-review`, where
  that judgment already lives.
- **No new lookup infrastructure** — ordinary web search proved sufficient in the manual dry
  run; adding a scraper or a cached catalog store would be solving a problem that hasn't
  actually appeared.
