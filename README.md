# CVApplicate

A plugin that turns "ask an AI to review my CV" into a repeatable,
version-controlled pipeline.

## What this is

If you already paste your CV and a job description into an AI, ask for a score, fix the
weak points, and submit — this packages that loop into seven skills, backed by
git. Each industry you apply to gets its own branch. Every application gets logged against
the exact commit of the CV you sent.

This one repo does two things at once:

1. **It's an installable plugin.** The skills and their helper script live under
   `plugins/cvapplicate/` and install once, system-wide, via `/plugin install` — you
   never fork or edit this part.
2. **It's a data template.** Everything else at the repo root (`cv.tex`,
   `master-data.md`, `claims-guardrails.example.md`, `applications/log.yaml`,
   `import-overleaf.sh`) is placeholder content for the private repo that holds *your*
   CV. You copy that part out; you don't work inside this repo.

## Structure

```
CVApplicate/
├── .claude-plugin/marketplace.json   Marketplace listing (points at the plugin below)
├── plugins/cvapplicate/
│   ├── .claude-plugin/plugin.json    Plugin manifest
│   ├── scripts/check-cv-text.py      Mechanical repetition/filler detector
│   └── skills/                       The seven skills below
│
├── cv.tex                        Placeholder LaTeX CV        ┐
├── master-data.md                Your experience/skills bank │  copy these into
├── claims-guardrails.example.md  Template for your claim limits │  your own private
├── applications/log.yaml         History of applications/outcomes │  data repo
├── import-overleaf.sh            Import a CV from an Overleaf zip ┘
└── docs/                         Design spec and implementation plan
```

## Skills

| Skill | What it does |
|---|---|
| **cv-review** | Scores your CV against a job description, fixes the weakest points, logs the application |
| **cv-new-industry** | Branches a new industry-specific CV variant off `main` |
| **cv-log-outcome** | Records an application's outcome (interview, offer, rejection) |
| **cv-sanity-check** | Finds and fixes writing that reads as AI-generated |
| **cv-application-skills** | Ranks the top skill keywords for a job application's Skills field, from a JD |
| **cv-add-coursework** | Verifies JD-named coursework against a transcript and enriches `master-data.md` with the official course description |
| **cv-score-postings** | Scores fetched job postings against every industry branch's CV data — read-only, no edits; normally run nightly, unattended |

---

# Setup

## 1. Install the plugin

In your AI coding CLI:

```
/plugin marketplace add https://github.com/ozikan5/CVApplicate
/plugin install cvapplicate@cvapplicate
```

This installs the seven skills once, available in any directory. When this repo's skills
get updated upstream, pull them with `/plugin update cvapplicate` (or reinstall) — updates
aren't automatic.

## 2. Create your own data repo

Use GitHub's **"Use this template"** on this repo (or fork it) to create your own
repository — **private**, since it will hold your real CV, contact details, and
application history. Then delete `plugins/` and `.claude-plugin/` from your copy — those
two only exist to distribute the plugin and aren't needed once it's installed:

```bash
git clone https://github.com/YOUR-USERNAME/YOUR-REPO.git my-cv && cd my-cv
rm -rf plugins .claude-plugin
git add -A && git commit -m "Drop plugin distribution files from data repo"
```

## 3. Add your CV

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

## 4. Fill in your experience bank

`master-data.md` is your source of truth — deliberately **larger** than one page. Put
everything in it: bullets that didn't make the cut, extra detail on each project, metrics
you haven't used yet. When a job description asks for something, the review skill draws
from here rather than inventing it.

## 5. Write your guardrails

```bash
cp claims-guardrails.example.md claims-guardrails.md
```

