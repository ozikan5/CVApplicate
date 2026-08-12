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
├── cv.tex                  Placeholder LaTeX CV
├── master-data.md          Your experience/education/skills bank
├── applications/log.yaml   History of applications, scores, and outcomes
├── .claude/skills/         The four skills below
└── docs/                   Design spec and other project docs

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

## Status

Design is finalized — see [`docs/superpowers/specs/`](docs/superpowers/specs/). Skills are
being implemented.
