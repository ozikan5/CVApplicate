# CVApplicate

A template for turning "ask an AI to review my CV" into a repeatable, version-controlled pipeline.

## What this is

CVApplicate packages a CV review workflow into four Claude Code skills, backed by a
git-based structure for tracking CV variants across industries and every application
you send. This repo ships with placeholder content only — fork it and fill in your own
CV, experience, and Overleaf sync to make it yours.

## Structure

```
CVApplicate/
├── cv.tex                        Placeholder LaTeX CV
├── master-data.md                Your experience/education/skills bank
├── claims-guardrails.example.md  Template for your claim limits (copy to claims-guardrails.md)
├── applications/log.yaml         History of applications, scores, and outcomes
├── import-overleaf.sh            Import a CV from an Overleaf source zip
├── .claude/skills/               The four skills below
└── docs/                         Design spec and other project docs

Branches: main (base CV) + one per industry (swe, ai-ml, quant-trading, data-science, ...)
```

## Skills

- **cv-review** — Scores a CV against a job description, fixes the weakest points, and logs the application.
- **cv-new-industry** — Branches a new industry-specific CV variant off `main`.
- **cv-log-outcome** — Records an application's outcome (interview, offer, rejection, etc.).
- **cv-sanity-check** — Flags and fixes CV text that reads as AI-generated.

## Getting started

1. Fork this repo.
2. Replace the placeholder `cv.tex` and `master-data.md` with your real content.
3. Add your Overleaf project as a git remote to keep it in sync.
4. Run `cv-new-industry` for each field you're targeting, then `cv-review` per application.

## Guardrails

An AI editing your CV will drift toward overclaiming — widening a metric's scope,
strengthening an ownership verb, calling unshipped work "live". `claims-guardrails.md`
is where you write those limits down, and the review skills treat it as binding: when a
job description tempts them past what's true, they keep the honest wording and report
the gap instead. That gap list is usually the useful part — it tells you what to go
build, not what to reword.

## Notes

`master-data.md` and `applications/log.yaml` are authoritative on `main` — the skills
commit changes to them there, so your experience bank and application history stay
unified no matter how many industry branches you have. Only `cv.tex` diverges per branch.

The skills live in the repo, so they're branched too. After editing a skill on `main`,
merge `main` into your industry branches to keep them in sync.

## Status

All four skills are implemented and validated end-to-end. See
[`docs/superpowers/specs/`](docs/superpowers/specs/) for the design and
[`docs/superpowers/plans/`](docs/superpowers/plans/) for how it was built.