This is the step people skip, and it's the one that matters most — see
[Guardrails](#guardrails) below.

## 6. Create your industry branches

Run `cv-new-industry` for each field you target. It branches off `main` and adapts
`cv.tex` for that industry using your `master-data.md`.

```
Run cv-new-industry for "consulting"
```

---

# Daily use

Skills trigger from plain-language requests like the ones below, or can be invoked
explicitly as `/cvapplicate:cv-review`, `/cvapplicate:cv-sanity-check`, etc.

## Verifying coursework against a transcript

```
Run cv-add-coursework with my transcript at <path>, for this JD: <paste or URL>
```

When a job description names specific coursework (e.g. "Operating Systems," "Linear
Algebra," "Relational Databases") that your `master-data.md` doesn't yet reflect
accurately, this cross-references the JD's asks against your actual transcript,
looks up each course's official description, and enriches the coursework line in
`master-data.md`'s Education section (labeled `Coursework:` or `Relevant
coursework:` depending on the fork) with verified detail — never inventing a
course, and never scoping a claim past what the official description actually
supports. Anything ambiguous or unverifiable gets batched into one round of
questions at the end, rather than guessed. Run `cv-review` afterward to pull the
newly-verified coursework onto a specific branch's `cv.tex`.

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
6. Compile-check the LaTeX (reverts the edit if it breaks) and hand you the compiled
   PDF to download, named `First_Last_CV_Company.pdf` — it's a build artifact, not
   tracked in git, so it's regenerated each run rather than committed
7. Re-score and report before/after
8. Log the application to `applications/log.yaml` on `main`

`cv-new-industry` and `cv-sanity-check` deliver a PDF the same way at the end of their
runs, named `First_Last_CV_Industry.pdf` and `First_Last_CV_Branch.pdf` respectively —
whichever single word identifies the industry/branch, since neither has a company to
name against.

Score bands follow VMock's public methodology: 🔴 0–32 · 🟡 33–85 · 🟢 86–100. Aim for 85+;
100 is not the goal.

**Read the gap list at the end of the report.** When the posting wants something you can't
honestly claim, the skill says so instead of writing around it. That list tells you what to
go build or document.

## Checking it doesn't read as AI-written

```
Run cv-sanity-check
```

Two passes. First `check-cv-text.py` (bundled inside the plugin) counts what's countable —
buzzwords, filler phrases, repeated bullet openers, overused words, dash-connectors (em
dashes and double/triple hyphens used mid-sentence, not numeric or date ranges), uniform
bullet lengths, unquantified bullets — all with line numbers. Then the model reads for
what a script can't see: tense consistency, cadence, vague-but-numbered claims.

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

## Filling in an application's "Skills" field

```
Run cv-application-skills for this JD: <paste or URL>
```

Many application portals ask for a separate list of skill keywords, independent of
whatever CV you upload. This reads `master-data.md` and reports the 10 best-fitting
ones for the posting, each with the specific experience it's grounded in, plus a gap
note for anything the JD emphasizes that your experience doesn't support. Nothing
gets written anywhere — copy the list into the application yourself.

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

`cv-review` and `cv-sanity-check` read this file before editing and treat it as binding;
`cv-application-skills` reads it too, before recommending skills, since it never edits
anything. All three treat it as binding — a guardrail beats a higher score. When a
posting tempts them past what's true, they keep the honest wording and report the gap.

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

# Job Postings Scoring

Phase 2 of the pipeline: scores every fetched posting against each industry branch's CV
data overnight, using the same JD Fit rubric `cv-review` applies interactively. See
`docs/superpowers/specs/2026-08-31-job-postings-scoring-design.md` for the full design.

This is scoring only — it never edits `cv.tex` or `master-data.md`, never commits, and
never checks out a branch (branch content is read via `git show`, leaving your working
tree untouched). It writes results to a local file for you to read when you choose;
nothing gets emailed or submitted automatically. Strong matches still go through
`cv-review` by hand before you apply.

## Setup

1. Make sure `fetch-postings.py` is already set up and running (see above) — scoring
   has nothing to score without it.
2. Run it once by hand to confirm it works: `./score-postings.sh` (requires the `claude`
   CLI on PATH).
3. To run it automatically every day, thirty minutes after the fetch job so it has
   fresh postings to work from:
   - Copy `launchd/com.cvapplicate.score-postings.plist.example` to
     `~/Library/LaunchAgents/com.cvapplicate.score-postings.plist`
   - Replace every `/ABSOLUTE/PATH/TO/CVApplicate` placeholder with this repo's actual
     absolute path (find it with `pwd`).
   - **Important:** if `which claude` differs between your interactive shell and a
     bare launchd environment, `score-postings.sh` will fail silently with "command not
     found" — the same class of PATH mismatch documented above for `fetch-postings.py`'s
     `python3`.
   - Load it: `launchctl load ~/Library/LaunchAgents/com.cvapplicate.score-postings.plist`
   - It now runs daily at 8:30am; check `score-postings.log` in the repo for output.
   - To stop it: `launchctl unload ~/Library/LaunchAgents/com.cvapplicate.score-postings.plist`

Results land in `matches.local.yaml` — gitignored, like `postings.local.yaml`. Each
scored posting carries a `best_branch`, a `jd_fit_score`, and a one-line rationale; read
it whenever you want to see what's worth applying to.

---

# How it's organised

`master-data.md` and `applications/log.yaml` are authoritative on `main` only, in *your*
data repo. The skills commit changes to them there and then return to your industry
branch, so your experience bank and application history stay unified however many
branches you have. Only `cv.tex` diverges per branch.

The skills themselves no longer live in your data repo — they're installed once as the
`cvapplicate` plugin and shared across every branch and every repo automatically. There's
nothing to sync when a skill is updated upstream; run `/plugin update cvapplicate` (or
reinstall) to pick up the latest version.

## Requirements

- An AI coding CLI with plugin support, with the `cvapplicate` plugin installed (see Setup above)
- git
- A LaTeX toolchain (`latexmk`, `pdflatex`, or `tectonic`) — optional. Without one the
  skills skip compile-checking and say so in their report.
- Python 3 for `check-cv-text.py` (bundled in the plugin — nothing to install separately)

## Status

All seven skills are implemented; six are validated end-to-end as skills.
`cv-score-postings` is implemented and unit-tested at the code layer (JD description
capture, the `scored` flag) but hasn't yet been exercised through a live nightly
`score-postings.sh` run against real postings and real branches — if that surfaces
anything, please open an issue. The plugin/marketplace manifests follow the documented
plugin schema but haven't yet been exercised through a live `/plugin install` by an end
user either. See [`docs/superpowers/specs/`](docs/superpowers/specs/) for the design and
[`docs/superpowers/plans/`](docs/superpowers/plans/) for how it was built.

## License

MIT
