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
        "location_ok",
        "authorization",
        "authorization_reason",
        "seeking",
        "max_years_experience_required",
    }
    assert result["location_ok"] is True
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
