#!/usr/bin/env python3
"""Small helper subcommands for the unattended tailor-packets/score-postings runners.

Usage:
    ./pipeline.py queue
    ./pipeline.py gate <posting-id>
    ./pipeline.py packet-path <posting-id>
    ./pipeline.py mail
    ./pipeline.py review
    ./pipeline.py packets
    ./pipeline.py fill-context <posting-id>
    ./pipeline.py remember

This exists so the unattended skill runners never need a
`Bash(python3 -c:*)` grant (arbitrary code execution, and a hole in the
"cannot write git history" guarantee those runners rely on). Each subcommand
is a narrow, committed, testable helper instead.

queue        Reads queue.local.txt via job_fetcher.tailor.parse_queue and
             prints {"urls": [...], "skipped": [...]}.
gate         Loads profile.local.yaml and the named posting from
             postings.local.yaml and prints the eligibility-gate JSON:
             location, location_reason, authorization, authorization_reason,
             seeking, max_years_experience_required. If profile.local.yaml
             does not exist, prints {"profile": null} and exits 0.
packet-path  Computes the packet directory for the named posting via
             job_fetcher.tailor.packet_slug against outbox/'s current
             entries and prints {"slug": ..., "path": ..., "exists": bool}.
mail         Reads recruiting mail since the earliest logged application,
             read-only (EXAMINE, BODY.PEEK), and prints the candidates that
             pass the prefilter as JSON: folder, since, warnings, applications,
             candidates, remaining. Credentials come from .env and are never
             printed.
review       Reads outcomes.pending.yaml and the application log, and prints
             each proposal annotated with current_outcome, application_missing,
             regresses and default_answer. Read-only.
packets      Lists outbox/*/packet.yaml as {"packets": [...]}: slug, path,
             posting_id, company, role, created, compile, applied, filled — or
             slug, path and error for a packet that cannot be read.
fill-context Prints everything a form-filling session needs for one packet:
             slug, path, packet, cv_pdf_path (absolute, or null), jd_text,
             answers (answers.local.yaml, or null) and warnings.
remember     Reads {"question": ..., "answer": ...} as JSON on stdin and saves
             it to answers.local.yaml's learned list, replacing an entry with
             the same normalised question. Prints {"remembered": {...}}.

<posting-id> is validated against [A-Za-z0-9._-]+ before it touches
anything else — ATS-supplied ids are not guaranteed to be shell-safe, so
this is enforced rather than assumed.

Human-readable messages go to stderr; stdout is always machine-readable
JSON (and only JSON — nothing is printed on a usage or validation failure).

Exit codes: 0 = success, 2 = usage, invalid posting id, missing credentials,
an unreadable log, an invalid answers file, or internal data inconsistency,
4 = posting id not found, or the mail server unreachable, or no packet for
the posting id.
"""

from __future__ import annotations

import datetime
import imaplib
import json
import os
import re
import socket
import subprocess
import sys

import yaml

from job_fetcher import mailbox, outcomes
from job_fetcher.answers import AnswersError, load_answers, remember
from job_fetcher.env import load_dotenv
from job_fetcher.profile import load_profile, authorization_verdict, location_verdict
from job_fetcher.store import load_postings
from job_fetcher.tailor import packet_slug, parse_queue

USAGE = (
    "usage: pipeline.py queue\n"
    "       pipeline.py gate <posting-id>\n"
    "       pipeline.py packet-path <posting-id>\n"
    "       pipeline.py mail\n"
    "       pipeline.py review\n"
    "       pipeline.py packets\n"
    "       pipeline.py fill-context <posting-id>\n"
    "       pipeline.py remember\n"
)

QUEUE_PATH = "queue.local.txt"
POSTINGS_PATH = "postings.local.yaml"
PROFILE_PATH = "profile.local.yaml"
OUTBOX_PATH = "outbox"
ANSWERS_PATH = "answers.local.yaml"

LOG_REF = "main:applications/log.yaml"
PENDING_PATH = "outcomes.pending.yaml"
ENV_PATH = ".env"
MAIL_CANDIDATE_LIMIT = 200
DEFAULT_IMAP_HOST = "imap.gmail.com"

_connect = mailbox.connect

_POSTING_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_posting_id(posting_id: str) -> bool:
    return bool(_POSTING_ID_RE.match(posting_id))


def _load_posting(posting_id: str):
    postings = load_postings(POSTINGS_PATH)
    for posting in postings:
        if posting.get("id") == posting_id:
            return posting
    return None


def queue_mode() -> int:
    urls, skipped = parse_queue(QUEUE_PATH)
    print(json.dumps({"urls": urls, "skipped": skipped}))
    return 0


