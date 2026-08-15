from __future__ import annotations

from job_fetcher import store


def test_load_postings_returns_empty_list_when_file_missing(tmp_path):
    result = store.load_postings(str(tmp_path / "missing.yaml"))
    assert result == []


def test_save_and_load_roundtrip(tmp_path):
    path = str(tmp_path / "postings.yaml")
    postings = [
        {
            "id": "acme-1",
            "company": "Acme",
            "title": "Engineer",
            "url": "https://example.com/1",
            "location": "Remote",
            "posted_date": "2026-08-10",
            "first_seen": "2026-08-10",
            "notified": False,
        }
    ]

    store.save_postings(path, postings)
    loaded = store.load_postings(path)

    assert loaded == postings


def test_merge_new_postings_marks_new_entries():
    existing = []
    fetched = [
        {
            "id": "acme-1",
            "company": "Acme",
            "title": "Engineer",
            "url": "https://example.com/1",
            "location": "Remote",
            "posted_date": "2026-08-10",
        }
    ]

    merged, new_postings = store.merge_new_postings(existing, fetched, "2026-08-14")

    assert len(merged) == 1
    assert merged[0]["first_seen"] == "2026-08-14"
    assert merged[0]["notified"] is False
    assert new_postings == merged


def test_merge_new_postings_preserves_existing_entries_untouched():
    existing = [
        {
            "id": "acme-1",
            "company": "Acme",
            "title": "Engineer",
            "url": "https://example.com/1",
            "location": "Remote",
            "posted_date": "2026-08-10",
            "first_seen": "2026-08-01",
            "notified": True,
        }
    ]
    fetched = [
        {
            "id": "acme-1",
            "company": "Acme",
            "title": "Engineer",
            "url": "https://example.com/1",
            "location": "Remote",
            "posted_date": "2026-08-10",
        }
    ]

    merged, new_postings = store.merge_new_postings(existing, fetched, "2026-08-14")

    assert merged == existing
    assert new_postings == []


def test_merge_new_postings_keeps_postings_that_disappeared_from_feed():
    existing = [
        {
            "id": "acme-1",
            "company": "Acme",
            "title": "Engineer",
            "url": "https://example.com/1",
            "location": "Remote",
            "posted_date": "2026-08-10",
            "first_seen": "2026-08-01",
            "notified": True,
        }
    ]
    fetched = []  # posting closed, no longer in the ATS feed

    merged, new_postings = store.merge_new_postings(existing, fetched, "2026-08-14")

    assert merged == existing
    assert new_postings == []


def test_mark_notified_sets_flag_only_for_given_ids():
    postings = [
        {"id": "acme-1", "notified": False},
        {"id": "acme-2", "notified": False},
    ]

    store.mark_notified(postings, {"acme-1"})

    assert postings[0]["notified"] is True
    assert postings[1]["notified"] is False
