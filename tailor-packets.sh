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

claude -p "Drain queue.local.txt: for each URL, run cv-resolve-posting, then score it, then run cv-tailor-packet for every eligible posting that has no packet yet. Report what was packeted, what the gate rejected and why, and any queue line that was not a URL." \
  --permission-mode acceptEdits \
  --allowedTools "Read Edit(/outbox/**) Edit(/.worktrees/**) Edit(postings.local.yaml) Edit(matches.local.yaml) Bash(python3 resolve-posting.py:*) Bash(python3 -c:*) Bash(git worktree:*) Bash(git show:*) Bash(git for-each-ref:*) Bash(latexmk:*) Bash(pdflatex:*) Bash(tectonic:*)"
