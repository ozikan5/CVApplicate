from __future__ import annotations

import pytest

from job_fetcher import htmltext, profile


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


def test_authorization_disqualifies_despite_eeo_clause_with_place_name():
    """Regression test for the false-negative finding: the unanchored
    abbreviation alternation matched 'co.' as a substring of 'Morocco.',
    merging the EEO sentence with the following citizenship-requirement
    sentence. Because the merged sentence contained 'equal opportunity', the
    non-discrimination discard swallowed the whole thing and a posting that
    plainly requires US citizenship was wrongly accepted as OK."""
    text = (
        "We are an equal opportunity employer with an office in Morocco. "
        "U.S. citizenship is required for this cleared role."
    )

    verdict, reason = profile.authorization_verdict(text, "cpt-opt")

    assert verdict == profile.DISQUALIFIED
    assert reason


def test_split_sentences_does_not_merge_on_word_ending_in_abbreviation_letters():
    """'Morocco.' ends in the letters of the 'Co.' abbreviation, but it is not
    an abbreviation token and must not suppress the sentence boundary after
    it."""
    text = "He previously worked in Morocco. Citizenship is required."

    sentences = profile._split_sentences(text)

    assert sentences == [
        "He previously worked in Morocco.",
        "Citizenship is required.",
    ]


def test_split_sentences_still_protects_real_abbreviations_after_anchoring():
    """The word-boundary anchor must not undo the original abbreviation
    protection: genuine 'e.g.' and 'U.S.A.' tokens still keep their periods
    and do not split the sentence, while the real sentence boundary after
    'team.' still splits."""
    text = "Send to e.g. the U.S.A. team. Citizenship is required."

    sentences = profile._split_sentences(text)

    assert sentences == [
        "Send to e.g. the U.S.A. team.",
        "Citizenship is required.",
    ]


# --- The seam: description_from_html -> authorization_verdict ---------------
#
# Nothing previously fed real htmltext output into authorization_verdict,
# which is the only place the gate meets its actual input. htmltext.strip_html
# collapses every block tag boundary (<li>, <p>, <ul>, ...) to a single space
# with NO punctuation, so a bulleted requirements list merges into whatever
# prose follows (or precedes) it into one pseudo-sentence. These fixtures
# deliberately omit terminal punctuation on individual bullets/paragraphs (as
# real ATS-authored HTML often does) so they exercise that exact merge.

_CITIZEN_LI = (
    "<li>Applicants must be a U.S. citizen due to federal contract "
    "requirements for this role</li>"
)
_EEO_P = (
    "<p>Acme Corp is an equal opportunity employer committed to a diverse "
    "workplace</p>"
)
_SPONSOR_LI = (
    "<li>we are not able to sponsor employment-based work visas for "
    "candidates applying to this particular open engineering role</li>"
)
_CPT_LI = (
    "<li>CPT/OPT students should apply through our university partner "
    "program</li>"
)


def test_authorization_disqualifies_citizen_bullet_with_eeo_paragraph_after():
    html = f"<ul>{_CITIZEN_LI}</ul>{_EEO_P}"
    text = htmltext.description_from_html(html)

    verdict, reason = profile.authorization_verdict(text, "cpt-opt")

    assert verdict == profile.DISQUALIFIED
    assert reason


def test_authorization_disqualifies_citizen_bullet_with_eeo_paragraph_before():
    """Position must not matter: the EEO paragraph sits before the
    disqualifying bullet here, the opposite of the previous test."""
    html = f"{_EEO_P}<ul>{_CITIZEN_LI}</ul>"
    text = htmltext.description_from_html(html)

    verdict, reason = profile.authorization_verdict(text, "cpt-opt")

    assert verdict == profile.DISQUALIFIED
    assert reason


def test_authorization_allows_permissive_sponsorship_bullets_eeo_after():
    html = f"<ul>{_SPONSOR_LI}{_CPT_LI}</ul>{_EEO_P}"
    text = htmltext.description_from_html(html)

    verdict, _ = profile.authorization_verdict(text, "cpt-opt")

    assert verdict == profile.OK


