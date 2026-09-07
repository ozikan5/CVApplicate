from __future__ import annotations

from pathlib import Path

from job_fetcher import resolve

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
