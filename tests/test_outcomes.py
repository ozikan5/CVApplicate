from __future__ import annotations

from job_fetcher import outcomes

APPLICATIONS = [
    {"id": "ctc-swe-2026-08", "company": "Chicago Trading Company (CTC)"},
    {"id": "hrt-swe-2026-08", "company": "Hudson River Trading (HRT)"},
    {"id": "janestreet-a", "company": "Jane Street"},
    {"id": "janestreet-b", "company": "Jane Street"},
    {"id": "microsoft-a", "company": "Microsoft"},
    {"id": "microsoft-b", "company": "Microsoft"},
    {"id": "microsoft-c", "company": "Microsoft"},
    {"id": "citadel-swe-2026-08", "company": "Citadel"},
]


def _message(sender, subject=""):
    address = sender.split("<")[-1].rstrip(">").strip().lower()
    return {"from": sender, "from_address": address, "subject": subject}


def test_company_aliases_splits_a_parenthesized_acronym():
    assert outcomes.company_aliases("Chicago Trading Company (CTC)") == [
        "chicago trading company", "chicagotradingcompany", "ctc",
    ]


def test_company_aliases_for_a_single_word():
    assert outcomes.company_aliases("Microsoft") == ["microsoft"]


def test_sender_domain():
    assert outcomes.sender_domain("no-reply@mail.citadel.com") == "mail.citadel.com"
    assert outcomes.sender_domain("not-an-address") == ""


def test_an_ats_subdomain_is_a_candidate():
    msg = _message("Greenhouse <no-reply@us.greenhouse-mail.io>", "Application update")

    assert outcomes.is_candidate(msg, APPLICATIONS)


def test_an_assessment_platform_is_a_candidate_even_without_a_company_name():
    msg = _message("HackerRank <support@hackerrank.com>", "Your assessment is ready")

    assert outcomes.is_candidate(msg, APPLICATIONS)
    assert outcomes.candidate_applications(msg, APPLICATIONS) == []


def test_a_whole_word_acronym_in_the_subject_matches():
    msg = _message("Recruiting <jobs@example.com>", "Your CTC application")

    assert outcomes.candidate_applications(msg, APPLICATIONS) == ["ctc-swe-2026-08"]


def test_an_acronym_inside_another_word_does_not_match():
    """Short aliases are the risk: 'ctc' must not match 'ctcarrier.com'."""
    msg = _message("CT Carrier <news@ctcarrier.com>", "Shipping update")

    assert not outcomes.is_candidate(msg, APPLICATIONS)


def test_a_company_with_three_applications_yields_all_three():
    msg = _message("Microsoft <no-reply@microsoft.com>", "Thank you for applying")

    assert outcomes.candidate_applications(msg, APPLICATIONS) == [
        "microsoft-a", "microsoft-b", "microsoft-c",
    ]


def test_a_compacted_name_matches_a_domain():
    """Company domains are usually the name without spaces."""
    msg = _message("recruiting@janestreet.com", "Next steps")

    assert outcomes.candidate_applications(msg, APPLICATIONS) == [
        "janestreet-a", "janestreet-b",
    ]


def test_a_display_name_matches():
    msg = _message("Hudson River Trading <jobs@example.org>", "Update")

    assert outcomes.candidate_applications(msg, APPLICATIONS) == ["hrt-swe-2026-08"]


def test_unrelated_mail_is_not_a_candidate():
    msg = _message("A Friend <friend@gmail.com>", "dinner on friday?")

    assert not outcomes.is_candidate(msg, APPLICATIONS)


import pytest


@pytest.mark.parametrize("current,proposed,expected", [
    ("pending", "assessment", False),
    ("assessment", "interview", False),
    ("interview", "offer", False),
    ("interview", "assessment", True),   # an old OA email after an interview
    ("offer", "interview", True),
    ("pending", "rejected", False),      # rejected is reachable from anything
    ("interview", "rejected", False),
    ("rejected", "interview", True),     # a positive after a rejection needs a human
    ("no_response", "interview", False), # they replied late
    ("interview", "interview", False),
])
def test_regresses(current, proposed, expected):
    assert outcomes.regresses(current, proposed) is expected


def _proposal(**overrides):
    proposal = {"proposed_outcome": "rejected", "application_id": "citadel-swe-2026-08",
                "confidence": "high"}
    proposal.update(overrides)
    return proposal


def test_default_answer_is_yes_only_for_a_clear_single_match():
    assert outcomes.default_answer(_proposal(), "pending") is True


def test_default_answer_is_no_for_low_confidence():
    assert outcomes.default_answer(_proposal(confidence="medium"), "pending") is False


def test_default_answer_is_no_when_ambiguous():
    assert outcomes.default_answer(_proposal(application_id=None), "pending") is False


def test_default_answer_is_no_for_a_regression():
    assert outcomes.default_answer(
        _proposal(proposed_outcome="assessment"), "interview"
    ) is False


def test_load_pending_returns_empty_state_for_a_missing_file(tmp_path):
    assert outcomes.load_pending(str(tmp_path / "absent.yaml")) == {
        "seen": [], "proposals": [],
    }


def test_load_pending_and_seen_ids(tmp_path):
    path = tmp_path / "outcomes.pending.yaml"
    path.write_text(
        "seen:\n  - '<a@x.com>'\nproposals:\n  - message_id: '<a@x.com>'\n"
        "    proposed_outcome: rejected\n",
        encoding="utf-8",
    )

    pending = outcomes.load_pending(str(path))

    assert outcomes.seen_ids(pending) == {"<a@x.com>"}
    assert pending["proposals"][0]["proposed_outcome"] == "rejected"


def test_load_pending_rejects_a_malformed_file(tmp_path):
    path = tmp_path / "outcomes.pending.yaml"
    path.write_text("- not\n- a mapping\n", encoding="utf-8")

    with pytest.raises(ValueError):
        outcomes.load_pending(str(path))
