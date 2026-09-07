# Posting URL Resolver — Design

**Date:** 2026-09-07
**Status:** Approved, not yet implemented
**Phase:** A of the application-automation roadmap (see [Roadmap](#roadmap))

## Problem

`fetch-postings.py` only discovers postings through the Greenhouse and Lever
board APIs, for companies listed in `companies.local.yaml`. Any posting found
some other way — a link from a friend, a company careers page, a Workday
requisition — cannot enter the pipeline at all. It gets pasted straight into
`cv-review` by hand, which means it is never scored against the other industry
branches, never stored, and never counted in the application history.

There is also no way to ask "how well does *this specific* posting fit me?"
without waiting for the 8:30am scoring run.

## Goals

- Resolve an arbitrary job-posting URL into the posting dict the pipeline
  already speaks, so every downstream consumer works unchanged.
- Prefer structured sources over HTML scraping wherever one exists.
- Store the resolved posting and score it immediately.
- Keep the resolver a pure function of its input: no CV data, no credentials,
  no branch checkouts.
- Stay unit-testable without network access.

## Non-goals

- **LinkedIn and Indeed.** No usable public API, terms that forbid automated
  access, and active anti-automation. Excluded deliberately, not deferred.
- **Taleo and iCIMS adapters.** Both are tenant-configured and inconsistent
  enough that a half-working adapter is worse than the generic HTML path.
- **Browser-based resolution.** Detected and reported (Tier 4), implemented in
  Phase C when the browser profile exists.
- **Tailoring or applying.** Phase A ends at a stored, scored posting.

## Architecture

### Tiers

Every resolution records how it succeeded in a `resolution` field.

| Tier | `resolution` | How | Model needed |
|---|---|---|---|
| 1 | `api` | A per-ATS adapter matched the URL and called its JSON endpoint | No |
| 2 | `jsonld` | No adapter, but the page carries a schema.org `JobPosting` blob | No |
| 3 | `html` | Page fetched and stripped to text; fields inferred from it | Yes |
| 4 | `needs_browser` | Fetch returned a JavaScript shell with no JD content | Phase C |

Tier 2 exists because Google Jobs requires `JobPosting` markup for a listing to
appear in Google's job search, so adoption among careers pages is high. It
covers a meaningful share of no-obvious-ATS pages deterministically and for
free.

### Adapters

`job_fetcher/resolve.py` holds an ordered list of adapters, each exposing
`matches(url) -> bool` and `fetch(url) -> dict | None`. The router tries each in
turn; first match wins. Adding an ATS later is one adapter plus one fixture and
touches nothing else.

| Adapter | URL shape | Endpoint |
|---|---|---|
| Greenhouse | `job-boards.greenhouse.io/<board>/jobs/<id>` | existing boards API, single-job form |
| Lever | `jobs.lever.co/<co>/<uuid>` | existing postings API, single-posting form |
| Workday | `<tenant>.<dc>.myworkdayjobs.com[/<locale>]/<site>/job/<path>` | `/wday/cxs/<tenant>/<site>/job/<path>` (verified — see below) |
| Ashby | `jobs.ashbyhq.com/<org>/<uuid>` | public posting API |
| SmartRecruiters | `jobs.smartrecruiters.com/<co>/<id>` | `api.smartrecruiters.com/v1/companies/<co>/postings/<id>` |

Greenhouse and Lever reuse `normalize_greenhouse` and `normalize_lever` on a
one-element list — no new normalization logic.

Workday's CxS endpoint is undocumented but was verified empirically on
2026-09-07 against two unrelated tenants in different datacenters. It is a
plain `GET` with `Accept: application/json` — no auth, no cookies, no session.
Adapter failure degrades rather than blocks (see [Degradation](#degradation)),
so the lack of a contract is tolerable.

#### Verified Workday field mapping

The response carries `jobPostingInfo`, `hiringOrganization`, `similarJobs`, and
`userAuthenticated`. Only `jobPostingInfo` is used:

| Posting field | Source | Note |
|---|---|---|
| `id` | `workday-<tenant>-<jobReqId>` | `jobReqId` is the stable requisition id, e.g. `JR2004601` |
| `company` | **the tenant subdomain**, title-cased | see the warning below |
| `title` | `jobPostingInfo.title` | |
| `url` | `jobPostingInfo.externalUrl` | canonical, and already locale-free |
| `location` | `jobPostingInfo.location` | `additionalLocations` is ignored |
| `posted_date` | `jobPostingInfo.startDate` | already `YYYY-MM-DD` |
| `description` | `_description_from_html(jobPostingInfo.jobDescription)` | HTML, so reuse the existing helper |

**Do not use `hiringOrganization.name` for `company`.** It is the legal hiring
entity, not the recognisable employer — an NVIDIA requisition returns
`"IL00 Mellanox Technologies, Ltd."`. Storing that would pollute
`applications/log.yaml` with subsidiary names you would not recognise months
later. The tenant subdomain (`nvidia`) is the reliable source. The legal entity
is deliberately not carried in the posting dict at all.

**Do not use `postedOn`.** It is a relative human string (`"Posted Today"`) and
is meaningless once stored. `startDate` is the real date.

#### URL transform

The locale segment is optional and must be stripped when present: a path
segment matching `^[a-z]{2}(-[A-Z]{2})?$` immediately after the host. The site
id is the segment after it (or the first segment when no locale is present).
The tenant is the first label of the host. Everything from `/job/` onward is
carried through verbatim.

### Files

```
job_fetcher/html.py          HTML helpers moved out of ats.py (shared)
job_fetcher/resolve.py       Router, tier logic, adapters
resolve-posting.py           CLI entry point
plugins/cvapplicate/skills/cv-resolve-posting/SKILL.md
tests/test_resolve.py
tests/fixtures/              JSON + HTML fixtures per adapter and tier
```

`_strip_html`, `_description_from_html`, `_description_from_plain`, and
`MAX_DESCRIPTION_LENGTH` move from `ats.py` to `job_fetcher/html.py`; both
modules import from there. This keeps `ats.py` from acquiring a second
responsibility and avoids duplicating the extraction logic.

## Data model

Resolved postings use the existing schema — `id`, `company`, `title`, `url`,
`location`, `posted_date`, `description` — with `store.py` adding `first_seen`,
`notified`, and `scored` as it does for fetched postings. No schema change.

Two additions to resolver output only (not persisted):

- `resolution` — the tier that succeeded.
- `needs_extraction` — true on Tier 3, where `company`, `title`, and
  `location` are present but null and must be inferred. Absent or false on
  Tiers 1 and 2.
- `raw_text` and `hints` — Tier 3 only. `hints` carries `og:title`, `<title>`,
  and the domain, for the skill to work from.

### Id convention

Tier 1 builds the id as `{slug}-{native_id}`, matching what `normalize_*`
produces from a nightly fetch. A pasted Greenhouse link for a company already
in `companies.local.yaml` therefore resolves to the **same id** the nightly
fetch would, and dedupes against it instead of creating a twin entry.

Tiers 2 and 3 have no native id and use `url-<sha1(url)[:12]>`, which is stable
across re-pastes of the same link.

### `notified` on manual adds

Manually resolved postings are stored with `notified: True`. The digest email
exists to tell you about postings you have not seen; you brought this one.

`merge_new_postings` gains an optional `notified: bool = False` parameter —
backward compatible, so the nightly path and its existing tests are unaffected.

## CLI contract

```bash
python3 resolve-posting.py <url>       # resolve → JSON on stdout
python3 resolve-posting.py --store -   # completed posting on stdin → merged into YAML
```

Neither mode calls a model. Human-readable messages go to **stderr**; **stdout
is always machine-readable JSON**.

Store mode is separate so that all YAML writing stays in tested Python. The
model returns a filled-in dict; Python persists it. The model never performs
file surgery.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | resolved (including "already tracked") |
| 2 | bad URL, usage error, or incomplete posting rejected by store mode |
| 3 | `needs_browser` |
| 4 | fetch failed — network, timeout, or HTTP error including a stale 404 |
| 5 | an adapter matched but neither it nor the generic path produced a posting |

Distinct exit codes and JSON-on-stdout are the whole cost of making this
callable from a future orchestration node (see [Roadmap](#roadmap)). No
dependency and no abstraction is added for it.

## The skill

`cv-resolve-posting` is deliberately thin:

1. Run resolve mode; read the JSON.
2. If `needs_extraction`, infer `company`, `title`, and `location` from
   `raw_text` and `hints`. **This is the only judgment in Phase A.**
3. Pipe the completed dict into store mode.
4. Delegate scoring to `cv-score-postings`.

Step 4 matters: the JD Fit rubric lives in one place today and `cv-review` and
`cv-score-postings` agree on it. A third copy would drift. Because store mode
writes `scored: false`, the existing scorer picks the posting up unchanged.

### Permission scope

The resolve-and-store portion (steps 1-3 above) needs no `Edit` grant, because
Python owns every write:

```
Read Bash(python3 resolve-posting.py:*)
```

Step 4 delegates to `cv-score-postings`, which inherits *that* skill's own
grants — `score-postings.sh` runs it with `Edit(matches.local.yaml)
Edit(postings.local.yaml) Bash(git show:*) Bash(git for-each-ref:*)`. The
end-to-end skill therefore needs the union of both scopes; the pattern below
holds only for the part that stops at store mode.

Worth keeping as a pattern for later phases: when deterministic code owns
persistence, *that portion* of the agent needs no write permission — but say
so precisely, scoped to the steps that actually stop at Python, rather than
claiming it for the skill as a whole when a later step delegates onward.

Note also that piping JSON to store mode's stdin (`echo '<json>' | python3
resolve-posting.py --store -`) does not match a `Bash(python3
resolve-posting.py:*)` prefix rule, because the command begins with `echo`.
Write the payload to a temp file and redirect it in instead, so the
invocation's first token stays `python3`.

## Error handling

### Degradation

When an adapter matches a URL but does not produce a posting — its response
did not parse, or its endpoint returned an HTTP error — the router does
**not** fail. It warns on stderr and falls through to the generic path, which
often still works because the JD is present in the served HTML. Exit 5 is
reserved for "adapter failed *and* generic failed."

The one exception is a 404 from the adapter's own endpoint: that means the
posting itself is gone, not that the adapter broke, so it propagates as
`FetchError` (exit 4, "posting no longer available") instead of degrading.
Retrying a dead posting against the generic path would waste a request and
report a confusing failure in place of a clear one.

An ATS changing its API therefore degrades Tier 1 to Tier 2 instead of blocking
you, and the stderr warning tells you which adapter needs attention.

### Cases

- **Stale link** — adapter matches, endpoint 404s. Exit 4 with "posting no
  longer available", distinguished from a generic network error because the
  action you would take differs.
- **Transient network** — one retry with short backoff on timeout and 5xx. No
  retry on 4xx.
- **Already tracked** — the URL resolves to an id already in
  `postings.local.yaml`. Not an error: exit 0, reporting the existing id and its
  `scored` state.
- **`needs_browser`** — exit 3, naming the existing escape hatch: run
  `cv-review` with the JD pasted.
- **Incomplete extraction** — store mode validates `company`, `title`, `url`,
  and `description` are non-null before merging. Otherwise exit 2, writing
  nothing. `description` is included because a posting can pass JSON-LD
  extraction with every identity field present and still carry no JD text (a
  `JobPosting` blob missing `description`, or a Tier 3 page whose text was all
  navigation chrome) — such a posting would store fine, then `cv-score-postings`
  would skip it for having nothing to score, silently dead-ending the flow
  after the CLI already reported success. A partial posting must never land in
  the YAML, because it would either be scored against your branches and
  produce a meaningless number, or never scored at all while looking stored.

## Testing

All fixture-based, no network — `urllib` calls are monkeypatched, matching
`tests/test_ats.py`.

- Router table: URL → expected adapter, including near-misses (a
  `greenhouse.io` marketing page must not match the job adapter).
- Each adapter against a saved JSON fixture, asserting the exact dict.
- JSON-LD: valid `JobPosting`; JSON-LD present with a different `@type`;
  malformed JSON inside the script tag.
- Tier 3: hints extracted from `og:` and `<title>`; `raw_text` non-empty.
- `needs_browser` detection against a JavaScript-shell fixture.
- **Id stability:** the same Greenhouse job resolved by URL produces the
  identical id `normalize_greenhouse` produces from a nightly fetch. This test
  protects the dedup property.
- `merge_new_postings(notified=True)` sets the flag; omitting it preserves
  current behaviour.
- Store mode rejects null `company`/`title`/`url`.
- Exit codes, including adapter-fails-then-generic-succeeds returning 0 with a
  stderr warning.

## Open items

**The Python pipeline is not plugin-distributed.** The skills install via
`/plugin install`, but `fetch-postings.py` and `job_fetcher/` live at repo root,
so a data repo created from this template holds a forked copy that must be
merged from upstream by hand. Phase A's code will not reach a data repo the way
a skill update does. Whether the Python pipeline should ship inside the plugin
is a real question, but it is not Phase A's to answer.

## Roadmap

Phase A is the first of five. Recorded here for context; each phase gets its own
spec.

- **A — Posting URL resolver.** This document.
- **B — Tailor.** Scored matches above a threshold become ready-to-submit
  packets in `outbox/<company>/` (PDF, skills list, gap notes) plus a `draft`
  row in `applications/log.yaml`. Never marks an application as submitted.
- **C — Filler.** Browser automation against a dedicated, tool-owned browser
  profile authenticated once by hand. Prefills application forms from
  `master-data.md` and the outbox packet, then stops for human review. Never
  handles passwords; never submits unsupervised. Also implements Tier 4 of this
  document behind the existing interface.
- **D — Postman.** Reads Gmail over IMAP using the credentials already in
  `.env`, matches mail against `applications/log.yaml`, and updates `outcome` /
  `outcome_date` for unambiguous cases while queueing the rest. Independent of
  A–C.
- **E — Pipeline graph.** A LangGraph graph orchestrating the phases as nodes,
  owning state, retries, checkpoints, and the human-in-the-loop interrupt that
  Phase C's review gate needs. Nodes shell out to the existing scripts and
  skills; nothing is rewritten. LangGraph is deliberately confined to this
  phase — the per-phase tools stay stdlib Python, and the agent runtime remains
  `launchd` → `claude -p` with a per-agent `--allowedTools` scope.
