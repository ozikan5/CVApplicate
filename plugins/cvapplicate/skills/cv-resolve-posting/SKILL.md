---
name: cv-resolve-posting
description: Resolve a job posting URL into the tracked postings file and score it against every industry branch. Use when the user pastes a link to a job posting and wants to know how well it fits, or wants it added to the pipeline.
---

# CV Resolve Posting

Turns a job posting URL into a stored, scored posting. All fetching and all
file writing happen in `resolve-posting.py`; this skill only fills in fields
that could not be extracted mechanically.

## Inputs needed

1. **A job posting URL.** If the user pasted a job description without a URL,
   this skill does not apply — use `cv-review` instead.

## Procedure

1. Run `python3 resolve-posting.py <url>` and capture stdout and the exit code.
2. Handle the exit code:
   - **0** — continue to step 3.
   - **2** — report the message and stop; the URL was not usable.
   - **3** — tell the user the page needs a browser, which is not yet
     supported, and that they can run `cv-review` with the job description
     pasted in. Stop.
   - **4** — report the message and stop. If it says the posting is no longer
     available, say that plainly: the job was filled or pulled.
   - **5** — report that both the ATS adapter and generic extraction failed,
     quote the warning from stderr, and suggest opening an issue since it names
     the adapter that broke. Stop.
3. Parse the JSON object from stdout. If it has no `needs_extraction` field, it
   is complete — go to step 5.
4. If `needs_extraction` is true, read `raw_text` and `hints` and determine
   `company`, `title`, and `location`:
   - Prefer `hints.og_title` and `hints.document_title` for the title, but
     strip any company-name suffix (`"Backend Engineer at Tiny Co"` → `"Backend
     Engineer"`).
   - Take the company from the page text or `hints.domain`.
   - Use `"Unknown"` for `location` only if the text genuinely does not say.
   - **Do not invent a title or company.** If `raw_text` is navigation chrome
     with no job description in it, say so and stop — a posting with a guessed
     title would be scored and reported as if it were real.
5. Write the completed posting object to stdin of
   `python3 resolve-posting.py --store -`. Include every field from the resolve
   output with the nulls filled in; the script drops its own transport fields.
   Write the JSON to a temp file first, then run:

   ```
   python3 resolve-posting.py --store - < /tmp/posting.json
   ```

   Redirection keeps the invocation's first token `python3`, matching the
   `Bash(python3 resolve-posting.py:*)` grant below — an `echo ... | python3
   ...` pipeline would not match that prefix rule.
6. Read the JSON status object from stdout:
   - `already_tracked: true` — tell the user the posting is already tracked,
     give the `id`, and say whether it has been scored. If `scored` is true,
     read the entry from `matches.local.yaml` and report the existing score
     instead of re-scoring. Stop.
   - `stored: true` — continue.
7. Invoke the `cv-score-postings` skill. It scores every posting whose `scored`
   flag is false, which now includes this one. Do not re-implement the JD Fit
   rubric here — it must live in exactly one place.
8. Report to the user: the company, title, location, how it was resolved
   (`resolution`), the `best_branch`, the `jd_fit_score`, and the one-line
   rationale from `matches.local.yaml`.

## Error handling

- Never hand-edit `postings.local.yaml` or `matches.local.yaml`. Every write
  goes through `resolve-posting.py` or `cv-score-postings`.
- If step 4 cannot determine the company or title from the page text, stop and
  report it. Do not guess.
- If `resolve-posting.py` writes a `warning:` line to stderr, include it in the
  report even on success — it means an ATS adapter is broken and the result came
  from a lower tier.

## Permission scope

Steps 1-6 (resolve and store) need no `Edit` grant, because every write goes
through `resolve-posting.py`:

```
Read Bash(python3 resolve-posting.py:*)
```

Step 7 delegates to `cv-score-postings`, which is a separate skill and
inherits its own grants — `score-postings.sh` runs it with
`Edit(matches.local.yaml) Edit(postings.local.yaml) Bash(git show:*)
Bash(git for-each-ref:*)`. The end-to-end skill therefore needs the union of
both scopes; only the resolve-and-store portion is `Edit`-free on its own.
