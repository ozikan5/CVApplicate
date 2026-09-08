from __future__ import annotations

import pytest

from job_fetcher import profile


def _write(tmp_path, text):
    path = tmp_path / "profile.local.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_load_profile_reads_a_full_profile(tmp_path):
    path = _write(tmp_path, """
seeking: internship
graduation: 2028-06
locations: ["United States", "Remote (US)"]
max_years_experience_required: 1
work_authorization: cpt-opt
""")

    result = profile.load_profile(path)

    assert result["seeking"] == "internship"
    assert result["locations"] == ["United States", "Remote (US)"]
    assert result["max_years_experience_required"] == 1
    assert result["work_authorization"] == "cpt-opt"


def test_load_profile_defaults_optional_keys_to_none(tmp_path):
    path = _write(tmp_path, "seeking: internship\n")

    result = profile.load_profile(path)

    assert result["work_authorization"] is None
    assert result["max_years_experience_required"] is None
    assert result["locations"] == []


def test_load_profile_missing_file_names_the_example(tmp_path):
    with pytest.raises(profile.ProfileError) as excinfo:
        profile.load_profile(str(tmp_path / "absent.yaml"))

    assert "profile.example.yaml" in str(excinfo.value)


def test_load_profile_rejects_an_unknown_seeking_value(tmp_path):
    path = _write(tmp_path, "seeking: astronaut\n")

    with pytest.raises(profile.ProfileError) as excinfo:
        profile.load_profile(path)

    assert "astronaut" in str(excinfo.value)


def test_load_profile_rejects_an_unknown_authorization_value(tmp_path):
    path = _write(tmp_path, "seeking: internship\nwork_authorization: green-card\n")

    with pytest.raises(profile.ProfileError) as excinfo:
        profile.load_profile(path)

    assert "green-card" in str(excinfo.value)


def test_load_profile_rejects_a_non_mapping(tmp_path):
    path = _write(tmp_path, "- internship\n")

    with pytest.raises(profile.ProfileError):
        profile.load_profile(path)


# Real phrasings from a live job board, 2026-09-08.
CANNOT_SPONSOR_CPT = (
    "Unfortunately, we are not able to sponsor visas, including CPT/OPT or "
    "employ corp-to-corp."
)
CLEARANCE_AND_CITIZENSHIP = (
    "Clearance: Ability to hold or obtain a U.S. security clearance; U.S. "
    "citizenship as required for cleared federal work."
)
EEO_BOILERPLATE = (
    "Scale is an equal opportunity employer. We consider all qualified applicants "
    "regardless of race, color, ancestry, religion, sex, national origin, sexual "
    "orientation, age, citizenship, marital status, disability status, gender "
    "identity or Veteran status."
)
NO_SPONSORSHIP_PLAIN = (
    "Applicants must be authorized to work in the United States without "
    "sponsorship. We are unable to provide visa sponsorship for this role."
)


def test_authorization_rejects_a_no_cpt_opt_employer():
    verdict, reason = profile.authorization_verdict(CANNOT_SPONSOR_CPT, "cpt-opt")

    assert verdict == profile.DISQUALIFIED
    assert "CPT" in reason


def test_authorization_rejects_citizenship_and_clearance_requirements():
    verdict, reason = profile.authorization_verdict(
        CLEARANCE_AND_CITIZENSHIP, "cpt-opt"
    )

    assert verdict == profile.DISQUALIFIED
    assert reason


def test_authorization_ignores_equal_opportunity_boilerplate():
    """The trap. 'regardless of ... citizenship' is a non-discrimination clause,
    the opposite of a requirement, and appears in most US postings. A rule that
    matches on the word alone rejects nearly every eligible posting."""
    verdict, reason = profile.authorization_verdict(EEO_BOILERPLATE, "cpt-opt")

    assert verdict == profile.OK
    assert reason is None


