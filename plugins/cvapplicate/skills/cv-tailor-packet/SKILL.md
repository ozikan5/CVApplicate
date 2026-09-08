---
name: cv-tailor-packet
description: Tailor the CV for one scored posting and write a submit-ready packet to outbox/, without committing anything or touching the working tree. Use when a posting has been resolved and scored and a packet is wanted; normally invoked by tailor-packets.sh draining the queue.
---

# CV Tailor Packet

Produces everything needed to submit one application, as files. Writes no git
history: it never runs `git add`, `git commit`, or `git checkout`, and its runner is
not granted those. Recording that you applied is `cv-log-application`'s job.

## Inputs needed

1. **A posting id** present in `postings.local.yaml` with `scored: true` and an entry
   in `matches.local.yaml`. If it is marked `eligible: false`, stop and report the
   reasons — never tailor for a posting the gate rejected.
2. **A branch**, optional. Defaults to the posting's `best_branch` from
   `matches.local.yaml`.

## Procedure

1. Read the posting from `postings.local.yaml`. If `description` is null or empty,
   stop — never tailor against a title alone.
2. If `packeted` is already true, run `python3 pipeline.py packet-path <posting-id>`
   and report the `path` it prints when `exists` is `true`. If `exists` is `false`,
   say so — the flag and the filesystem have diverged, and the user should know
   rather than have it silently repaired.
3. Read `claims-guardrails.md` and the experience bank via
   `git show main:master-data.md`. **The guardrails are binding**, exactly as in
   `cv-review`: they state how each claim may and may not be phrased. Never write a
   bullet that violates one, however much better it would score.
4. Create an isolated checkout:
   `git worktree add .worktrees/tailor-<posting-id> <branch>`
   Work only inside it. Never `git checkout` in the main working tree — this skill
   runs unattended and must not disturb whatever the user has open.
   If this fails because `.worktrees/tailor-<posting-id>` already exists from an
   earlier run whose cleanup didn't complete, remove the stale worktree
   (`git worktree remove --force .worktrees/tailor-<posting-id>`, then
   `git worktree prune`) and retry once. If it still fails, stop and report the
   path — never work inside a worktree left behind by a previous run, whose
   contents are unknown.
5. Score the branch's `cv.tex` as `cv-review` does: **Base Quality /100** (impact 40%,
   competencies 35%, presentation 25%) and **JD Fit /100** (keyword match 40%,
   experience relevance 40%, seniority fit 20%). Keep both as the *before* scores.
6. Pool weaknesses across both layers, take the worst 3, and edit the worktree's
   `cv.tex` to fix them, staying inside the guardrails. Where the JD wants something
   not grounded in the experience bank, keep the honest wording and record it as a
   gap.
7. Compile-check inside the worktree with whichever of `latexmk`, `pdflatex`,
   `tectonic` is found first.
   - None found → `compile: skipped`, no PDF, and say so in `PACKET.md`.
   - Compile fails → `compile: failed`; keep the tailored `.tex`, write the LaTeX
     error into `PACKET.md`, and continue to step 9. A broken packet must never look
     submit-ready.
8. Re-score both layers against the edited `cv.tex` for the *after* scores.
9. Produce the ranked skills list for the portal's Skills field using the same method
   as `cv-application-skills`, grounded in the experience bank and the guardrails.
10. Write the packet to `outbox/<slug>/`, where `<slug>` comes from
    `job_fetcher/tailor.py`'s `packet_slug`:
    - `<First>_<Last>_CV_<Company>.pdf` — the upload, named as `cv-review` names it
    - `cv.tex` — the tailored source, copied out of the worktree
    - `jd.txt` — the posting's `description`
    - `skills.txt` — the ranked keywords, one per line
    - `PACKET.md` — for the user: before/after scores, the three fixes and why, the
      gap list, and any compile problem
    - `packet.yaml` — machine-readable, for the Filler:
      ```yaml
      posting_id: workday-nvidia-JR2007263
      company: "Nvidia"
      role: "Infiniband Network Software Engineer"
      url: "https://…"
      industry_branch: quant-trading
      created: 2026-09-08
      cv_pdf: Ozan_Kan_CV_Nvidia.pdf
      cv_tex: cv.tex
      compile: ok            # ok | failed | skipped
      skills: ["C++", "…"]
      base_quality_before: {total: 93, impact: 93, competencies: 93, presentation: 91}
      base_quality_after:  {total: 95, impact: 95, competencies: 94, presentation: 93}
      jd_fit_before: {total: 61, keyword_match: 78, experience_relevance: 60, seniority_fit: 30}
      jd_fit_after:  {total: 72, keyword_match: 88, experience_relevance: 70, seniority_fit: 30}
      weak_points_fixed: ["…"]
      gaps: ["…"]
      applied: false
      ```
11. Remove the worktree, **on every exit path including failure**:
    `git worktree remove --force .worktrees/tailor-<posting-id>` then
    `git worktree prune`. A leftover worktree breaks the next run.
12. Set `packeted: true` for that posting in `postings.local.yaml`.
13. Report: the packet path, before/after scores, the three fixes, and the gap list.

## Error handling

- Posting missing, unscored, or `eligible: false` → stop and say which.
- `description` empty → stop; never tailor blind.
- Branch has no `cv.tex` → stop and name the branch.
- Compile failure → packet still written, marked `compile: failed`.
- Worktree removal is unconditional. If removal itself fails, say so loudly in the
  report: the next run cannot proceed until it is cleaned up.
- Never run `git add`, `git commit`, `git push`, or `git checkout`. Never edit
  `cv.tex` outside the worktree, and never edit `master-data.md` or
  `claims-guardrails.md` at all.

## Permission scope

This skill needs no commit rights, by design, and its writes are confined to its
own throwaway locations:

```
Read Edit(/outbox/**) Edit(/.worktrees/**) Edit(postings.local.yaml)
Bash(git worktree:*) Bash(git show:*) Bash(python3 pipeline.py:*)
Bash(latexmk:*) Bash(pdflatex:*) Bash(tectonic:*)
```

The absence of `Bash(git add:*)` and `Bash(git commit:*)` is what makes it impossible
for an unattended run to claim an application it did not make. And because the
grant scopes writes to `outbox/` and `.worktrees/` plus the one `postings.local.yaml`
entry, it cannot touch the experience bank, the guardrails, or a branch's `cv.tex`
outside its own worktree, no matter what the procedure above intends. These rules
use `Edit(...)`, not `Write(...)`, because Claude Code's permission engine only
consults path scoping on `Edit` rules — a `Write(pattern)` rule is accepted but
silently ignored, leaving writes as unscoped as bare `Write`.
