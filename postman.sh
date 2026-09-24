#!/bin/bash
# Reads recent recruiting mail and proposes application outcomes into
# outcomes.pending.yaml, via the cv-check-mail skill. Confirm them later with
# cv-review-outcomes, which is the only step that writes applications/log.yaml.
#
# Never changes the mailbox or the application log. The grant below has no git
# rights and no edit rights on the log, so a misbehaving run cannot alter either.
#
# Designed to run once a day via launchd (see
# launchd/com.cvapplicate.postman.plist.example). Requires the `claude` CLI on
# PATH, and IMAP enabled for the Gmail account in .env.
set -euo pipefail
cd "$(dirname "$0")"

claude -p "Run cv-check-mail." \
  --permission-mode acceptEdits \
  --allowedTools "Read Edit(/outcomes.pending.yaml) Bash(python3 pipeline.py:*)"
