from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

from job_fetcher import resolve as resolve_module
from job_fetcher import store
from job_fetcher.fetching import AdapterParseError, FetchError, NeedsBrowser, UnresolvableError

REPO_ROOT = Path(__file__).parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"


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


PLAIN_PAGE_URL = "https://careers.tinyco.example/jobs/backend-engineer"


def test_resolve_generic_output_flows_cleanly_through_store_mode(
    monkeypatch, tmp_path, capsys
):
    """The one end-to-end test of the resolve -> store seam. resolve_generic is
    the only producer of needs_extraction/raw_text/hints and store mode the
    only consumer; they were written in separate tasks, so this is the
    likeliest place for a contract mismatch (the carried-forward raw_text
    assertion elsewhere used a hand-built dict that never actually flowed
    through resolve_generic)."""
    path = tmp_path / "postings.local.yaml"
    monkeypatch.setattr(cli, "POSTINGS_PATH", str(path))

    html_text = (FIXTURES / "plain_page.html").read_text()
    resolved = resolve_module.resolve_generic(html_text, PLAIN_PAGE_URL)
    assert resolved["needs_extraction"] is True

    # This is the judgment call the skill makes in step 4: fill in the nulls
    # from raw_text/hints, then pass the whole dict (transport fields and
    # all) to store mode as-is.
    completed = dict(resolved)
    completed["company"] = "Tiny Co"
    completed["title"] = "Backend Engineer"
    completed["location"] = "Berlin"

    exit_code = cli.store_mode(io.StringIO(json.dumps(completed)))

    assert exit_code == 0
    stored = store.load_postings(str(path))
    assert len(stored) == 1
    entry = stored[0]

    for transport_field in ("resolution", "needs_extraction", "raw_text", "hints"):
        assert transport_field not in entry

    assert entry["company"] == "Tiny Co"
    assert entry["title"] == "Backend Engineer"
    assert entry["location"] == "Berlin"
    assert entry["url"] == PLAIN_PAGE_URL
    assert entry["description"]


class _CLIStubAdapter:
    name = "stub"

    def matches(self, url):
        return True

    def fetch(self, url):
        raise AdapterParseError("stub adapter shape changed")


def test_cli_exits_zero_when_adapter_fails_but_generic_succeeds(monkeypatch, capsys):
    monkeypatch.setattr(resolve_module, "find_adapter", lambda url: _CLIStubAdapter())
    monkeypatch.setattr(
        resolve_module,
        "http_get",
        lambda url, accept="application/json": (FIXTURES / "plain_page.html").read_text(),
    )

    exit_code = cli.main(["resolve-posting.py", PLAIN_PAGE_URL])

    captured = capsys.readouterr()
    assert exit_code == 0
    posting = json.loads(captured.out)
    assert posting["resolution"] == "html"
    assert "stub adapter failed" in captured.err
    assert "shape changed" in captured.err
