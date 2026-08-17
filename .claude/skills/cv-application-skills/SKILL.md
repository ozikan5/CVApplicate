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
2. **Count** (optional) — defaults to 10. If the user requests a different number, use
   that instead; otherwise don't ask, just use 10.

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
4. Rank candidates by how strongly each is grounded in `master-data.md` and how
   prominently the JD emphasizes it — a skill with deep, specific evidence and heavy
   JD emphasis ranks above one with thin evidence or a passing JD mention. Select the
   top N (10 by default). When a skill is genuinely grounded, prefer phrasing it the
   way the JD itself phrases it — this is a tie-breaker on wording, never a reason to
   stretch a claim past what step 5 allows.
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
  support for them, stated plainly. If nothing is excluded, say so explicitly (e.g.
  'no gaps — every JD-emphasized skill is grounded') rather than omitting the gaps
  note.

## Error handling

- `master-data.md` missing → stop, tell the user it's required before this or any
  other review skill can run.
- `claims-guardrails.md` missing → proceed, note it in the report, be conservative.
- JD URL unreachable → ask the user to paste the text.
- Fewer than N genuinely grounded, JD-relevant skills exist → return what's honestly
  supportable and say so.
