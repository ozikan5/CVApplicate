from __future__ import annotations

from job_fetcher import filters


def _posting(title="Software Engineering Intern", location="United States"):
    return {"title": title, "location": location}


def test_matches_filters_true_when_all_criteria_match():
    f = {
        "location_keywords": ["united states"],
        "title_keywords": ["software engineer"],
        "require_internship": True,
    }
    assert filters.matches_filters(_posting(), f) is True


def test_matches_filters_false_when_location_does_not_match():
    f = {
        "location_keywords": ["canada"],
        "title_keywords": ["software engineer"],
        "require_internship": True,
    }
    assert filters.matches_filters(_posting(), f) is False


def test_matches_filters_false_when_title_lacks_intern_and_required():
    f = {
        "location_keywords": ["united states"],
        "title_keywords": ["software engineer"],
        "require_internship": True,
    }
    posting = _posting(title="Software Engineer")  # no "intern"
    assert filters.matches_filters(posting, f) is False


def test_matches_filters_true_when_internship_not_required():
    f = {
        "location_keywords": ["united states"],
        "title_keywords": ["software engineer"],
        "require_internship": False,
    }
    posting = _posting(title="Software Engineer")  # no "intern"
    assert filters.matches_filters(posting, f) is True


def test_matches_filters_false_when_title_does_not_match_keywords():
    f = {
        "location_keywords": ["united states"],
        "title_keywords": ["cloud engineer"],
        "require_internship": True,
    }
    posting = _posting(title="Software Engineering Intern")
    assert filters.matches_filters(posting, f) is False


def test_matches_filters_skips_title_keyword_check_when_list_empty():
    f = {
        "location_keywords": ["united states"],
        "title_keywords": [],
        "require_internship": True,
    }
    posting = _posting(title="Marketing Intern")
    assert filters.matches_filters(posting, f) is True


def test_matches_filters_skips_location_check_when_list_empty():
    f = {
        "location_keywords": [],
        "title_keywords": ["software engineer"],
        "require_internship": True,
    }
    posting = _posting(location="Bengaluru, India")
    assert filters.matches_filters(posting, f) is True


def test_matches_filters_is_case_insensitive():
    f = {
        "location_keywords": ["UNITED STATES"],
        "title_keywords": ["SOFTWARE ENGINEER"],
        "require_internship": True,
    }
    posting = _posting(title="software engineering INTERN", location="united states")
    assert filters.matches_filters(posting, f) is True


def test_load_filters_returns_none_when_file_missing(tmp_path):
    result = filters.load_filters(str(tmp_path / "missing.yaml"))
    assert result is None


def test_load_filters_returns_parsed_dict(tmp_path):
    path = tmp_path / "filters.yaml"
    path.write_text("location_keywords: [\"united states\"]\nrequire_internship: true\n")

    result = filters.load_filters(str(path))

    assert result == {"location_keywords": ["united states"], "require_internship": True}
