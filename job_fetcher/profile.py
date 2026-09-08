from __future__ import annotations

import re

import yaml

VALID_SEEKING = ("internship", "new-grad", "full-time")
VALID_AUTHORIZATION = ("cpt-opt", "citizen-or-pr", "unrestricted")


class ProfileError(Exception):
    pass


def load_profile(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except FileNotFoundError:
        raise ProfileError(
            f"{path} not found. Copy profile.example.yaml to {path} and fill in what "
            "you are seeking and eligible for."
        )

    if data is None:
        raise ProfileError(f"{path} is empty. See profile.example.yaml for the shape.")
    if not isinstance(data, dict):
        raise ProfileError(
            f"{path} must be a mapping of settings. See profile.example.yaml."
        )

    seeking = data.get("seeking", "internship")
    if seeking not in VALID_SEEKING:
        raise ProfileError(
            f"seeking: {seeking!r} is not one of {', '.join(VALID_SEEKING)}"
        )

    authorization = data.get("work_authorization")
    if authorization is not None and authorization not in VALID_AUTHORIZATION:
        raise ProfileError(
            f"work_authorization: {authorization!r} is not one of "
            f"{', '.join(VALID_AUTHORIZATION)} (omit the key to disable the rule)"
        )

    locations = data.get("locations") or []
    if not isinstance(locations, list):
        raise ProfileError("locations: must be a list of location strings")

    return {
        "seeking": seeking,
        "graduation": data.get("graduation"),
        "locations": locations,
        "max_years_experience_required": data.get("max_years_experience_required"),
        "work_authorization": authorization,
    }


OK = "ok"
DISQUALIFIED = "disqualified"
AMBIGUOUS = "ambiguous"

_ABBREVIATIONS = (
    "U.S.A.", "U.S.", "e.g.", "i.e.", "Ph.D.", "B.S.", "M.S.", "B.Sc.", "M.Sc.",
    "Inc.", "Ltd.", "Co.", "Corp.", "St.", "No.", "etc.", "vs.", "approx.",
    "Dr.", "Mr.", "Mrs.", "Ms.",
)
_ABBREVIATION_RE = re.compile(
    "|".join(re.escape(a) for a in sorted(_ABBREVIATIONS, key=len, reverse=True)),
    re.IGNORECASE,
)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;])\s+")
_SENTINEL = "\x00"


def _split_sentences(text: str) -> list:
    """Split into sentences without breaking on common abbreviations.

    The abbreviation list is protected by substituting a sentinel for its periods
    before splitting and restoring them afterwards. Sorting by length descending
    matters: "U.S.A." must be protected before "U.S." can match its prefix.
    """
    protected = _ABBREVIATION_RE.sub(
        lambda m: m.group(0).replace(".", _SENTINEL), text
    )
    return [
        part.replace(_SENTINEL, ".") for part in _SENTENCE_BOUNDARY.split(protected)
    ]

# A match inside any of these is a non-discrimination statement, which is the
# opposite of a requirement. Discard the whole sentence.
_NON_DISCRIMINATION = re.compile(
    r"(regardless of|without regard to|does not discriminate|"
    r"equal opportunity|equal employment)",
    re.I,
)

_DISQUALIFYING = (
    (
        re.compile(r"(not able to|cannot|can't|unable to)\s+sponsor[^;]{0,90}\b(CPT|OPT)\b", re.I),
        "employer states it cannot sponsor CPT/OPT",
    ),
    (
        re.compile(r"(do(es)? not|cannot|can't|unable to)\s+(hire|accept|employ)[^;]{0,60}\b(CPT|OPT)\b", re.I),
        "employer does not accept CPT/OPT",
    ),
    (
        re.compile(r"U\.?S\.?\s+citizenship\s+(is\s+)?(required|as required)", re.I),
        "US citizenship required",
    ),
    (
        re.compile(r"must be (a|an)\s+U\.?S\.?\s+citizen", re.I),
        "must be a US citizen",
    ),
    (
        re.compile(r"U\.?S\.?\s+citizens?(\s+or\s+permanent\s+residents?)?\s+only", re.I),
        "US citizens or permanent residents only",
    ),
    (
        re.compile(r"(ability to (hold or )?obtain|active|current)[^;]{0,30}security clearance", re.I),
        "security clearance required",
    ),
)

# Mentions that are relevant but match no known disqualifying frame: escalate
# rather than guess.
_UNCLEAR = re.compile(r"\b(CPT|OPT)\b|citizenship|citizen", re.I)


def authorization_verdict(jd_text: str, mode):
    """Judge a JD's work-authorization language against the profile's mode.

    Returns (verdict, reason). Only the 'cpt-opt' mode filters anything.
    """
    if mode != "cpt-opt" or not jd_text:
        return OK, None

    unclear_reason = None
    for sentence in _split_sentences(jd_text):
        if _NON_DISCRIMINATION.search(sentence):
            continue
        for pattern, reason in _DISQUALIFYING:
            if pattern.search(sentence):
                return DISQUALIFIED, reason
        if unclear_reason is None and _UNCLEAR.search(sentence):
            unclear_reason = (
                "work-authorization language present but not clearly disqualifying: "
                + " ".join(sentence.split())[:160]
            )

    if unclear_reason is not None:
        return AMBIGUOUS, unclear_reason
    return OK, None


def location_matches(location_text, allowed) -> bool:
    """True when the posting's location is acceptable.

    An empty `allowed` disables the rule, and missing location text counts as a
    match: an unstated location is ambiguous, and the gate errs toward eligible.
    """
    if not allowed:
        return True
    if not location_text:
        return True
    haystack = location_text.lower()
    return any(entry.lower() in haystack for entry in allowed)