def gate_mode(posting_id: str) -> int:
    if not _validate_posting_id(posting_id):
        print(
            f"error: {posting_id!r} is not a valid posting id "
            "(expected only letters, digits, '.', '_', '-')",
            file=sys.stderr,
        )
        return 2

    if not os.path.exists(PROFILE_PATH):
        print(json.dumps({"profile": None}))
        return 0

    profile = load_profile(PROFILE_PATH)

    posting = _load_posting(posting_id)
    if posting is None:
        print(f"error: no posting {posting_id!r} in {POSTINGS_PATH}", file=sys.stderr)
        return 4

    auth_verdict, auth_reason = authorization_verdict(
        posting.get("description") or "", profile.get("work_authorization")
    )
    loc_verdict, loc_reason = location_verdict(
        posting.get("location"), profile.get("locations") or []
    )
    print(json.dumps({
        "location": loc_verdict,
        "location_reason": loc_reason,
        "authorization": auth_verdict,
        "authorization_reason": auth_reason,
        "seeking": profile.get("seeking"),
        "max_years_experience_required": profile.get("max_years_experience_required"),
    }))
    return 0


def _existing_outbox_slugs():
    if not os.path.isdir(OUTBOX_PATH):
        return set()
    return {
        entry for entry in os.listdir(OUTBOX_PATH)
        if os.path.isdir(os.path.join(OUTBOX_PATH, entry))
    }


def _find_existing_packet(posting_id: str, existing):
    """Scan outbox/*/packet.yaml for the one whose posting_id matches."""
    for slug in sorted(existing):
        data, error = _read_packet_yaml(slug)
        if error is None and data.get("posting_id") == posting_id:
            return slug
    return None


def packet_path_mode(posting_id: str) -> int:
    if not _validate_posting_id(posting_id):
        print(
            f"error: {posting_id!r} is not a valid posting id "
            "(expected only letters, digits, '.', '_', '-')",
            file=sys.stderr,
        )
        return 2

    posting = _load_posting(posting_id)
    if posting is None:
        print(f"error: no posting {posting_id!r} in {POSTINGS_PATH}", file=sys.stderr)
        return 4

    existing = _existing_outbox_slugs()

    found = _find_existing_packet(posting_id, existing)
    if found is not None:
        print(json.dumps({
            "slug": found,
            "path": os.path.join(OUTBOX_PATH, found),
            "exists": True,
        }))
        return 0

    slug = packet_slug(
        posting.get("company") or "",
        posting.get("title") or "",
        posting_id,
        existing,
    )
    path = os.path.join(OUTBOX_PATH, slug)
    print(json.dumps({"slug": slug, "path": path, "exists": False}))
    return 0


def _read_log_text() -> str:
    """Read the application log from main.

    applications/log.yaml is tracked on main only and deliberately absent from
    industry branches, so reading it as a path would fail whenever an industry
    branch is checked out.
    """
    result = subprocess.run(["git", "show", LOG_REF], capture_output=True, text=True)
    if result.returncode != 0:
        raise FileNotFoundError(f"{LOG_REF} not found: {result.stderr.strip()}")
    return result.stdout


def _load_applications() -> list:
    entries = yaml.safe_load(_read_log_text()) or []
    if not isinstance(entries, list):
        raise ValueError("applications/log.yaml must be a list of applications")
    applications = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id")
        if not entry_id:
            continue
        company = entry.get("company", "")
        role = entry.get("role", "")
        applications.append({
            "id": str(entry_id),
            "company": str(company) if company is not None else "",
            "role": str(role) if role is not None else "",
            "outcome": entry.get("outcome") or "pending",
            "date_applied": entry.get("date_applied"),
        })
    return applications


def _as_date(value):
    # datetime.datetime is a subclass of datetime.date, so it must be checked
    # first: a hand-edited "date_applied: 2026-09-03 10:00:00" parses as a
    # datetime, and isinstance(value, datetime.date) would otherwise return it
    # unchanged, leaving date/datetime objects mixed in the same min() call.
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value))


