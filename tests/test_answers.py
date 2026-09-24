from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from job_fetcher import answers

REPO_ROOT = Path(__file__).parent.parent
TODAY = datetime.date(2026, 9, 24)


def _write(tmp_path, text):
    path = tmp_path / "answers.local.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_load_missing_file_returns_none(tmp_path):
    assert answers.load_answers(str(tmp_path / "absent.yaml")) is None


def test_load_empty_file_is_an_empty_mapping_with_learned(tmp_path):
    assert answers.load_answers(_write(tmp_path, "")) == {"learned": []}


def test_load_keeps_empty_values(tmp_path):
    data = answers.load_answers(_write(tmp_path, "contact:\n  phone: ''\neducation:\n  gpa: null\n"))
    assert data["contact"]["phone"] == ""
    assert data["education"]["gpa"] is None


def test_example_file_loads_cleanly():
    data = answers.load_answers(str(REPO_ROOT / "answers.example.yaml"))
    assert data["demographics"]["gender"] == "Decline to self-identify"
    assert data["work_authorization"]["requires_sponsorship_now"] == ""
    assert data["learned"] == []


@pytest.mark.parametrize("key", [
    "password", "ssn", "social_security_number", "passport_number",
    "bank_account", "credit_card", "date_of_birth", "dob", "Birthdate",
])
def test_load_rejects_a_forbidden_key_at_any_depth_without_echoing_it(tmp_path, key):
    path = _write(tmp_path, f"contact:\n  nested:\n    {key}: secret-value-123\n")
    with pytest.raises(answers.AnswersError) as caught:
        answers.load_answers(path)
    assert "secret-value-123" not in str(caught.value)
    assert key in str(caught.value)


def test_load_rejects_a_forbidden_key_inside_a_list(tmp_path):
    with pytest.raises(answers.AnswersError):
        answers.load_answers(_write(tmp_path, "extra:\n  - passport: X\n"))


def test_load_rejects_a_non_mapping(tmp_path):
    with pytest.raises(answers.AnswersError):
        answers.load_answers(_write(tmp_path, "- a\n- b\n"))


def test_load_rejects_invalid_yaml(tmp_path):
    with pytest.raises(answers.AnswersError):
        answers.load_answers(_write(tmp_path, "contact: [unclosed\n"))


def test_load_rejects_a_malformed_learned_entry(tmp_path):
    with pytest.raises(answers.AnswersError):
        answers.load_answers(_write(tmp_path, "learned:\n  - just a string\n"))


def test_load_rejects_learned_that_is_not_a_list(tmp_path):
    with pytest.raises(answers.AnswersError):
        answers.load_answers(_write(tmp_path, "learned: nope\n"))


def test_load_rejects_a_forbidden_learned_question(tmp_path):
    with pytest.raises(answers.AnswersError):
        answers.load_answers(_write(
            tmp_path, "learned:\n  - question: 'What is your SSN?'\n    answer: 'x'\n"))


def test_ordinary_keys_are_not_forbidden():
    assert not answers.names_forbidden("requires_sponsorship_future")
    assert not answers.names_forbidden("dashboard_url")
    assert not answers.names_forbidden("discard_policy")
    assert not answers.names_forbidden("date_available")


def test_normalize_question_ignores_case_punctuation_and_spacing():
    assert answers.normalize_question("  Are you legally AUTHORIZED to work?! ") == \
        answers.normalize_question("are you legally authorized   to work")


def test_remember_appends_to_learned_and_keeps_other_keys(tmp_path):
    path = _write(tmp_path, "contact:\n  phone: '555'\nlearned: []\n")
    entry = answers.remember(path, "Are you open to relocation?", "Yes", TODAY)
    assert entry == {"question": "Are you open to relocation?", "answer": "Yes",
                     "added": "2026-09-24"}
    data = answers.load_answers(path)
    assert data["learned"] == [entry]
    assert data["contact"]["phone"] == "555"


def test_remember_replaces_a_normalised_duplicate(tmp_path):
    path = _write(tmp_path, "learned: []\n")
    answers.remember(path, "Open to relocation?", "No", TODAY)
    answers.remember(path, "open to RELOCATION", "Yes", datetime.date(2026, 9, 25))
    learned = answers.load_answers(path)["learned"]
    assert len(learned) == 1
    assert learned[0]["answer"] == "Yes"
    assert learned[0]["added"] == "2026-09-25"


def test_remember_creates_the_file_when_missing(tmp_path):
    path = str(tmp_path / "answers.local.yaml")
    answers.remember(path, "Preferred pronouns?", "they/them", TODAY)
    assert answers.load_answers(path)["learned"][0]["answer"] == "they/them"


def test_remember_refuses_a_forbidden_question_and_leaves_the_file_alone(tmp_path):
    path = _write(tmp_path, "learned: []\n")
    before = Path(path).read_text(encoding="utf-8")
    with pytest.raises(answers.AnswersError) as caught:
        answers.remember(path, "Social Security Number", "123-45-6789", TODAY)
    assert "123-45-6789" not in str(caught.value)
    assert Path(path).read_text(encoding="utf-8") == before


@pytest.mark.parametrize("question, answer", [
    ("", "x"), ("   ", "x"), ("q", ""), ("q", "  "), (None, "x"), ("q", 5),
])
def test_remember_refuses_empty_or_non_string(tmp_path, question, answer):
    with pytest.raises(answers.AnswersError):
        answers.remember(_write(tmp_path, ""), question, answer, TODAY)


