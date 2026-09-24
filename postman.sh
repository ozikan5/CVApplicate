#!/bin/bash
# Reads recent recruiting mail and proposes application outcomes into
# outcomes.pending.yaml, via the cv-check-mail skill. Confirm them later with
# cv-review-outcomes, which is the only step that writes applications/log.yaml.
#
# Never changes the mailbox or the application log. The grant below has no git
# rights and no edit rights on the log, so a misbehaving run cannot alter either.
#
# This is an unattended run over arbitrary inbound email, so a prompt
# injection in a message body is in scope. No --permission-mode is set: in -p
# mode a tool call not matched by --allowedTools is denied without prompting,
# so the scoped Edit(...) grant above is what actually limits writes.
# --disallowedTools is a backstop on top of that (deny rules win in every
# permission mode, including acceptEdits, were one ever added back) that
# explicitly blocks edits to the project's own code and config. This has not
# yet been verified end-to-end on the real machine — do that once before
# relying on it unattended.
#
# Designed to run once a day via launchd (see
# launchd/com.cvapplicate.postman.plist.example). Requires the `claude` CLI on
# PATH, and IMAP enabled for the Gmail account in .env.
set -euo pipefail
cd "$(dirname "$0")"

claude -p "Run cv-check-mail." \
  --allowedTools "Read Edit(/outcomes.pending.yaml) Bash(python3 pipeline.py:*)" \
  --disallowedTools "Edit(/pipeline.py) Edit(/resolve-posting.py) Edit(/job_fetcher/**) Edit(/applications/**) Edit(/plugins/**) Edit(/.claude/**) Edit(/.env) Edit(/*.sh)"
