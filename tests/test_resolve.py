from __future__ import annotations

from pathlib import Path

import pytest

from job_fetcher import resolve
from job_fetcher.fetching import AdapterParseError, FetchError, NeedsBrowser, UnresolvableError, UsageError

FIXTURES = Path(__file__).parent / "fixtures"

PAGE_URL = "https://careers.tinyco.example/jobs/backend-engineer"


def test_url_id_is_stable_and_prefixed():
    first = resolve.url_id(PAGE_URL)
    second = resolve.url_id(PAGE_URL)

    assert first == second
    assert first.startswith("url-")
    assert len(first) == len("url-") + 12


def test_url_id_differs_between_urls():
    assert resolve.url_id(PAGE_URL) != resolve.url_id(PAGE_URL + "-2")


def test_extract_jsonld_posting_reads_a_plain_jobposting():
    html_text = (FIXTURES / "jsonld_page.html").read_text()

    posting = resolve.extract_jsonld_posting(html_text, PAGE_URL)

    assert posting == {
        "id": resolve.url_id(PAGE_URL),
        "company": "Tiny Co",
        "title": "Backend Engineer",
        "url": PAGE_URL,
        "location": "Berlin, BE",
        "posted_date": "2026-08-30",
        "description": "Build APIs in Python.",
        "resolution": "jsonld",
    }


def test_extract_jsonld_posting_finds_a_posting_inside_an_at_graph():
    html_text = (FIXTURES / "jsonld_graph_page.html").read_text()

    posting = resolve.extract_jsonld_posting(html_text, PAGE_URL)

    assert posting is not None
    assert posting["title"] == "Backend Engineer"
    assert posting["resolution"] == "jsonld"


def test_extract_jsonld_posting_ignores_a_non_jobposting_type():
    html_text = (FIXTURES / "jsonld_wrong_type_page.html").read_text()

    assert resolve.extract_jsonld_posting(html_text, PAGE_URL) is None


def test_extract_jsonld_posting_survives_malformed_json():
    html_text = (FIXTURES / "jsonld_malformed_page.html").read_text()

    assert resolve.extract_jsonld_posting(html_text, PAGE_URL) is None


def test_extract_jsonld_posting_returns_none_when_there_is_no_markup():
    assert resolve.extract_jsonld_posting("<html><body>hi</body></html>", PAGE_URL) is None


def test_extract_jsonld_posting_requires_both_title_and_company():
    html_text = (
        '<script type="application/ld+json">'
        '{"@type":"JobPosting","title":"No Company"}'
        "</script>"
    )

    assert resolve.extract_jsonld_posting(html_text, PAGE_URL) is None


def test_extract_hints_reads_og_title_and_document_title():
    html_text = (FIXTURES / "plain_page.html").read_text()

    hints = resolve.extract_hints(html_text, PAGE_URL)

    assert hints["og_title"] == "Backend Engineer"
    assert hints["document_title"] == "Backend Engineer at Tiny Co"
    assert hints["domain"] == "careers.tinyco.example"


def test_extract_hints_tolerates_missing_metadata():
    hints = resolve.extract_hints("<html><body>hi</body></html>", PAGE_URL)

    assert hints["og_title"] is None
    assert hints["document_title"] is None
    assert hints["domain"] == "careers.tinyco.example"


def test_resolve_generic_leaves_fields_null_and_flags_extraction():
    html_text = (FIXTURES / "plain_page.html").read_text()

    posting = resolve.resolve_generic(html_text, PAGE_URL)

    assert posting["id"] == resolve.url_id(PAGE_URL)
    assert posting["url"] == PAGE_URL
    assert posting["company"] is None
    assert posting["title"] is None
    assert posting["location"] is None
    assert posting["posted_date"] == ""
    assert posting["resolution"] == "html"
    assert posting["needs_extraction"] is True
    assert "backend engineer" in posting["raw_text"].lower()
    assert posting["hints"]["og_title"] == "Backend Engineer"


