from __future__ import annotations

import importlib.util
import json
from pathlib import Path

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

import imaplib
import re as _re

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
