# CVApplicate

A template for turning "ask an AI to review my CV" into a repeatable, version-controlled pipeline.

## What this is

If you already paste your CV and a job description into an AI, ask for a score, fix the
weak points, and submit — this packages that loop into four Claude Code skills, backed by
git. Each industry you apply to gets its own branch. Every application gets logged against
the exact commit of the CV you sent.

This repo ships with placeholder content only. Fork it and fill in your own.

## Structure

```
CVApplicate/
├── cv.tex                        Placeholder LaTeX CV
├── master-data.md                Your experience/education/skills bank
├── claims-guardrails.example.md  Template for your claim limits (copy to claims-guardrails.md)
├── applications/log.yaml         History of applications, scores, and outcomes
├── check-cv-text.py              Mechanical repetition/filler detector
├── import-overleaf.sh            Import a CV from an Overleaf source zip
├── .claude/skills/               The four skills below
└── docs/                         Design spec and implementation plan

Branches: main (base CV) + one per industry (swe, ai-ml, quant-trading, data-science, ...)
```

## Skills

| Skill | What it does |
|---|---|
| **cv-review** | Scores your CV against a job description, fixes the weakest points, logs the application |
| **cv-new-industry** | Branches a new industry-specific CV variant off `main` |
| **cv-log-outcome** | Records an application's outcome (interview, offer, rejection) |
| **cv-sanity-check** | Finds and fixes writing that reads as AI-generated |

---

# Setup

## 1. Fork and clone

Create your own repository — **private**, since it will hold your real CV, contact
details, and application history. Then:

```bash
git clone https://github.com/YOUR-USERNAME/YOUR-REPO.git my-cv && cd my-cv
```

To keep pulling improvements from this template later, add it as a second remote:

```bash
git remote add upstream https://github.com/ozikan5/CVApplicate.git
```

## 2. Add your CV

If your CV lives in Overleaf, download it (**Menu → Download → Source**) and import:

```bash
./import-overleaf.sh ~/Downloads/YourProject.zip
```

The script finds the main `.tex` in the zip, copies it to `cv.tex`, and carries over any
`.cls`/`.sty`/image assets. Otherwise just replace `cv.tex` yourself.

> **Overleaf sync:** Overleaf's git integration is a premium feature. On a free plan,
> re-import with the script when you edit in Overleaf, and paste `cv.tex` back when you
> edit here. On a paid plan you can instead add your Overleaf project as a git remote and
> push/pull directly.

## 3. Fill in your experience bank

`master-data.md` is your source of truth — deliberately **larger** than one page. Put
everything in it: bullets that didn't make the cut, extra detail on each project, metrics
you haven't used yet. When a job description asks for something, the review skill draws
from here rather than inventing it.

## 4. Write your guardrails

```bash
cp claims-guardrails.example.md claims-guardrails.md
```

This is the step people skip, and it's the one that matters most — see
[Guardrails](#guardrails) below.

## 5. Create your industry branches

Ask Claude to run `cv-new-industry` for each field you target. It branches off `main` and
adapts `cv.tex` for that industry using your `master-data.md`.

```
Run cv-new-industry for "consulting"
```

---

# Daily use

## Reviewing your CV against a job posting

```
Run cv-review — branch swe, company Acme, role Backend Engineer Intern.
JD: <paste the posting, or give a URL>
```

The skill will:

1. Check out the `swe` branch
2. Score **Base Quality** /100 — Impact 40%, Competencies 35%, Presentation 25%
3. Score **JD Fit** /100 — keyword match 40%, experience relevance 40%, seniority 20%
4. Pick the worst 3 weaknesses across both scores
5. Edit `cv.tex` to fix them, staying inside your guardrails
6. Compile-check the LaTeX (reverts the edit if it breaks)
7. Re-score and report before/after
8. Log the application to `applications/log.yaml` on `main`

Score bands follow VMock's public methodology: 🔴 0–32 · 🟡 33–85 · 🟢 86–100. Aim for 85+;
100 is not the goal.

**Read the gap list at the end of the report.** When the posting wants something you can't
honestly claim, the skill says so instead of writing around it. That list tells you what to
go build or document.

## Checking it doesn't read as AI-written

```
Run cv-sanity-check
```

Two passes. First `check-cv-text.py` counts what's countable — buzzwords, filler phrases,
repeated bullet openers, overused words, em dashes, uniform bullet lengths, unquantified
bullets — all with line numbers. Then the model reads for what a script can't see: tense
consistency, cadence, vague-but-numbered claims.

You can run the detector yourself any time:

```bash
python3 check-cv-text.py cv.tex
```

Findings are signals, not verdicts. A domain term repeating across bullets ("search",
"pipeline") is often unavoidable; the skill tells you which findings it fixed and which it
judged acceptable, and why.

## Recording what happened

```
Run cv-log-outcome for Acme — interview
```

Updates that entry's `outcome` and `outcome_date` on `main`. Because each entry stores the
`cv_commit` of the CV you actually sent, you can recover it exactly later:

```bash
git show <cv_commit>:cv.tex
```

Over time this is the interesting artifact — which CV versions and scores actually
correlated with interviews.

---

# Guardrails

An AI editing your CV drifts toward overclaiming. It widens a metric's scope ("99% F1 on
held-out pairs" becomes "99% accurate"), strengthens ownership verbs ("contributed to"
becomes "drove"), and describes unshipped work as live. Each edit looks like an
improvement and scores better. Collectively they build a CV you can't defend in an
interview.