def test_resolve_generic_caps_raw_text():
    html_text = "<p>" + ("word " * 20000) + "</p>"

    posting = resolve.resolve_generic(html_text, PAGE_URL)

    assert len(posting["raw_text"]) == resolve.RAW_TEXT_MAX_LENGTH


def test_resolve_generic_raises_needs_browser_for_a_js_shell():
    html_text = (FIXTURES / "js_shell_page.html").read_text()

    with pytest.raises(NeedsBrowser) as excinfo:
        resolve.resolve_generic(html_text, PAGE_URL)

    assert excinfo.value.exit_code == 3


class _StubAdapter:
    name = "stub"

    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    def matches(self, url):
        return True

    def fetch(self, url):
        if self._error is not None:
            raise self._error
        return self._result


def test_resolve_rejects_a_non_http_url():
    with pytest.raises(UsageError) as excinfo:
        resolve.resolve("ftp://example.com/job")

    assert excinfo.value.exit_code == 2


def test_resolve_returns_the_adapter_result_when_one_matches(monkeypatch):
    expected = {"id": "x-1", "title": "T", "resolution": "api"}
    monkeypatch.setattr(resolve, "find_adapter", lambda url: _StubAdapter(expected))

    assert resolve.resolve(PAGE_URL) == expected


def test_resolve_does_not_fetch_the_page_when_an_adapter_succeeds(monkeypatch):
    monkeypatch.setattr(
        resolve, "find_adapter", lambda url: _StubAdapter({"id": "x", "resolution": "api"})
    )

    def fail(*args, **kwargs):
        raise AssertionError("http_get should not be called")

    monkeypatch.setattr(resolve, "http_get", fail)

    resolve.resolve(PAGE_URL)


def test_resolve_propagates_a_fetch_error_from_an_adapter(monkeypatch):
    monkeypatch.setattr(
        resolve,
        "find_adapter",
        lambda url: _StubAdapter(error=FetchError("posting no longer available")),
    )

    with pytest.raises(FetchError) as excinfo:
        resolve.resolve(PAGE_URL)

    assert excinfo.value.exit_code == 4


def test_resolve_degrades_to_jsonld_when_an_adapter_cannot_parse(monkeypatch, capsys):
    monkeypatch.setattr(
        resolve,
        "find_adapter",
        lambda url: _StubAdapter(error=AdapterParseError("shape changed")),
    )
    monkeypatch.setattr(
        resolve,
        "http_get",
        lambda url, accept="application/json": (FIXTURES / "jsonld_page.html").read_text(),
    )

    posting = resolve.resolve(PAGE_URL)

    assert posting["resolution"] == "jsonld"
    assert "shape changed" in capsys.readouterr().err


def test_resolve_falls_through_to_generic_when_there_is_no_adapter(monkeypatch):
    monkeypatch.setattr(resolve, "find_adapter", lambda url: None)
    monkeypatch.setattr(
        resolve,
        "http_get",
        lambda url, accept="application/json": (FIXTURES / "plain_page.html").read_text(),
    )

    posting = resolve.resolve(PAGE_URL)

    assert posting["resolution"] == "html"


def test_resolve_reports_needs_browser_when_no_adapter_matched(monkeypatch):
    monkeypatch.setattr(resolve, "find_adapter", lambda url: None)
    monkeypatch.setattr(
        resolve,
        "http_get",
        lambda url, accept="application/json": (FIXTURES / "js_shell_page.html").read_text(),
    )

    with pytest.raises(NeedsBrowser) as excinfo:
        resolve.resolve(PAGE_URL)

    assert excinfo.value.exit_code == 3


def test_resolve_reports_unresolvable_when_the_adapter_failed_too(monkeypatch):
    monkeypatch.setattr(
        resolve,
        "find_adapter",
        lambda url: _StubAdapter(error=AdapterParseError("shape changed")),
    )
    monkeypatch.setattr(
        resolve,
        "http_get",
        lambda url, accept="application/json": (FIXTURES / "js_shell_page.html").read_text(),
    )

    with pytest.raises(UnresolvableError) as excinfo:
        resolve.resolve(PAGE_URL)

    assert excinfo.value.exit_code == 5
