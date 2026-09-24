#!/bin/bash
# Scores every not-yet-scored posting in postings.local.yaml against each industry
# branch's CV data, via the cv-score-postings skill. Read-only: only ever writes
# matches.local.yaml and the `scored` flag in postings.local.yaml — never edits
# cv.tex or master-data.md, never commits, never checks out a branch.
#
# Designed to run once a day via launchd, after fetch-postings.py (see
# launchd/com.cvapplicate.score-postings.plist.example). Requires the `claude` CLI
# on PATH — if `which claude` differs between your interactive shell and this
# script's launchd environment, update the ProgramArguments path in the plist,
# the same PATH mismatch documented for fetch-postings.py's python3.
#
# No --permission-mode is set: in -p mode a tool call not matched by
# --allowedTools is denied without prompting, so the scoped Edit(...) grant
# above is what actually limits writes. --disallowedTools is a backstop on
# top of that (deny rules win in every permission mode) blocking edits to the
# project's own code and config.
set -euo pipefail
cd "$(dirname "$0")"

claude -p "Run cv-score-postings" \
  --allowedTools "Read Edit(matches.local.yaml) Edit(postings.local.yaml) Bash(git show:*) Bash(git for-each-ref:*) Bash(python3 pipeline.py:*)" \
  --disallowedTools "Edit(/pipeline.py) Edit(/resolve-posting.py) Edit(/job_fetcher/**) Edit(/applications/**) Edit(/plugins/**) Edit(/.claude/**) Edit(/.env) Edit(/*.sh)"