def test_authorization_narrow_sponsor_window_stops_cross_bullet_false_match():
    """Regression test for the false-rejection finding: two separate <li>
    bullets merge into one pseudo-sentence with no punctuation between them
    (as htmltext.description_from_html collapses block boundaries to a bare
    space), and a "cannot sponsor" phrase in one bullet used to fall inside
    the CPT/OPT sponsorship pattern's old 90-character window and falsely
    match an unrelated CPT/OPT mention in a separate bullet.

    This was originally written (and named) as an EEO-position-independence
    test expecting OK, with the EEO paragraph merged into the very same
    pseudo-sentence as the sponsor/CPT bullets (no terminal punctuation
    between them, matching how htmltext collapses block boundaries). That
    fixture cannot actually exercise the 90-vs-55 window: whenever a
    non-discrimination marker (e.g. "equal opportunity employer") sits in
    the *same* sentence as the CPT/OPT mention, the pre-fix code's
    `if _NON_DISCRIMINATION.search(sentence): continue` discards that whole
    sentence unconditionally, before the CPT/OPT window is ever consulted --
    so the pre-fix code returns OK regardless of the gap (verified: even an
    18-character gap, well inside the old 90-char window, still returns OK
    against the pre-fix code, because the sentence is never scanned at all).
    A test built that way passes against both the pre-fix and current code
    for a reason that has nothing to do with the window size, which is
    exactly the placebo a reviewer flagged (measured gap 94 chars in the
    original fixture, wider than even the old 90-char window).

    To make the window itself the thing under test, the EEO paragraph below
    ends with a period, so it forms its own sentence and the sponsor/CPT
    pseudo-sentence has no non-discrimination marker in it at all. Given
    that isolation:
      - pre-fix (90-char window): the sponsor/CPT gap falls inside the old
        window, so the disqualifying pattern falsely matches -> DISQUALIFIED.
      - current (55-char window): the same gap falls outside the new,
        narrower window, so the pattern does not match. With no marker to
        suppress the AMBIGUOUS fallback, the bare "CPT" mention correctly
        escalates rather than silently passing -> AMBIGUOUS (see _UNCLEAR's
        "escalate rather than guess" comment in profile.py). AMBIGUOUS, not
        OK, is the correct fixed-code outcome for an unrelated CPT mention
        with no accompanying EEO/non-discrimination context to suppress it.
    """
    eeo_p = (
        "<p>Acme Corp is an equal opportunity employer committed to a "
        "diverse workplace.</p>"
    )
    sponsor_li = (
        "<li>we are not able to sponsor employment-based work visas for "
        "candidates in this open role</li>"
    )
    cpt_li = (
        "<li>CPT/OPT students should apply through our university partner "
        "program</li>"
    )
    html = f"{eeo_p}<ul>{sponsor_li}{cpt_li}</ul>"
    text = htmltext.description_from_html(html)

    # Gap between "sponsor" and "CPT": inside the pre-fix 90-char window,
    # outside the current 55-char one. Assert it so a future reword of the
    # fixture can't silently drift out of the range this test depends on.
    gap = text.index("CPT") - (text.lower().index("sponsor") + len("sponsor"))
    assert 55 < gap <= 90, gap

    verdict, _ = profile.authorization_verdict(text, "cpt-opt")

    assert verdict == profile.AMBIGUOUS


def test_authorization_disqualifies_citizenship_required_beside_eeo_clause():
    text = (
        "U.S. citizenship is required, and we are an equal opportunity "
        "employer."
    )

    verdict, reason = profile.authorization_verdict(text, "cpt-opt")

    assert verdict == profile.DISQUALIFIED
    assert reason


def test_authorization_does_not_pass_a_clearance_requirement_silently():
    text = "Requires a TS/SCI clearance with polygraph."

    verdict, reason = profile.authorization_verdict(text, "cpt-opt")

    # AMBIGUOUS would also be an acceptable outcome per the spec; this
    # implementation broadens the disqualifying clearance pattern to catch
    # "TS/SCI clearance" directly.
    assert verdict == profile.DISQUALIFIED
    assert reason


def test_authorization_disqualifies_do_not_sponsor_cpt_opt():
    text = "We do not sponsor CPT/OPT."

    verdict, reason = profile.authorization_verdict(text, "cpt-opt")

    assert verdict == profile.DISQUALIFIED
    assert "CPT" in reason


def test_authorization_disqualifies_leading_only_us_citizens():
    text = "Only U.S. citizens will be considered."

    verdict, reason = profile.authorization_verdict(text, "cpt-opt")

    assert verdict == profile.DISQUALIFIED
    assert reason


def test_authorization_disqualifies_not_able_to_hire_on_cpt_or_opt():
    text = "We are not able to hire students on CPT or OPT."

    verdict, reason = profile.authorization_verdict(text, "cpt-opt")

    assert verdict == profile.DISQUALIFIED
    assert "CPT" in reason


def test_authorization_disqualifies_plural_citizens_without_article():
    text = "Applicants must be US citizens and able to start immediately."

    verdict, reason = profile.authorization_verdict(text, "cpt-opt")

    assert verdict == profile.DISQUALIFIED
    assert reason


def test_authorization_disqualifies_requires_citizenship_word_order():
    text = "This position requires US citizenship."

    verdict, reason = profile.authorization_verdict(text, "cpt-opt")

    assert verdict == profile.DISQUALIFIED
    assert reason


def test_authorization_escalates_an_obtain_clearance_phrasing_not_in_pattern():
    text = "Must be able to obtain and maintain a security clearance."

    verdict, reason = profile.authorization_verdict(text, "cpt-opt")

    assert verdict != profile.OK
    assert reason
