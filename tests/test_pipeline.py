from __future__ import annotations

import datetime
import importlib.util
import io
import json
import os
from pathlib import Path

import yaml

from job_fetcher.store import save_postings

REPO_ROOT = Path(__file__).parent.parent


def _load_cli():
    spec = importlib.util.spec_from_file_location("pipeline", REPO_ROOT / "pipeline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = _load_cli()

POSTING = {
    "id": "stripe-8172508",
    "company": "Stripe",
    "title": "Abuse Investigator",
    "url": "https://job-boards.greenhouse.io/stripe/jobs/8172508",
    "location": "Dublin",
    "description": "Investigate abuse. Requires 2+ years of experience.",
    "scored": False,
    "packeted": False,
}

PROFILE_YAML = """
seeking: full-time
locations:
  - Dublin
  - Remote
max_years_experience_required: 5
work_authorization: unrestricted
"""


def _chdir_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "QUEUE_PATH", str(tmp_path / "queue.local.txt"))
    monkeypatch.setattr(cli, "POSTINGS_PATH", str(tmp_path / "postings.local.yaml"))
    monkeypatch.setattr(cli, "PROFILE_PATH", str(tmp_path / "profile.local.yaml"))
    monkeypatch.setattr(cli, "OUTBOX_PATH", str(tmp_path / "outbox"))


# --- queue ---------------------------------------------------------------