`claims-guardrails.md` is where you write those limits down. It states, per claim, what is
**true**, what may be **claimed**, and what must **not** be:

```markdown
### "99% accuracy"
- **True:** 99% F1 on a held-out *pair-classification* set.
- **Claim:** "99% F1 pair classification."
- **Do not claim:** "99% accurate" — end-to-end accuracy on the real task is much lower.
```

`cv-review` and `cv-sanity-check` read this file before editing and treat it as binding —
a guardrail beats a higher score. When a posting tempts them past what's true, they keep
the honest wording and report the gap.

Worth writing rules for: metrics whose real scope is narrower than they sound, work you
contributed to rather than owned, anything not yet in production, team results, early A/B
readouts, and self-estimates. If something you shipped underperformed, note that too —
being able to explain it reads as maturity.

Update this file whenever the facts change, before touching the CV.

---

# Job Postings Fetcher

Pulls new job listings from companies' ATS APIs (Greenhouse, Lever) once a day and
emails you a summary. See
`docs/superpowers/specs/2026-08-14-job-postings-fetcher-design.md` for the full design.

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Copy `companies.example.yaml` to `companies.local.yaml` and fill in the companies
   you want to track (see the comments in that file for how to find each company's
   ATS slug).
3. Copy `.env.example` to `.env` and fill in your SMTP credentials — for Gmail, use
   an App Password (https://myaccount.google.com/apppasswords), not your normal
   password.
4. Run it once by hand to confirm it works: `python3 fetch-postings.py`
5. To run it automatically every day:
   - Copy `launchd/com.cvapplicate.fetch-postings.plist.example` to
     `~/Library/LaunchAgents/com.cvapplicate.fetch-postings.plist`
   - Replace every `/ABSOLUTE/PATH/TO/CVApplicate` placeholder in that copied file
     with this repo's actual absolute path (find it with `pwd`).
   - **Important:** The plist hardcodes `/usr/bin/python3` (Apple's system Python). If you
     installed dependencies with a different Python (Homebrew, pyenv, etc.), check `which python3`
     — if it differs, update that path in the plist too. Otherwise the scheduled job will fail
     silently with `ModuleNotFoundError` even though your manual test works.
   - Load it: `launchctl load ~/Library/LaunchAgents/com.cvapplicate.fetch-postings.plist`
   - It now runs daily at 8:00am; check `fetch-postings.log` in the repo for output.
   - To stop it: `launchctl unload ~/Library/LaunchAgents/com.cvapplicate.fetch-postings.plist`

`companies.local.yaml`, `postings.local.yaml`, and `.env` are all gitignored — your
real target list, fetched postings, and credentials never get committed to this
template repo.

---

# How it's organised

`master-data.md` and `applications/log.yaml` are authoritative on `main` only. The skills
commit changes to them there and then return to your industry branch, so your experience
bank and application history stay unified however many branches you have. Only `cv.tex`
diverges per branch.

The skills live in the repo, so they're branched too. After editing a skill on `main`,
merge `main` into your industry branches:

```bash
for b in swe ai-ml quant-trading data-science; do
  git checkout $b && git merge main -m "Merge main: sync skills"
done
git checkout main
```

Same command pulls template updates through, after `git merge upstream/main` on `main`.

## Requirements

- Claude Code
- git
- A LaTeX toolchain (`latexmk`, `pdflatex`, or `tectonic`) — optional. Without one the
  skills skip compile-checking and say so in their report.
- Python 3 for `check-cv-text.py`

## Status

All four skills are implemented and validated end-to-end. See
[`docs/superpowers/specs/`](docs/superpowers/specs/) for the design and
[`docs/superpowers/plans/`](docs/superpowers/plans/) for how it was built.

## License

MIT