def mail_mode() -> int:
    load_dotenv(ENV_PATH)
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_APP_PASSWORD")
    if not user or not password:
        print("error: SMTP_USER and SMTP_APP_PASSWORD must be set in .env", file=sys.stderr)
        return 2
    host = os.environ.get("IMAP_HOST") or DEFAULT_IMAP_HOST

    try:
        applications = _load_applications()
        pending = outcomes.load_pending(PENDING_PATH)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    date_warnings = []
    parsed_dates = []
    for application in applications:
        raw_date = application.get("date_applied")
        if not raw_date:
            continue
        try:
            parsed_dates.append(_as_date(raw_date))
        except ValueError:
            date_warnings.append(
                f"application {application['id']} has an unreadable date_applied "
                f"{raw_date!r}; it was left out of the search start date"
            )

    if not parsed_dates:
        print(json.dumps({"folder": None, "since": None, "warnings": date_warnings,
                          "applications": [], "candidates": [], "remaining": 0}))
        return 0
    since = min(parsed_dates)
    seen = outcomes.seen_ids(pending)

    conn = None
    try:
        conn = _connect(host, user, password)
        folder, warnings = mailbox.open_folder(conn)
        warnings = date_warnings + warnings
        seqs = mailbox.search_since(conn, since)
        headers = mailbox.fetch_parsed(conn, seqs, mailbox.HEADERS_SPEC)
        headers = [h for h in headers if h.get("message_id")]
        own = user.lower()
        fresh = [h for h in headers
                 if h.get("from_address") != own and h.get("message_id") not in seen]
        matched = [h for h in fresh if outcomes.is_candidate(h, applications)]
        selected = matched[:MAIL_CANDIDATE_LIMIT]
        bodies = {}
        if selected:
            for full in mailbox.fetch_parsed(conn, [h["seq"] for h in selected],
                                             mailbox.FULL_SPEC):
                bodies[full["seq"]] = full
    except imaplib.IMAP4.abort:
        # A subclass of imaplib.IMAP4.error (the connection dropped mid-request):
        # must be checked first. The exception text is never interpolated —
        # it can echo server data, and must never be able to leak the password.
        print("error: lost connection to the mailbox", file=sys.stderr)
        return 4
    except (socket.timeout, OSError):
        print("error: lost connection to the mailbox", file=sys.stderr)
        return 4
    except imaplib.IMAP4.error:
        print("error: the mailbox server rejected a request", file=sys.stderr)
        return 4
    except mailbox.MailboxError as error:
        print(f"error: {error}", file=sys.stderr)
        return error.exit_code
    except mailbox.MailboxUnavailable as error:
        print(f"error: {error}", file=sys.stderr)
        return error.exit_code
    finally:
        if conn is not None:
            try:
                conn.logout()
            except Exception:
                pass

    candidates = []
    for header in selected:
        full = bodies.get(header["seq"], header)
        candidates.append({
            "message_id": header["message_id"],
            "from": header["from"],
            "received": header["received"],
            "subject": header["subject"],
            "body": full.get("body", ""),
            "candidate_ids": outcomes.candidate_applications(header, applications),
        })

    print(json.dumps({
        "folder": folder,
        "since": since.isoformat(),
        "warnings": warnings,
        "applications": [{k: a[k] for k in ("id", "company", "role", "outcome")}
                         for a in applications],
        "candidates": candidates,
        "remaining": len(matched) - len(selected),
    }, default=str))
    return 0


