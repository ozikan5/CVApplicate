"""Standing answers for application forms, stored in answers.local.yaml.

The file is read by an agent filling forms, so it must never hold a password,
an SSN or national ID, a passport number, bank or card details, or a date of
birth. The loader refuses a file with a key naming any of those, and
`remember` refuses to store a question asking for one. Error messages name the
offending key path, never its value.

The loader also rejects any string value that is shaped like an SSN (a
9-digit number, optionally hyphenated 3-2-4) or a payment card (13-19 digits
that pass the Luhn check), even under an innocuous-looking key; `remember`
applies the same check to the answer being stored.
"""

from __future__ import annotations

import datetime
import os
import re
import tempfile

import yaml

FORBIDDEN_TOKENS = (
    "password", "passwd", "ssn", "passport", "bank", "card", "dob",
    "birthdate", "dateofbirth", "socialsecurity",
)
FORBIDDEN_PHRASES = (
    ("social", "security"),
    ("date", "of", "birth"),
    ("birth", "date"),
    ("national", "id"),
)

# Unambiguous roots checked as substrings against the separator-stripped,
# lowercased text. These catch split words (pass-word, pass_word) and
# lowercase compounds (cardnumber) that camelCase-splitting and whole-token
# matching would otherwise miss, without flagging ordinary words that merely
# contain a short forbidden token as a substring (postcard, discard).
FORBIDDEN_SUBSTRINGS = (
    "password", "passwd", "passport", "socialsecurity", "dateofbirth",
    "birthdate", "nationalid",
    "creditcard", "debitcard", "cardnumber", "bankaccount", "accountnumber",
    "routingnumber", "iban", "cvv",
    "acctnumber", "acctno", "accountno", "sortcode",
)


class AnswersError(Exception):
    pass


def _tokens(text) -> list:
    return re.findall(r"[a-z0-9]+", str(text).lower())


def _split_camel_case(text: str) -> str:
    # lower/digit -> Upper: "cardNumber" -> "card Number"
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    # a run of capitals followed by a capitalised word: "SSNNumber" ->
    # "SSN Number" (splits before the capital that starts the new word).
    text = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", text)
    return text


def names_forbidden(text) -> bool:
    raw = str(text)
    tokens = _tokens(_split_camel_case(raw))
    if any(token in FORBIDDEN_TOKENS for token in tokens):
        return True
    for phrase in FORBIDDEN_PHRASES:
        width = len(phrase)
        for start in range(len(tokens) - width + 1):
            if tuple(tokens[start:start + width]) == phrase:
                return True
    stripped = re.sub(r"[^a-z0-9]", "", raw.lower())
    if any(root in stripped for root in FORBIDDEN_SUBSTRINGS):
        return True
    return False


def _luhn_valid(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _looks_like_ssn(value: str) -> bool:
    stripped = value.replace(" ", "")
    return re.fullmatch(r"\d{3}[-.]?\d{2}[-.]?\d{4}", stripped) is not None


def _looks_like_card(value: str) -> bool:
    stripped = re.sub(r"[ -]", "", value)
    if not stripped.isdigit() or not (13 <= len(stripped) <= 19):
        return False
    return _luhn_valid(stripped)


def value_looks_forbidden(value) -> bool:
    if isinstance(value, bool):
        # bool subclasses int, so check it first and exclude it
        return False
    if isinstance(value, str):
        return _looks_like_ssn(value) or _looks_like_card(value)
    if isinstance(value, int):
        # Check int values via str() but skip float
        return _looks_like_ssn(str(value)) or _looks_like_card(str(value))
    # float and other types: skip check
    return False


def forbidden_values(data, prefix: str = "") -> list:
    found = []
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                if value_looks_forbidden(value):
                    found.append(path)
            else:
                found.extend(forbidden_values(value, path))
    elif isinstance(data, list):
        for index, item in enumerate(data):
            path = f"{prefix}[{index}]"
            if isinstance(item, (str, int)) and not isinstance(item, bool):
                if value_looks_forbidden(item):
                    found.append(path)
            else:
                found.extend(forbidden_values(item, path))
    return found


def forbidden_keys(data, prefix: str = "") -> list:
    found = []
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if names_forbidden(key):
                found.append(path)
            found.extend(forbidden_keys(value, path))
    elif isinstance(data, list):
        for index, item in enumerate(data):
            found.extend(forbidden_keys(item, f"{prefix}[{index}]"))
    return found


def normalize_question(text) -> str:
    return " ".join(_tokens(text))


def _validate_learned(learned, path: str) -> list:
    if learned is None:
        return []
    if not isinstance(learned, list):
        raise AnswersError(f"{path}: 'learned' must be a list")
    for index, entry in enumerate(learned, start=1):
        if (not isinstance(entry, dict)
                or not isinstance(entry.get("question"), str)
                or not isinstance(entry.get("answer"), str)):
            raise AnswersError(
                f"{path}: learned entry {index} needs a 'question' and an 'answer' string"
            )
        if names_forbidden(entry["question"]):
            raise AnswersError(
                f"{path}: learned entry {index} asks for a forbidden category; remove it"
            )
    return learned


def load_answers(path: str):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError:
        raise AnswersError(f"{path} is not valid YAML") from None
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise AnswersError(f"{path} must be a mapping. See answers.example.yaml.")
    bad = forbidden_keys(data)
    if bad:
        raise AnswersError(
            f"{path} contains a forbidden category ({', '.join(bad)}). Remove it: "
            "passwords, SSNs, passport numbers, bank or card details and dates of "
            "birth must never be in a file an agent reads."
        )
    bad_values = forbidden_values(data)
    if bad_values:
        raise AnswersError(
            f"{path} has a value that looks like an SSN or a payment card "
            f"({', '.join(bad_values)}). Remove it: those must never be in a "
            "file an agent reads."
        )
    data["learned"] = _validate_learned(data.get("learned"), path)
    return data


def _write_atomically(path: str, data: dict) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    handle, temporary = tempfile.mkstemp(dir=directory, prefix=".answers-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            yaml.safe_dump(data, stream, sort_keys=False, allow_unicode=True,
                           default_flow_style=False)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def remember(path: str, question, answer, today: datetime.date) -> dict:
    if not isinstance(question, str) or not question.strip():
        raise AnswersError("question must be a non-empty string")
    if not isinstance(answer, str) or not answer.strip():
        raise AnswersError("answer must be a non-empty string")
    if names_forbidden(question):
        raise AnswersError("that question asks for a forbidden category; it is never stored")
    if value_looks_forbidden(answer):
        raise AnswersError("that answer looks like an SSN or a payment card; it is never stored")

    data = load_answers(path)
    if data is None:
        data = {"learned": []}

    entry = {"question": question.strip(), "answer": answer.strip(),
             "added": today.isoformat()}
    key = normalize_question(question)
    learned = data["learned"]
    for index, existing in enumerate(learned):
        if normalize_question(existing["question"]) == key:
            learned[index] = entry
            break
    else:
        learned.append(entry)

    _write_atomically(path, data)
    return entry