def test_queue_prints_urls_and_skipped_lines(tmp_path, monkeypatch, capsys):
    _chdir_project(tmp_path, monkeypatch)
    (tmp_path / "queue.local.txt").write_text(
        "https://example.com/a\nremember the NVIDIA one\n", encoding="utf-8"
    )

    exit_code = cli.main(["pipeline.py", "queue"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "urls": ["https://example.com/a"],
        "skipped": ["remember the NVIDIA one"],
    }


def test_queue_handles_absent_file(tmp_path, monkeypatch, capsys):
    _chdir_project(tmp_path, monkeypatch)

    exit_code = cli.main(["pipeline.py", "queue"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"urls": [], "skipped": []}


# --- gate ------------------------------------------------------------------


def test_gate_prints_the_expected_keys(tmp_path, monkeypatch, capsys):
    _chdir_project(tmp_path, monkeypatch)
    (tmp_path / "profile.local.yaml").write_text(PROFILE_YAML, encoding="utf-8")
    save_postings(str(tmp_path / "postings.local.yaml"), [POSTING])

    exit_code = cli.main(["pipeline.py", "gate", POSTING["id"]])

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert set(result.keys()) == {
        "location",
        "location_reason",
        "authorization",
        "authorization_reason",
        "seeking",
        "max_years_experience_required",
    }
    assert result["location"] == "ok"
    assert result["location_reason"] is None
    assert result["seeking"] == "full-time"
    assert result["max_years_experience_required"] == 5


def test_gate_with_no_profile_prints_null_and_exits_zero(tmp_path, monkeypatch, capsys):
    _chdir_project(tmp_path, monkeypatch)
    save_postings(str(tmp_path / "postings.local.yaml"), [POSTING])

    exit_code = cli.main(["pipeline.py", "gate", POSTING["id"]])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"profile": None}


def test_gate_unknown_posting_id_exits_four(tmp_path, monkeypatch, capsys):
    _chdir_project(tmp_path, monkeypatch)
    (tmp_path / "profile.local.yaml").write_text(PROFILE_YAML, encoding="utf-8")
    save_postings(str(tmp_path / "postings.local.yaml"), [POSTING])

    exit_code = cli.main(["pipeline.py", "gate", "does-not-exist"])

    assert exit_code == 4
    assert capsys.readouterr().out == ""


def test_gate_rejects_a_shell_metacharacter_in_the_id(tmp_path, monkeypatch, capsys):
    """Regression test: ATS ids are uncoerced third-party data and must never be
    trusted to be shell-safe just because they look slug-shaped in practice."""
    _chdir_project(tmp_path, monkeypatch)
    (tmp_path / "profile.local.yaml").write_text(PROFILE_YAML, encoding="utf-8")
    save_postings(str(tmp_path / "postings.local.yaml"), [POSTING])

    exit_code = cli.main(["pipeline.py", "gate", '"; git commit -am x'])

    assert exit_code == 2
    assert capsys.readouterr().out == ""


# --- packet-path -------------------------------------------------------------


def test_packet_path_reports_not_existing_for_a_fresh_outbox(tmp_path, monkeypatch, capsys):
    _chdir_project(tmp_path, monkeypatch)
    save_postings(str(tmp_path / "postings.local.yaml"), [POSTING])

    exit_code = cli.main(["pipeline.py", "packet-path", POSTING["id"]])

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["exists"] is False
    assert result["slug"] == "stripe-abuse-investigator"
    assert result["path"].endswith("stripe-abuse-investigator")


def test_packet_path_reports_existing_when_directory_is_present(tmp_path, monkeypatch, capsys):
    _chdir_project(tmp_path, monkeypatch)
    save_postings(str(tmp_path / "postings.local.yaml"), [POSTING])
    packet_dir = tmp_path / "outbox" / "stripe-abuse-investigator"
    packet_dir.mkdir(parents=True)
    (packet_dir / "packet.yaml").write_text(
        f"posting_id: {POSTING['id']}\n", encoding="utf-8"
    )

    exit_code = cli.main(["pipeline.py", "packet-path", POSTING["id"]])

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["exists"] is True
    assert result["slug"] == "stripe-abuse-investigator"


def test_packet_path_rejects_a_shell_metacharacter_in_the_id(tmp_path, monkeypatch, capsys):
    _chdir_project(tmp_path, monkeypatch)

    exit_code = cli.main(["pipeline.py", "packet-path", "$(rm -rf /)"])

    assert exit_code == 2
    assert capsys.readouterr().out == ""


# --- usage -------------------------------------------------------------------


def test_usage_error_with_no_subcommand(capsys):
    exit_code = cli.main(["pipeline.py"])

    assert exit_code == 2
    assert "usage:" in capsys.readouterr().err
    assert capsys.readouterr().out == ""


# --- mail ----------------------------------------------------------------

import datetime
import imaplib
import re as _re
import socket

import pytest

from job_fetcher import mailbox
from tests.mail_fixtures import build_message

LOG_YAML = """
- id: citadel-swe-2026-08
  company: "Citadel"
  role: "Software Engineering Intern"
  date_applied: 2026-08-19
  outcome: pending
- id: microsoft-a
  company: "Microsoft"
  role: "SWE Intern, AI/ML"
  date_applied: 2026-08-24
  outcome: pending
"""

PASSWORD = "s3cr3t-p4ss-XYZ"


class FakeIMAP:
    def __init__(self, messages, list_lines=None):
        self.messages = messages
        self.list_lines = list_lines or [b'(\\HasNoChildren \\All) "/" "[Gmail]/All Mail"']
        self.logged_out = False

    def list(self, *args):
        return "OK", self.list_lines

    def select(self, mailbox="INBOX", readonly=False):
        assert readonly is True
        return "OK", [b"1"]

    def search(self, charset, *criteria):
        return "OK", [" ".join(self.messages).encode()]

    def fetch(self, message_set, spec):
        assert "PEEK" in spec
        data = []
        for seq in message_set.split(","):
            raw = self.messages[seq]
            if "HEADER.FIELDS" in spec:
                raw = _re.split(rb"\r?\n\r?\n", raw, maxsplit=1)[0] + b"\r\n\r\n"
            data.append((f"{seq} (BODY[] {{{len(raw)}}}".encode(), raw))
            data.append(b")")
        return "OK", data

    def logout(self):
        self.logged_out = True
        return "BYE", []

    def __getattr__(self, name):
        raise AssertionError(f"forbidden IMAP command issued: {name}")


def _mail_project(tmp_path, monkeypatch, messages=None, log_yaml=LOG_YAML):
    _chdir_project(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "PENDING_PATH", str(tmp_path / "outcomes.pending.yaml"))
    monkeypatch.setattr(cli, "ENV_PATH", str(tmp_path / "absent.env"))
    monkeypatch.setattr(cli, "_read_log_text", lambda: log_yaml)
    monkeypatch.setenv("SMTP_USER", "me@gmail.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", PASSWORD)
    fake = FakeIMAP(messages or {})
    monkeypatch.setattr(cli, "_connect", lambda host, user, password: fake)
    return fake


def _three_messages():
    return {
        "1": build_message(sender="Citadel <no-reply@citadel.com>", subject="Your application",
                           plain="Unfortunately, we will not be moving forward.",
                           message_id="<rej@citadel.com>"),
        "2": build_message(sender="A Friend <friend@example.org>", subject="dinner?",
                           plain="Friday?", message_id="<friend@example.org>"),
        "3": build_message(sender="Me <me@gmail.com>", subject="Citadel follow-up",
                           plain="note to self", message_id="<self@gmail.com>"),
    }


def test_mail_returns_only_recruiting_candidates(tmp_path, monkeypatch, capsys):
    fake = _mail_project(tmp_path, monkeypatch, _three_messages())

    exit_code = cli.main(["pipeline.py", "mail"])

    out = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert out["folder"] == '"[Gmail]/All Mail"'
    assert out["since"] == "2026-08-19"
    assert [c["message_id"] for c in out["candidates"]] == ["<rej@citadel.com>"]
    assert out["candidates"][0]["candidate_ids"] == ["citadel-swe-2026-08"]
    assert "not be moving forward" in out["candidates"][0]["body"]
    assert out["remaining"] == 0
    assert fake.logged_out


def test_mail_skips_already_seen_messages(tmp_path, monkeypatch, capsys):
    _mail_project(tmp_path, monkeypatch, _three_messages())
    (tmp_path / "outcomes.pending.yaml").write_text(
        "seen:\n  - '<rej@citadel.com>'\nproposals: []\n", encoding="utf-8"
    )

    cli.main(["pipeline.py", "mail"])

    assert json.loads(capsys.readouterr().out)["candidates"] == []


def test_mail_caps_candidates_and_reports_the_remainder(tmp_path, monkeypatch, capsys):
    messages = {
        "1": build_message(sender="Citadel <a@citadel.com>", subject="One", plain="x",
                           message_id="<1@citadel.com>"),
        "2": build_message(sender="Citadel <b@citadel.com>", subject="Two", plain="x",
                           message_id="<2@citadel.com>"),
    }
    _mail_project(tmp_path, monkeypatch, messages)
    monkeypatch.setattr(cli, "MAIL_CANDIDATE_LIMIT", 1)

    cli.main(["pipeline.py", "mail"])

    out = json.loads(capsys.readouterr().out)
    assert len(out["candidates"]) == 1
    assert out["remaining"] == 1


def test_mail_never_prints_the_password_on_success(tmp_path, monkeypatch, capsys):
    _mail_project(tmp_path, monkeypatch, _three_messages())

    cli.main(["pipeline.py", "mail"])

    captured = capsys.readouterr()
    assert PASSWORD not in captured.out
    assert PASSWORD not in captured.err


class _AuthFailSSL:
    def __init__(self, *args, **kwargs):
        pass

    def login(self, user, password):
        raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")


def test_mail_auth_failure_exits_2_without_leaking_the_password(tmp_path, monkeypatch, capsys):
    _mail_project(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "_connect", mailbox.connect)
    monkeypatch.setattr(mailbox.imaplib, "IMAP4_SSL", _AuthFailSSL)

    exit_code = cli.main(["pipeline.py", "mail"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "Enable IMAP" in captured.err
    assert PASSWORD not in captured.err


def test_mail_network_failure_exits_4(tmp_path, monkeypatch, capsys):
    _mail_project(tmp_path, monkeypatch)

    def unreachable(host, user, password):
        raise mailbox.MailboxUnavailable("could not reach imap.gmail.com: timeout")

    monkeypatch.setattr(cli, "_connect", unreachable)

    assert cli.main(["pipeline.py", "mail"]) == 4
    assert capsys.readouterr().out == ""


def test_mail_missing_credentials_exits_2(tmp_path, monkeypatch, capsys):
    _mail_project(tmp_path, monkeypatch)
    monkeypatch.delenv("SMTP_APP_PASSWORD")

    assert cli.main(["pipeline.py", "mail"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "SMTP_APP_PASSWORD" in captured.err


def test_mail_unreadable_log_exits_2(tmp_path, monkeypatch, capsys):
    _mail_project(tmp_path, monkeypatch)

    def no_log():
        raise FileNotFoundError("main:applications/log.yaml not found")

    monkeypatch.setattr(cli, "_read_log_text", no_log)

    assert cli.main(["pipeline.py", "mail"]) == 2
    assert capsys.readouterr().out == ""


# --- mail: malformed date_applied -----------------------------------------

ONE_BAD_DATE_LOG_YAML = """
- id: citadel-swe-2026-08
  company: "Citadel"
  role: "Software Engineering Intern"
  date_applied: TBD
  outcome: pending
- id: microsoft-a
  company: "Microsoft"
  role: "SWE Intern, AI/ML"
  date_applied: 2026-08-24
  outcome: pending
"""

ALL_BAD_DATE_LOG_YAML = """
- id: citadel-swe-2026-08
  company: "Citadel"
  role: "Software Engineering Intern"
  date_applied: TBD
  outcome: pending
- id: microsoft-a
  company: "Microsoft"
  role: "SWE Intern, AI/ML"
  date_applied: unknown
  outcome: pending
"""

MAPPING_LOG_YAML = """
citadel-swe-2026-08:
  company: "Citadel"
  role: "Software Engineering Intern"
  date_applied: 2026-08-19
  outcome: pending
"""


def test_mail_one_unparseable_date_warns_but_keeps_going(tmp_path, monkeypatch, capsys):
    _mail_project(tmp_path, monkeypatch, _three_messages(), log_yaml=ONE_BAD_DATE_LOG_YAML)

    exit_code = cli.main(["pipeline.py", "mail"])

    out = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert out["since"] == "2026-08-24"
    assert len(out["warnings"]) == 1
    assert "citadel-swe-2026-08" in out["warnings"][0]
    assert "TBD" in out["warnings"][0]
    assert any(a["id"] == "citadel-swe-2026-08" for a in out["applications"])


def test_mail_all_dates_unparseable_exits_zero_with_warnings(tmp_path, monkeypatch, capsys):
    _mail_project(tmp_path, monkeypatch, log_yaml=ALL_BAD_DATE_LOG_YAML)

    exit_code = cli.main(["pipeline.py", "mail"])

    out = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert out["since"] is None
    assert out["candidates"] == []
    assert len(out["warnings"]) == 2
    joined = " ".join(out["warnings"])
    assert "citadel-swe-2026-08" in joined
    assert "microsoft-a" in joined


def test_mail_mapping_shaped_log_exits_2(tmp_path, monkeypatch, capsys):
    _mail_project(tmp_path, monkeypatch, log_yaml=MAPPING_LOG_YAML)

    exit_code = cli.main(["pipeline.py", "mail"])

    assert exit_code == 2
    assert capsys.readouterr().out == ""


# --- mail: headers-first property -------------------------------------------


def test_mail_fetches_full_bodies_only_for_selected_candidates(tmp_path, monkeypatch, capsys):
    messages = {}
    for i in range(1, 19):
        messages[str(i)] = build_message(
            sender=f"Friend{i} <friend{i}@example.org>", subject="hi",
            plain="just saying hi", message_id=f"<friend{i}@example.org>",
        )
    messages["19"] = build_message(
        sender="Citadel <no-reply@citadel.com>", subject="Your application",
        plain="Unfortunately, we will not be moving forward.",
        message_id="<rej19@citadel.com>",
    )
    messages["20"] = build_message(
        sender="Microsoft <no-reply@microsoft.com>", subject="Update on your application",
        plain="Thanks for applying.", message_id="<rej20@microsoft.com>",
    )
    fake = _mail_project(tmp_path, monkeypatch, messages)

    fetch_calls = []
    original_fetch = fake.fetch

    def recording_fetch(message_set, spec):
        fetch_calls.append((message_set, spec))
        return original_fetch(message_set, spec)

    fake.fetch = recording_fetch

    exit_code = cli.main(["pipeline.py", "mail"])

    assert exit_code == 0
    header_calls = [c for c in fetch_calls if c[1] == mailbox.HEADERS_SPEC]
    full_calls = [c for c in fetch_calls if c[1] == mailbox.FULL_SPEC]

    assert len(header_calls) == 1
    assert set(header_calls[0][0].split(",")) == {str(i) for i in range(1, 21)}

    assert len(full_calls) == 1
    assert set(full_calls[0][0].split(",")) == {"19", "20"}


# --- review ----------------------------------------------------------------


def _review_project(tmp_path, monkeypatch, pending_yaml, log_yaml=LOG_YAML):
    _chdir_project(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "PENDING_PATH", str(tmp_path / "outcomes.pending.yaml"))
    monkeypatch.setattr(cli, "_read_log_text", lambda: log_yaml)
    (tmp_path / "outcomes.pending.yaml").write_text(pending_yaml, encoding="utf-8")


def test_review_annotates_a_clear_proposal(tmp_path, monkeypatch, capsys):
    _review_project(tmp_path, monkeypatch, """
seen: []
proposals:
  - message_id: "<rej@citadel.com>"
    received: 2026-09-02
    proposed_outcome: rejected
    application_id: citadel-swe-2026-08
    confidence: high
""")

    assert cli.main(["pipeline.py", "review"]) == 0

    proposal = json.loads(capsys.readouterr().out)["proposals"][0]
    assert proposal["current_outcome"] == "pending"
    assert proposal["regresses"] is False
    assert proposal["default_answer"] is True
    assert proposal["received"] == "2026-09-02"


def test_review_flags_a_regression(tmp_path, monkeypatch, capsys):
    log = LOG_YAML.replace("  outcome: pending\n- id: microsoft-a", "  outcome: interview\n- id: microsoft-a", 1)
    _review_project(tmp_path, monkeypatch, """
proposals:
  - message_id: "<oa@citadel.com>"
    proposed_outcome: assessment
    application_id: citadel-swe-2026-08
    confidence: high
""", log_yaml=log)

    cli.main(["pipeline.py", "review"])

    proposal = json.loads(capsys.readouterr().out)["proposals"][0]
    assert proposal["current_outcome"] == "interview"
    assert proposal["regresses"] is True
    assert proposal["default_answer"] is False


def test_review_defaults_an_ambiguous_proposal_to_no(tmp_path, monkeypatch, capsys):
    _review_project(tmp_path, monkeypatch, """
proposals:
  - message_id: "<m@microsoft.com>"
    proposed_outcome: rejected
    application_id: null
    candidates: [microsoft-a]
    confidence: high
""")

    cli.main(["pipeline.py", "review"])

    proposal = json.loads(capsys.readouterr().out)["proposals"][0]
    assert proposal["current_outcome"] is None
    assert proposal["default_answer"] is False


def test_review_marks_a_proposal_for_a_deleted_application(tmp_path, monkeypatch, capsys):
    _review_project(tmp_path, monkeypatch, """
proposals:
  - message_id: "<x@gone.com>"
    proposed_outcome: rejected
    application_id: no-longer-in-the-log
    confidence: high
""")

    cli.main(["pipeline.py", "review"])

    proposal = json.loads(capsys.readouterr().out)["proposals"][0]
    assert proposal["application_missing"] is True
    assert proposal["default_answer"] is False


def test_review_with_no_pending_file(tmp_path, monkeypatch, capsys):
    _chdir_project(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "PENDING_PATH", str(tmp_path / "absent.yaml"))
    monkeypatch.setattr(cli, "_read_log_text", lambda: LOG_YAML)

    assert cli.main(["pipeline.py", "review"]) == 0
    assert json.loads(capsys.readouterr().out) == {"proposals": []}


def test_review_rejects_a_non_mapping_proposal(tmp_path, monkeypatch, capsys):
    _review_project(tmp_path, monkeypatch, """
proposals:
  - "just a string, not a mapping"
""")

    exit_code = cli.main(["pipeline.py", "review"])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == f"error: {cli.PENDING_PATH} proposal 1 is not a mapping"


def test_review_treats_unhashable_application_id_as_missing(tmp_path, monkeypatch, capsys):
    _review_project(tmp_path, monkeypatch, """
proposals:
  - message_id: "<weird@x.com>"
    proposed_outcome: rejected
    application_id: [not, a, string]
    confidence: high
""")

    exit_code = cli.main(["pipeline.py", "review"])

    assert exit_code == 0
    proposal = json.loads(capsys.readouterr().out)["proposals"][0]
    assert proposal["application_missing"] is True
    assert proposal["current_outcome"] is None
    assert proposal["regresses"] is False
    assert proposal["default_answer"] is False


# --- mail: network/protocol failure after login (I1) ------------------------


def _raise(exc):
    def _fn(*args, **kwargs):
        raise exc
    return _fn


def test_mail_fetch_abort_exits_4(tmp_path, monkeypatch, capsys):
    fake = _mail_project(tmp_path, monkeypatch, _three_messages())
    fake.fetch = _raise(imaplib.IMAP4.abort("BYE"))

    exit_code = cli.main(["pipeline.py", "mail"])

    captured = capsys.readouterr()
    assert exit_code == 4
    assert captured.out == ""
    assert "lost connection to the mailbox" in captured.err
    assert PASSWORD not in captured.err
    assert fake.logged_out


def test_mail_fetch_timeout_exits_4(tmp_path, monkeypatch, capsys):
    fake = _mail_project(tmp_path, monkeypatch, _three_messages())
    fake.fetch = _raise(socket.timeout())

    exit_code = cli.main(["pipeline.py", "mail"])

    captured = capsys.readouterr()
    assert exit_code == 4
    assert captured.out == ""
    assert "lost connection to the mailbox" in captured.err
    assert PASSWORD not in captured.err


def test_mail_fetch_os_error_exits_4(tmp_path, monkeypatch, capsys):
    fake = _mail_project(tmp_path, monkeypatch, _three_messages())
    fake.fetch = _raise(OSError("network is unreachable"))

    exit_code = cli.main(["pipeline.py", "mail"])

    captured = capsys.readouterr()
    assert exit_code == 4
    assert captured.out == ""
    assert "lost connection to the mailbox" in captured.err
    assert PASSWORD not in captured.err
    assert "network is unreachable" not in captured.err


def test_mail_fetch_imap_error_exits_4(tmp_path, monkeypatch, capsys):
    fake = _mail_project(tmp_path, monkeypatch, _three_messages())
    fake.fetch = _raise(imaplib.IMAP4.error("server says no"))

    exit_code = cli.main(["pipeline.py", "mail"])

    captured = capsys.readouterr()
    assert exit_code == 4
    assert captured.out == ""
    assert "the mailbox server rejected a request" in captured.err
    assert PASSWORD not in captured.err
    assert "server says no" not in captured.err


def test_mail_search_abort_exits_4(tmp_path, monkeypatch, capsys):
    fake = _mail_project(tmp_path, monkeypatch, _three_messages())
    fake.search = _raise(imaplib.IMAP4.abort("BYE"))

    exit_code = cli.main(["pipeline.py", "mail"])

    captured = capsys.readouterr()
    assert exit_code == 4
    assert captured.out == ""
    assert "lost connection to the mailbox" in captured.err
    assert PASSWORD not in captured.err
    assert fake.logged_out


# --- _as_date: datetime mixed with date (M2) --------------------------------


def test_as_date_converts_a_datetime_to_a_date():
    assert cli._as_date(datetime.datetime(2026, 9, 3, 10, 0, 0)) == datetime.date(2026, 9, 3)


def test_as_date_leaves_a_plain_date_unchanged():
    assert cli._as_date(datetime.date(2026, 9, 3)) == datetime.date(2026, 9, 3)


MIXED_DATE_LOG_YAML = """
- id: citadel-swe-2026-08
  company: "Citadel"
  role: "Software Engineering Intern"
  date_applied: 2026-09-03 10:00:00
  outcome: pending
- id: microsoft-a
  company: "Microsoft"
  role: "SWE Intern, AI/ML"
  date_applied: 2026-08-24
  outcome: pending
"""


def test_mail_mixing_a_datetime_and_a_date_does_not_crash_min(tmp_path, monkeypatch, capsys):
    _mail_project(tmp_path, monkeypatch, _three_messages(), log_yaml=MIXED_DATE_LOG_YAML)

    exit_code = cli.main(["pipeline.py", "mail"])

    out = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert out["since"] == "2026-08-24"


# --- _load_applications: non-string company/role/id (M3) --------------------


def test_load_applications_skips_non_mapping_and_missing_id_entries(tmp_path, monkeypatch):
    _chdir_project(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "_read_log_text", lambda: """
- id: a
  company: "A Co"
- "just a string"
- company: "No Id Co"
- id: null
  company: "Null Id Co"
""")

    applications = cli._load_applications()

    assert [a["id"] for a in applications] == ["a"]


def test_load_applications_coerces_non_string_company_role_and_id(tmp_path, monkeypatch):
    _chdir_project(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "_read_log_text", lambda: """
- id: 1010
  company: 1010
  role: 7
  outcome: pending
""")

    applications = cli._load_applications()

    assert applications == [{
        "id": "1010", "company": "1010", "role": "7",
        "outcome": "pending", "date_applied": None,
    }]


def test_mail_with_a_numeric_company_does_not_crash(tmp_path, monkeypatch, capsys):
    log = """
- id: acme-2026-08
  company: 1010
  role: SWE
  date_applied: 2026-08-19
  outcome: pending
"""
    _mail_project(tmp_path, monkeypatch, _three_messages(), log_yaml=log)

    exit_code = cli.main(["pipeline.py", "mail"])

    assert exit_code == 0
    assert capsys.readouterr().out != ""


def test_review_with_a_non_string_id_log_entry_does_not_crash(tmp_path, monkeypatch, capsys):
    log = """
- id: 1010
  company: "Weird Co"
  outcome: pending
"""
    _review_project(tmp_path, monkeypatch, """
proposals:
  - message_id: "<x@weird.com>"
    proposed_outcome: rejected
    application_id: "1010"
    confidence: high
""", log_yaml=log)

    exit_code = cli.main(["pipeline.py", "review"])

    out = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert out["proposals"][0]["current_outcome"] == "pending"


# --- packets / fill-context ------------------------------------------------


FILL_PACKET = {
    "posting_id": "greenhouse-citadel-123",
    "company": "Citadel",
    "role": "SWE Intern",
    "url": "https://job-boards.greenhouse.io/citadel/jobs/123",
    "industry_branch": "quant-trading",
    "created": datetime.date(2026, 9, 20),
    "cv_pdf": "Ozan_Kan_CV_Citadel.pdf",
    "cv_tex": "cv.tex",
    "compile": "ok",
    "applied": False,
}

ANSWERS_YAML = """
contact:
  first_name: "Ozan"
  phone: ""
work_authorization:
  requires_sponsorship_now: "No"
learned: []
"""


def _fill_project(tmp_path, monkeypatch):
    _chdir_project(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "ANSWERS_PATH", str(tmp_path / "answers.local.yaml"))


def _make_packet(tmp_path, slug="citadel-swe-intern", packet=None, pdf=True,
                 jd="Build low-latency systems."):
    directory = tmp_path / "outbox" / slug
    directory.mkdir(parents=True)
    data = dict(FILL_PACKET if packet is None else packet)
    (directory / "packet.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    if pdf:
        (directory / data.get("cv_pdf", "cv.pdf")).write_bytes(b"%PDF-1.4")
    if jd is not None:
        (directory / "jd.txt").write_text(jd, encoding="utf-8")
    return directory


def _write_answers(tmp_path, text=ANSWERS_YAML):
    (tmp_path / "answers.local.yaml").write_text(text, encoding="utf-8")


def test_packets_lists_each_packet(tmp_path, monkeypatch, capsys):
    _fill_project(tmp_path, monkeypatch)
    _make_packet(tmp_path)

    assert cli.main(["pipeline.py", "packets"]) == 0

    entry = json.loads(capsys.readouterr().out)["packets"][0]
    assert entry["slug"] == "citadel-swe-intern"
    assert entry["posting_id"] == "greenhouse-citadel-123"
    assert entry["company"] == "Citadel"
    assert entry["created"] == "2026-09-20"
    assert entry["applied"] is False
    assert entry["filled"] is None


def test_packets_with_no_outbox(tmp_path, monkeypatch, capsys):
    _fill_project(tmp_path, monkeypatch)

    assert cli.main(["pipeline.py", "packets"]) == 0
    assert json.loads(capsys.readouterr().out) == {"packets": []}


def test_packets_reports_an_unreadable_packet_instead_of_dropping_it(tmp_path, monkeypatch, capsys):
    _fill_project(tmp_path, monkeypatch)
    broken = tmp_path / "outbox" / "broken"
    broken.mkdir(parents=True)
    (broken / "packet.yaml").write_text("posting_id: [unclosed\n", encoding="utf-8")
    (tmp_path / "outbox" / "empty").mkdir()
    listed = tmp_path / "outbox" / "listed"
    listed.mkdir()
    (listed / "packet.yaml").write_text("- not\n- a mapping\n", encoding="utf-8")

    assert cli.main(["pipeline.py", "packets"]) == 0

    entries = {e["slug"]: e for e in json.loads(capsys.readouterr().out)["packets"]}
    assert entries["broken"]["error"] == "packet.yaml is not valid YAML"
    assert entries["empty"]["error"] == "packet.yaml is missing"
    assert entries["listed"]["error"] == "packet.yaml is not a mapping"


def test_fill_context_gathers_the_session(tmp_path, monkeypatch, capsys):
    _fill_project(tmp_path, monkeypatch)
    directory = _make_packet(tmp_path)
    _write_answers(tmp_path)

    assert cli.main(["pipeline.py", "fill-context", "greenhouse-citadel-123"]) == 0

    context = json.loads(capsys.readouterr().out)
    assert context["slug"] == "citadel-swe-intern"
    assert context["packet"]["company"] == "Citadel"
    assert context["packet"]["created"] == "2026-09-20"
    assert os.path.isabs(context["cv_pdf_path"])
    assert os.path.samefile(context["cv_pdf_path"], directory / "Ozan_Kan_CV_Citadel.pdf")
    assert context["jd_text"] == "Build low-latency systems."
    assert context["answers"]["contact"]["phone"] == ""
    assert context["answers"]["work_authorization"]["requires_sponsorship_now"] == "No"
    assert context["warnings"] == []


def test_fill_context_warns_without_an_answers_file(tmp_path, monkeypatch, capsys):
    _fill_project(tmp_path, monkeypatch)
    _make_packet(tmp_path)

    assert cli.main(["pipeline.py", "fill-context", "greenhouse-citadel-123"]) == 0

    context = json.loads(capsys.readouterr().out)
    assert context["answers"] is None
    assert len(context["warnings"]) == 1
    assert "answers.local.yaml" in context["warnings"][0]


def test_fill_context_warns_on_an_applied_packet_and_a_failed_compile(tmp_path, monkeypatch, capsys):
    _fill_project(tmp_path, monkeypatch)
    _make_packet(tmp_path, packet=dict(FILL_PACKET, applied=True, compile="failed"))
    _write_answers(tmp_path)

    cli.main(["pipeline.py", "fill-context", "greenhouse-citadel-123"])

    warnings = json.loads(capsys.readouterr().out)["warnings"]
    assert len(warnings) == 2
    assert any("applied" in w for w in warnings)
    assert any("compile" in w for w in warnings)


def test_fill_context_without_a_pdf(tmp_path, monkeypatch, capsys):
    _fill_project(tmp_path, monkeypatch)
    _make_packet(tmp_path, pdf=False)
    _write_answers(tmp_path)

    cli.main(["pipeline.py", "fill-context", "greenhouse-citadel-123"])

    context = json.loads(capsys.readouterr().out)
    assert context["cv_pdf_path"] is None
    assert any("PDF" in w for w in context["warnings"])


def test_fill_context_refuses_a_cv_pdf_path_outside_the_packet(tmp_path, monkeypatch, capsys):
    _fill_project(tmp_path, monkeypatch)
    _make_packet(tmp_path, packet=dict(FILL_PACKET, cv_pdf="../../secret.pdf"), pdf=False)
    (tmp_path / "secret.pdf").write_bytes(b"%PDF-1.4")
    _write_answers(tmp_path)

    cli.main(["pipeline.py", "fill-context", "greenhouse-citadel-123"])

    assert json.loads(capsys.readouterr().out)["cv_pdf_path"] is None


def test_fill_context_without_a_jd(tmp_path, monkeypatch, capsys):
    _fill_project(tmp_path, monkeypatch)
    _make_packet(tmp_path, jd=None)
    _write_answers(tmp_path)

    cli.main(["pipeline.py", "fill-context", "greenhouse-citadel-123"])

    context = json.loads(capsys.readouterr().out)
    assert context["jd_text"] is None
    assert any("jd.txt" in w for w in context["warnings"])


def test_fill_context_unknown_posting_exits_4(tmp_path, monkeypatch, capsys):
    _fill_project(tmp_path, monkeypatch)
    _make_packet(tmp_path)

    assert cli.main(["pipeline.py", "fill-context", "greenhouse-nobody-1"]) == 4
    assert capsys.readouterr().out == ""


def test_fill_context_invalid_id_exits_2(tmp_path, monkeypatch, capsys):
    _fill_project(tmp_path, monkeypatch)

    assert cli.main(["pipeline.py", "fill-context", "bad id!"]) == 2
    assert capsys.readouterr().out == ""


def test_fill_context_invalid_answers_file_exits_2_without_echoing_values(tmp_path, monkeypatch, capsys):
    _fill_project(tmp_path, monkeypatch)
    _make_packet(tmp_path)
    _write_answers(tmp_path, "contact:\n  password: hunter2-XYZ\n")

    assert cli.main(["pipeline.py", "fill-context", "greenhouse-citadel-123"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "hunter2-XYZ" not in captured.err


def test_fill_context_two_packets_claiming_one_posting_exits_2(tmp_path, monkeypatch, capsys):
    _fill_project(tmp_path, monkeypatch)
    _make_packet(tmp_path, slug="citadel-a")
    _make_packet(tmp_path, slug="citadel-b")

    assert cli.main(["pipeline.py", "fill-context", "greenhouse-citadel-123"]) == 2
    assert capsys.readouterr().out == ""
