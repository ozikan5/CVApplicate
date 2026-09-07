from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

from job_fetcher import store
from job_fetcher.fetching import FetchError, NeedsBrowser, UnresolvableError

REPO_ROOT = Path(__file__).parent.parent


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "resolve_posting", REPO_ROOT / "resolve-posting.py"
    )
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
    "posted_date": "2026-09-04",
    "description": "Investigate abuse.",
    "resolution": "api",
}


def test_resolve_mode_prints_json_to_stdout(monkeypatch, capsys):
    monkeypatch.setattr(cli, "resolve", lambda url: dict(POSTING))

    exit_code = cli.main(["resolve-posting.py", POSTING["url"]])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == POSTING


def test_resolve_mode_keeps_stdout_pure_json(monkeypatch, capsys):
    """A human summary on stdout would break a machine consumer."""
    monkeypatch.setattr(cli, "resolve", lambda url: dict(POSTING))

    cli.main(["resolve-posting.py", POSTING["url"]])

    captured = capsys.readouterr()
    json.loads(captured.out)
    assert "Stripe" in captured.err


@pytest.mark.parametrize(
    "error,expected_code",
    [
        (NeedsBrowser("js shell"), 3),
        (FetchError("posting no longer available"), 4),
        (UnresolvableError("both paths failed"), 5),
    ],
)
def test_resolve_mode_maps_errors_to_exit_codes(monkeypatch, capsys, error, expected_code):
    def raise_error(url):
        raise error

    monkeypatch.setattr(cli, "resolve", raise_error)

    exit_code = cli.main(["resolve-posting.py", POSTING["url"]])

    assert exit_code == expected_code
    assert capsys.readouterr().out == ""


def test_needs_browser_message_names_the_escape_hatch(monkeypatch, capsys):
    def raise_error(url):
        raise NeedsBrowser("js shell")

    monkeypatch.setattr(cli, "resolve", raise_error)

    cli.main(["resolve-posting.py", POSTING["url"]])

    assert "cv-review" in capsys.readouterr().err


def test_usage_error_without_arguments(capsys):
    exit_code = cli.main(["resolve-posting.py"])

    assert exit_code == 2
    assert "usage:" in capsys.readouterr().err


def test_store_mode_writes_the_posting_as_notified(monkeypatch, tmp_path, capsys):
    path = tmp_path / "postings.local.yaml"
    monkeypatch.setattr(cli, "POSTINGS_PATH", str(path))

    exit_code = cli.store_mode(io.StringIO(json.dumps(POSTING)))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {
        "stored": True,
        "already_tracked": False,
        "id": "stripe-8172508",
        "scored": False,
    }

    stored = store.load_postings(str(path))
    assert len(stored) == 1
    assert stored[0]["notified"] is True
    assert stored[0]["scored"] is False
    assert "resolution" not in stored[0]
    assert "raw_text" not in stored[0]


def test_store_mode_reports_an_already_tracked_posting(monkeypatch, tmp_path, capsys):
    path = tmp_path / "postings.local.yaml"
    monkeypatch.setattr(cli, "POSTINGS_PATH", str(path))
    existing = dict(POSTING)
    existing.pop("resolution")
    existing.update({"first_seen": "2026-09-01", "notified": True, "scored": True})
    store.save_postings(str(path), [existing])

    exit_code = cli.store_mode(io.StringIO(json.dumps(POSTING)))

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "stored": False,
        "already_tracked": True,
        "id": "stripe-8172508",
        "scored": True,
    }
    assert len(store.load_postings(str(path))) == 1


@pytest.mark.parametrize("missing", ["company", "title", "url", "description"])
def test_store_mode_rejects_a_posting_with_a_null_identity_field(
    monkeypatch, tmp_path, capsys, missing
):
    path = tmp_path / "postings.local.yaml"
    monkeypatch.setattr(cli, "POSTINGS_PATH", str(path))
    incomplete = dict(POSTING)
    incomplete[missing] = None

    exit_code = cli.store_mode(io.StringIO(json.dumps(incomplete)))

    assert exit_code == 2
    assert missing in capsys.readouterr().err
    assert store.load_postings(str(path)) == []


def test_store_mode_rejects_invalid_json(monkeypatch, tmp_path, capsys):
    path = tmp_path / "postings.local.yaml"
    monkeypatch.setattr(cli, "POSTINGS_PATH", str(path))

    exit_code = cli.store_mode(io.StringIO("not json"))

    assert exit_code == 2
    assert store.load_postings(str(path)) == []


def test_store_mode_is_reachable_through_main(monkeypatch, tmp_path, capsys):
    path = tmp_path / "postings.local.yaml"
    monkeypatch.setattr(cli, "POSTINGS_PATH", str(path))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(POSTING)))

    exit_code = cli.main(["resolve-posting.py", "--store", "-"])

    assert exit_code == 0
    assert len(store.load_postings(str(path))) == 1
