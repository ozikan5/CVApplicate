from __future__ import annotations

from pathlib import Path

import pytest

from job_fetcher import resolve
from job_fetcher.fetching import NeedsBrowser

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