def review_mode() -> int:
    try:
        pending = outcomes.load_pending(PENDING_PATH)
        applications = {a["id"]: a for a in _load_applications()}
    except (FileNotFoundError, ValueError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    annotated = []
    for index, proposal in enumerate(pending["proposals"], start=1):
        if not isinstance(proposal, dict):
            print(f"error: {PENDING_PATH} proposal {index} is not a mapping", file=sys.stderr)
            return 2
        application_id = proposal.get("application_id")
        try:
            missing = application_id is not None and application_id not in applications
            current = applications[application_id]["outcome"] if not missing and application_id is not None else None
        except TypeError:
            # application_id is unhashable (e.g. a list or mapping): treat as
            # an application we cannot find rather than crashing.
            missing = True
            current = None
        proposed = proposal.get("proposed_outcome", "")
        annotated.append(dict(
            proposal,
            current_outcome=current,
            application_missing=missing,
            regresses=outcomes.regresses(current, proposed) if current else False,
            default_answer=(not missing) and current is not None
                           and outcomes.default_answer(proposal, current),
        ))
    print(json.dumps({"proposals": annotated}, default=str))
    return 0


PACKET_SUMMARY_FIELDS = (
    "posting_id", "company", "role", "created", "compile", "applied", "filled",
)


def _read_packet_yaml(slug: str):
    """Return (data, error) for outbox/<slug>/packet.yaml; exactly one is None."""
    path = os.path.join(OUTBOX_PATH, slug, "packet.yaml")
    if not os.path.isfile(path):
        return None, "packet.yaml is missing"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except (UnicodeDecodeError, OSError):
        return None, "packet.yaml could not be read"
    except yaml.YAMLError:
        return None, "packet.yaml is not valid YAML"
    if not isinstance(data, dict):
        return None, "packet.yaml is not a mapping"
    return data, None


def packets_mode() -> int:
    entries = []
    for slug in sorted(_existing_outbox_slugs()):
        entry = {"slug": slug, "path": os.path.join(OUTBOX_PATH, slug)}
        data, error = _read_packet_yaml(slug)
        if error is not None:
            entry["error"] = error
        else:
            for field in PACKET_SUMMARY_FIELDS:
                entry[field] = data.get(field)
        entries.append(entry)
    print(json.dumps({"packets": entries}, default=str))
    return 0


def fill_context_mode(posting_id: str) -> int:
    if not _validate_posting_id(posting_id):
        print(
            f"error: {posting_id!r} is not a valid posting id "
            "(expected only letters, digits, '.', '_', '-')",
            file=sys.stderr,
        )
        return 2

    matches = []
    for slug in sorted(_existing_outbox_slugs()):
        data, error = _read_packet_yaml(slug)
        if error is None and data.get("posting_id") == posting_id:
            matches.append((slug, data))
    if not matches:
        print(f"error: no packet for {posting_id!r} in {OUTBOX_PATH}", file=sys.stderr)
        return 4
    if len(matches) > 1:
        slugs = ", ".join(slug for slug, _ in matches)
        print(f"error: several packets claim {posting_id!r}: {slugs}", file=sys.stderr)
        return 2
    slug, packet = matches[0]
    directory = os.path.join(OUTBOX_PATH, slug)

    try:
        answers = load_answers(ANSWERS_PATH)
    except AnswersError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    warnings = []
    if answers is None:
        warnings.append(
            f"{ANSWERS_PATH} not found; copy answers.example.yaml to it. Every "
            "standing question will be asked instead."
        )
    if packet.get("applied") is True:
        warnings.append("this packet is already marked applied")
    if packet.get("compile") != "ok":
        warnings.append(
            f"compile is {packet.get('compile')!r}, not 'ok'; the PDF was not verified"
        )

    cv_pdf = packet.get("cv_pdf")
    cv_pdf_path = None
    if (isinstance(cv_pdf, str) and cv_pdf and os.path.basename(cv_pdf) == cv_pdf
            and os.path.isfile(os.path.join(directory, cv_pdf))):
        pdf_full_path = os.path.join(directory, cv_pdf)
        # Check that the resolved path is within the packet directory
        try:
            pdf_realpath = os.path.realpath(pdf_full_path)
            dir_realpath = os.path.realpath(directory)
            common = os.path.commonpath([pdf_realpath, dir_realpath])
            if common == dir_realpath:
                cv_pdf_path = os.path.abspath(pdf_full_path)
            else:
                warnings.append("no CV PDF in the packet; there is nothing to upload")
        except (ValueError, OSError):
            # ValueError from commonpath if paths are on different drives
            # OSError from realpath issues
            warnings.append("no CV PDF in the packet; there is nothing to upload")
    else:
        warnings.append("no CV PDF in the packet; there is nothing to upload")

    jd_path = os.path.join(directory, "jd.txt")
    jd_text = None
    if os.path.isfile(jd_path):
        try:
            with open(jd_path, "r", encoding="utf-8", errors="replace") as handle:
                jd_text = handle.read()
        except OSError:
            warnings.append(
                "jd.txt is missing; free-text answers have no job description to draw on"
            )
    else:
        warnings.append(
            "jd.txt is missing; free-text answers have no job description to draw on"
        )

    print(json.dumps({
        "slug": slug,
        "path": directory,
        "packet": packet,
        "cv_pdf_path": cv_pdf_path,
        "jd_text": jd_text,
        "answers": answers,
        "warnings": warnings,
    }, default=str))
    return 0


def main(argv: list[str]) -> int:
    arguments = argv[1:]

    if len(arguments) == 1 and arguments[0] == "queue":
        return queue_mode()
    if len(arguments) == 2 and arguments[0] == "gate":
        return gate_mode(arguments[1])
    if len(arguments) == 2 and arguments[0] == "packet-path":
        return packet_path_mode(arguments[1])
    if len(arguments) == 1 and arguments[0] == "mail":
        return mail_mode()
    if len(arguments) == 1 and arguments[0] == "review":
        return review_mode()
    if len(arguments) == 1 and arguments[0] == "packets":
        return packets_mode()
    if len(arguments) == 2 and arguments[0] == "fill-context":
        return fill_context_mode(arguments[1])

    print(USAGE, file=sys.stderr, end="")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