def test_remember_keeps_quotes_and_colons_verbatim(tmp_path):
    path = _write(tmp_path, "")
    answers.remember(path, 'Why "us": really?', "Because: it's 'great'", TODAY)
    assert answers.load_answers(path)["learned"][0]["answer"] == "Because: it's 'great'"


def test_remember_refuses_to_write_into_an_invalid_file(tmp_path):
    path = _write(tmp_path, "contact:\n  password: hunter2\n")
    with pytest.raises(answers.AnswersError):
        answers.remember(path, "Open to relocation?", "Yes", TODAY)
    assert "hunter2" in Path(path).read_text(encoding="utf-8")


# --- Security finding: tokenizer bypasses -------------------------------

@pytest.mark.parametrize("key", [
    "cardNumber", "bankAccountNumber", "passportNo", "socialSecurityNumber",
    "pass-word", "pass_word", "national_id", "SSNNumber",
])
def test_names_forbidden_catches_tokenizer_bypasses(key):
    assert answers.names_forbidden(key)


@pytest.mark.parametrize("key", [
    "cardNumber", "bankAccountNumber", "passportNo", "socialSecurityNumber",
    "pass-word", "pass_word", "national_id", "SSNNumber",
])
def test_load_rejects_bypass_keys_without_echoing_value(tmp_path, key):
    path = _write(tmp_path, f"contact:\n  nested:\n    {key}: secret-value-123\n")
    with pytest.raises(answers.AnswersError) as caught:
        answers.load_answers(path)
    assert "secret-value-123" not in str(caught.value)
    assert key in str(caught.value)


@pytest.mark.parametrize("key", [
    "postcard", "discard", "passing_grade", "embankment_notes", "lessons",
])
def test_names_forbidden_has_no_false_positives_on_lookalikes(key):
    assert not answers.names_forbidden(key)


def test_passing_grade_does_not_trip_the_password_substring_check():
    # "passinggrade" must not contain the "password" root once separators
    # are stripped; guards against a fuzzy pass...word pattern.
    assert not answers.names_forbidden("passing_grade")
    assert not answers.names_forbidden("passingGrade")


# --- Security finding: value-shaped secrets -----------------------------

def test_load_rejects_a_key_whose_value_looks_like_an_ssn(tmp_path):
    path = _write(tmp_path, "contact:\n  nested:\n    id_number: '123-45-6789'\n")
    with pytest.raises(answers.AnswersError) as caught:
        answers.load_answers(path)
    assert "123-45-6789" not in str(caught.value)
    assert "id_number" in str(caught.value)


def test_load_rejects_a_key_whose_value_looks_like_a_luhn_valid_card(tmp_path):
    path = _write(tmp_path, "contact:\n  nested:\n    misc: '4111111111111111'\n")
    with pytest.raises(answers.AnswersError) as caught:
        answers.load_answers(path)
    assert "4111111111111111" not in str(caught.value)
    assert "misc" in str(caught.value)


@pytest.mark.parametrize("value", [
    "555-123-4567",   # 10-digit US phone number
    "3.8",            # GPA
    "2026",           # year
    "2026-09-24",     # date
    "12345",          # ZIP
    "4111111111111112",  # 16 digits but fails Luhn
])
def test_value_looks_forbidden_has_no_false_positives(value):
    assert not answers.value_looks_forbidden(value)


@pytest.mark.parametrize("value", [
    "123-45-6789",
    "123456789",
    "4111111111111111",
])
def test_value_looks_forbidden_catches_ssn_and_card_shapes(value):
    assert answers.value_looks_forbidden(value)


def test_load_allows_plausible_non_secret_values(tmp_path):
    path = _write(tmp_path, (
        "contact:\n"
        "  phone: '555-123-4567'\n"
        "education:\n"
        "  gpa: '3.8'\n"
        "  graduation_year: '2026'\n"
        "  start_date: '2026-09-24'\n"
        "  zip: '12345'\n"
    ))
    data = answers.load_answers(path)
    assert data["contact"]["phone"] == "555-123-4567"


def test_remember_refuses_an_ssn_shaped_answer_and_does_not_echo_it(tmp_path):
    path = _write(tmp_path, "learned: []\n")
    before = Path(path).read_text(encoding="utf-8")
    with pytest.raises(answers.AnswersError) as caught:
        answers.remember(path, "What is your ID number?", "123-45-6789", TODAY)
    assert "123-45-6789" not in str(caught.value)
    assert Path(path).read_text(encoding="utf-8") == before


def test_remember_refuses_a_card_shaped_answer_and_does_not_echo_it(tmp_path):
    path = _write(tmp_path, "learned: []\n")
    before = Path(path).read_text(encoding="utf-8")
    with pytest.raises(answers.AnswersError) as caught:
        answers.remember(path, "Payment reference?", "4111111111111111", TODAY)
    assert "4111111111111111" not in str(caught.value)
    assert Path(path).read_text(encoding="utf-8") == before


def test_remember_allows_a_phone_number_answer(tmp_path):
    path = _write(tmp_path, "learned: []\n")
    entry = answers.remember(path, "Best contact number?", "555-123-4567", TODAY)
    assert entry["answer"] == "555-123-4567"
