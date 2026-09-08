#!/bin/bash
# Drains queue.local.txt: resolves each URL, scores it (applying the eligibility
# gate), and writes a submit-ready packet to outbox/ for anything eligible.
#
# Writes no git history. The allowedTools list below deliberately grants no
# staging and no committing of git changes (and no checkout), so an unattended
# run cannot claim an application you did not make. Recording an application is
# cv-log-application's job, and it is interactive only.
#
# Can run on a schedule (see launchd/com.cvapplicate.tailor-packets.plist.example)
# or by hand after adding URLs. Requires the `claude` CLI on PATH — if
# `which claude` differs between your interactive shell and a bare launchd
# environment, update the plist, the same PATH mismatch documented for
# fetch-postings.py's python3.
set -euo pipefail
cd "$(dirname "$0")"

claude -p "Run 'python3 pipeline.py queue' to get this run's queue: a list of URLs and any skipped (non-URL) lines. For each of those URLs, and no others, run cv-resolve-posting, take the posting id from the resolver's JSON, score it, then run cv-tailor-packet only if it is eligible and has no packet yet. Do not tailor any posting that did not come from this run's queue output, even if cv-score-postings' own scan would surface it. Report what was packeted, what the gate rejected and why, and any skipped queue line." \
  --permission-mode acceptEdits \
  --allowedTools "Read Edit(/outbox/**) Edit(/.worktrees/**) Edit(postings.local.yaml) Edit(matches.local.yaml) Bash(python3 resolve-posting.py:*) Bash(python3 pipeline.py:*) Bash(git worktree:*) Bash(git show:*) Bash(git for-each-ref:*) Bash(latexmk:*) Bash(pdflatex:*) Bash(tectonic:*)"
