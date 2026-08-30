# `cv-application-skills` — Design

**Date:** 2026-08-15
**Status:** Approved for planning

## Purpose

A fifth skill for the CVApplicate skill set. Given a job description, produces a
ranked list of the 10 skill keywords best suited for an application portal's
free-text "Skills" field (Workday-style tag pickers, "list your top skills" boxes) —
a field that's separate from the CV document itself and exists on many application
forms independent of whatever resume gets uploaded.

## Non-goals

- Not for portals with a fixed, closed dropdown of skill options (only free-text
  entry is in scope; see Key decisions log).
- Does not edit `cv.tex`, does not write to `applications/log.yaml`, does not
  commit anything. Output is chat-only.
- Does not require selecting or switching to an industry branch. It reads
  `master-data.md` directly, which holds the full experience bank across all
  branches, so the currently checked-out branch is irrelevant to its output.

## Inputs needed

1. **Job description** — pasted text, or a URL to fetch. If a URL is given, try
   fetching it first; if the fetch fails or returns unusable content, ask the user
   to paste the text instead. (Same fallback behavior as `cv-review`.)
2. Optionally, a count other than 10, if the user asks for a different number.

No industry/branch input, no company/role name required (nothing gets logged).

## Procedure

1. Read `master-data.md` (full experience bank) and `claims-guardrails.md` (binding
   constraints on how any given claim may be phrased/scoped).
2. Extract the JD's explicit skill, technology, and competency terms.
3. Cross-reference those terms — and general relevant competencies — against
   everything demonstrated in `master-data.md`, not just its dedicated Skills
   section. A skill evidenced only in an Experience or Project bullet still counts.
4. Rank candidates and select the top 10 (or the user-requested count). Ranking
   preference: when a skill is genuinely grounded, prefer phrasing it the way the
   JD itself phrases it, so an ATS or recruiter scanning the field sees their own
   terminology reflected back — not a rule to stretch a claim, just a tie-breaker
   on wording when the underlying skill is already solidly grounded.
5. Never include a skill not grounded in `master-data.md`, and never phrase one in
   a way `claims-guardrails.md` prohibits (e.g. do not suggest "Kubernetes" if the
   only grounding is "used Docker once" — that's not the same skill).
6. Identify JD-emphasized skills that have no grounded support in `master-data.md`
   at all — this becomes the gaps note in the report.

## Output

- The 10 (or requested count) skills, each with a one-line reason tying it back to
  specific grounded experience.
- A short **gaps** note: JD-emphasized skills excluded because there's no grounded
  support for them — stated plainly, not glossed over, matching the reporting
  style of the other skills in this repo (an unmet requirement stated plainly is
  more useful than a list that quietly excludes something without explanation).
- Nothing is written to any file. The user copies the list into the application
  portal themselves.

## Error handling

- `master-data.md` missing → stop, tell the user it's required (this repo is
  meant to be forked and filled in before any review skill is used).
- `claims-guardrails.md` missing → proceed, but say so in the report and be
  conservative about which skills count as "grounded" (same fallback as the other
  skills).
- JD URL unreachable → ask the user to paste the text.
- Fewer than 10 genuinely grounded, JD-relevant skills exist → return however many
  are honestly supportable and say so, rather than padding the list with weak or
  ungrounded entries to hit the count.

## Key decisions log

- **Free-text portals only, not fixed dropdowns** — a fixed-dropdown portal's
  available options can't be known in advance; supporting that case would require
  the user to paste in the portal's own option list first, which is a different
  (and more niche) workflow than what was asked for. Can be added later as a
  separate mode if needed.
- **Separate skill, not folded into `cv-review`** — matches this repo's existing
  one-skill-one-purpose design (four already-decoupled skills). You might want the
  skills list without wanting a full CV edit-and-score cycle, e.g. re-running it
  after a JD changes slightly, or before deciding whether to do a full review at
  all.
- **No branch switching, no file writes** — this skill only ever reads
  `master-data.md`/`claims-guardrails.md` and prints to chat, so it's safe to run
  from any branch, at any time, with no cleanup required afterward.
- **Guardrails-bound, same as `cv-review`/`cv-sanity-check`** — a skills list that
  overstates a competency is exactly the kind of thing that collapses under a
  recruiter's or interviewer's follow-up question; the same discipline that
  governs `cv.tex` edits governs this list.
