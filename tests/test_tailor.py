from __future__ import annotations

from job_fetcher import tailor


def _queue(tmp_path, text):
    path = tmp_path / "queue.local.txt"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_parse_queue_returns_empty_when_the_file_is_absent(tmp_path):
    assert tailor.parse_queue(str(tmp_path / "absent.txt")) == ([], [])


def test_parse_queue_strips_comments_blanks_and_whitespace(tmp_path):
    path = _queue(tmp_path, """
# postings to tailor for
  https://job-boards.greenhouse.io/stripe/jobs/1

https://jobs.lever.co/palantir/abc   # trailing note
""")

    urls, skipped = tailor.parse_queue(path)

    assert urls == [
        "https://job-boards.greenhouse.io/stripe/jobs/1",
        "https://jobs.lever.co/palantir/abc",
    ]
    assert skipped == []


def test_parse_queue_deduplicates_preserving_order(tmp_path):
    path = _queue(tmp_path, """
https://example.com/a
https://example.com/b
https://example.com/a
""")

    urls, _ = tailor.parse_queue(path)

    assert urls == ["https://example.com/a", "https://example.com/b"]


def test_parse_queue_reports_lines_that_are_not_urls(tmp_path):
    path = _queue(tmp_path, "https://example.com/a\nremember the NVIDIA one\n")

    urls, skipped = tailor.parse_queue(path)

    assert urls == ["https://example.com/a"]
    assert skipped == ["remember the NVIDIA one"]


def test_packet_slug_combines_company_and_role():
    slug = tailor.packet_slug("Nvidia", "Infiniband Network Software Engineer", "x-1", set())

    assert slug == "nvidia-infiniband-network-software-engineer"


def test_packet_slug_truncates_a_very_long_role():
    slug = tailor.packet_slug("Acme", "Senior " * 40 + "Engineer", "x-1", set())

    assert len(slug) <= tailor.MAX_SLUG_LENGTH
    assert slug.startswith("acme-senior")
    assert not slug.endswith("-")


def test_packet_slug_folds_non_ascii_and_punctuation():
    slug = tailor.packet_slug("Bosch Group", "Pflichtpraktikum — People & Matter", "x-1", set())

    assert slug == "bosch-group-pflichtpraktikum-people-matter"


def test_packet_slug_disambiguates_a_collision_with_the_posting_id():
    existing = {"acme-engineer"}

    slug = tailor.packet_slug("Acme", "Engineer", "greenhouse-4567890", existing)

    assert slug != "acme-engineer"
    assert "4567890" in slug