def test_authorization_allows_plain_no_sponsorship_language():
    """CPT is school-authorized, so an F-1 intern already satisfies 'without
    sponsorship'. Rejecting this would discard a large share of open internships."""
    verdict, _ = profile.authorization_verdict(NO_SPONSORSHIP_PLAIN, "cpt-opt")

    assert verdict == profile.OK


def test_authorization_escalates_an_unclear_cpt_mention():
    text = "Sponsorship and CPT/OPT questions are handled case by case."

    verdict, reason = profile.authorization_verdict(text, "cpt-opt")

    assert verdict == profile.AMBIGUOUS
    assert reason


def test_authorization_is_disabled_for_other_modes():
    for mode in ("citizen-or-pr", "unrestricted", None):
        assert profile.authorization_verdict(CANNOT_SPONSOR_CPT, mode) == (
            profile.OK,
            None,
        )


def test_authorization_handles_empty_text():
    assert profile.authorization_verdict("", "cpt-opt") == (profile.OK, None)


def test_location_matches_is_case_and_substring_tolerant():
    allowed = ["United States", "Remote (US)"]

    assert profile.location_matches("San Francisco, CA, United States", allowed)
    assert profile.location_matches("remote (us)", allowed)


def test_location_matches_rejects_an_unlisted_location():
    assert not profile.location_matches("Israel, Raanana", ["United States"])


def test_location_matches_allows_everything_when_no_locations_configured():
    assert profile.location_matches("Israel, Raanana", [])


def test_location_matches_treats_missing_location_text_as_a_match():
    """An unstated location is ambiguous, and the gate errs toward eligible."""
    assert profile.location_matches(None, ["United States"])
    assert profile.location_matches("", ["United States"])


def test_authorization_survives_an_abbreviation_inside_eeo_language():
    """Regression test for the sentence-splitter finding: 'e.g.' used to split
    the EEO sentence in two, separating 'regardless of' from 'citizenship' so
    the non-discrimination exclusion never fired and the posting was wrongly
    flagged as ambiguous."""
    text = (
        "We consider applicants regardless of race, e.g. all backgrounds, "
        "and citizenship, in line with EEO law."
    )

    verdict, reason = profile.authorization_verdict(text, "cpt-opt")

    assert verdict == profile.OK
    assert reason is None


def test_authorization_still_disqualifies_across_an_abbreviation():
    """The literal 'Acme Inc. requires U.S. citizenship for this cleared role.'
    example from the finding does not actually match any _DISQUALIFYING
    pattern even once split correctly (the pattern needs 'citizenship
    required'/'citizenship is required', not 'requires ... citizenship'), so
    it is AMBIGUOUS both before and after the fix and would not exercise the
    regression. This uses an equivalent real-world phrasing instead: the
    'cannot sponsor ... CPT/OPT' pattern's matched span straddles the 'Inc.'
    abbreviation, so the old splitter broke the match into two fragments
    (neither containing the whole phrase) and fell back to AMBIGUOUS, while
    the fixed splitter keeps the sentence whole and disqualifies it."""
    text = (
        "We cannot sponsor, per Acme Inc. guidelines, candidates requiring "
        "CPT or OPT support."
    )

    verdict, reason = profile.authorization_verdict(text, "cpt-opt")

    assert verdict == profile.DISQUALIFIED
    assert "CPT" in reason


def test_authorization_disqualifies_after_a_phd_prefix():
    """A 'Ph.D.' abbreviation earlier in the text must not prevent a later
    citizenship requirement from being recognized."""
    text = "Ph.D. preferred. U.S. citizenship is required for this role."

    verdict, reason = profile.authorization_verdict(text, "cpt-opt")

    assert verdict == profile.DISQUALIFIED
    assert reason


def test_split_sentences_protects_multiple_abbreviations_by_length():
    """Pins the length-descending ordering: 'U.S.A.' must be protected before
    the shorter 'U.S.' pattern can match a prefix of it and leave a stray
    period that still splits the sentence."""
    text = "Founded in the U.S.A. in 1999, the U.S. office is our headquarters."

    sentences = profile._split_sentences(text)

    assert sentences == [text]
