from __future__ import annotations

from job_fetcher import htmltext


def test_strip_html_removes_tags_and_collapses_whitespace():
    html = "<p>Hello</p>\n\n<ul><li>One</li><li>Two</li></ul>"

    result = htmltext.strip_html(html)

    assert result == "Hello One Two"


def test_description_from_html_returns_none_for_empty_input():
    assert htmltext.description_from_html(None) is None
    assert htmltext.description_from_html("") is None
    assert htmltext.description_from_html("<p> </p>") is None


def test_description_from_html_truncates_to_max_length():
    html = "<p>" + ("word " * 4000) + "</p>"

    result = htmltext.description_from_html(html)

    assert len(result) == htmltext.MAX_DESCRIPTION_LENGTH


def test_description_from_plain_collapses_whitespace():
    assert htmltext.description_from_plain("a\n\n  b\tc") == "a b c"


def test_description_from_plain_returns_none_for_blank():
    assert htmltext.description_from_plain("   \n ") is None
