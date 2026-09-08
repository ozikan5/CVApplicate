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
    r"\b(?:" + "|".join(re.escape(a) for a in sorted(_ABBREVIATIONS, key=len, reverse=True)) + ")",
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
# opposite of a requirement.
_NON_DISCRIMINATION = re.compile(
    r"(regardless of|without regard to|does not discriminate|"
    r"equal opportunity|equal employment)",
    re.I,
)

# Stored descriptions come from job_fetcher.htmltext.description_from_html,
# which strips tags and collapses ALL whitespace to single spaces. Real JD
# <li> bullets carry no terminal punctuation, so an entire requirements list
# can merge into whatever prose follows (or precedes) it into one
# pseudo-"sentence" as far as _split_sentences is concerned. Discarding that
# whole pseudo-sentence whenever it happens to contain a non-discrimination
# marker anywhere would throw away a merged, unrelated requirement along with
# the marker (a false negative -- the critical failure mode here). Instead we
# redact only the marker phrase itself (e.g. "equal opportunity"), which is
# always safe to drop since it is never itself a requirement, and keep
# scanning the rest of the sentence -- both before and after the marker --
# for disqualifying language.
def _redact_non_discrimination_markers(sentence: str) -> str:
    return _NON_DISCRIMINATION.sub(" ", sentence)


# Shared across both CPT/OPT sponsorship patterns so "do(es) not" reads the
# same as "not able to" / "cannot" / "unable to" in either frame.
_SPONSOR_MODAL = r"(?:not able to|cannot|can't|unable to|do(?:es)?\s+not)"

# Two-tier window for the "cannot sponsor ... CPT/OPT" pattern.
#
# Close proximity (the modal and the CPT/OPT mention in one breath) is a
# genuine single statement and is safe to reject outright. But
# description_from_html (job_fetcher/htmltext.py) collapses ALL whitespace
# and leaves <li> bullets with no terminal punctuation, so several unrelated
# bullets can merge into one pseudo-sentence -- a wide gap may just as
# easily span two unrelated bullets (an unrelated "cannot sponsor visas"
# bullet plus a separate, genuinely permissive "OPT welcome" bullet) as it
# may span one real statement. A false rejection there is invisible to the
# user, while treating it as merely AMBIGUOUS costs one score and lets the
# scoring skill adjudicate the quoted sentence itself, defaulting to
# eligible. So: close -> DISQUALIFIED, wide -> AMBIGUOUS. Do not fold this
# back into a single DISQUALIFIED window.
#
# _SPONSOR_CLOSE_WINDOW is chosen from measurement, not taste: the real
# captured fixture ("...not able to sponsor visas, including CPT/OPT...")
# has an actual sponsor->CPT gap of 18 characters. 25 gives that fixture a
# small margin (+7) while sitting comfortably below the reviewer's
# real-world false-rejection case (a 33-character gap between an unrelated
# "cannot sponsor" bullet and a permissive "OPT welcome" bullet), which must
# now land in the wide/AMBIGUOUS tier rather than DISQUALIFIED.
#
# _SPONSOR_WIDE_WINDOW keeps the prior single-tier bound of 55: beyond that,
# the pattern simply does not fire and the _UNCLEAR fallback below still
# escalates any bare CPT/OPT mention to AMBIGUOUS, so there is no gap in
# coverage from leaving it here.
_SPONSOR_CLOSE_WINDOW = 25
_SPONSOR_WIDE_WINDOW = 55

_SPONSOR_CPT = re.compile(
    _SPONSOR_MODAL + r"\s+sponsor([^;]{0,%d})\b(CPT|OPT)\b" % _SPONSOR_WIDE_WINDOW,
    re.I,
)

_DISQUALIFYING = (
    (
        re.compile(_SPONSOR_MODAL + r"\s+(hire|accept|employ)[^;]{0,60}\b(CPT|OPT)\b", re.I),
        "employer does not accept CPT/OPT",
    ),
    (
        re.compile(r"U\.?S\.?\s+citizenship\s+(is\s+)?(required|as required)", re.I),
        "US citizenship required",
    ),
    (
        re.compile(r"requires?\s+U\.?S\.?\s+citizenship", re.I),
        "US citizenship required",
    ),
    (
        re.compile(r"must be\s+(?:(?:a|an)\s+)?U\.?S\.?\s+citizens?\b", re.I),
        "must be a US citizen",
    ),
    (
        re.compile(
            r"(U\.?S\.?\s+citizens?(\s+or\s+permanent\s+residents?)?\s+only"
            r"|only\s+U\.?S\.?\s+citizens?(\s+or\s+permanent\s+residents?)?)",
            re.I,
        ),
        "US citizens or permanent residents only",
    ),
    (
        re.compile(
            r"(ability to (hold or )?obtain|able to obtain|active|current"
            r"|must\s+(?:be\s+able\s+to\s+)?(?:obtain|maintain)|TS/?SCI)"
            r"[^;]{0,30}clearance",
            re.I,
        ),
        "security clearance required",
    ),
)

# Mentions that are relevant but match no known disqualifying frame: escalate
# rather than guess. "clearance" is included so a clearance mention that
# misses the (deliberately specific) disqualifying pattern above -- e.g. an
# unusual phrasing -- still surfaces as AMBIGUOUS instead of passing silently.
_UNCLEAR = re.compile(r"\b(CPT|OPT)\b|citizenship|citizen|clearance", re.I)


def authorization_verdict(jd_text: str, mode):
    """Judge a JD's work-authorization language against the profile's mode.

    Returns (verdict, reason). Only the 'cpt-opt' mode filters anything.
    """
    if mode != "cpt-opt" or not jd_text:
        return OK, None

    unclear_reason = None
    for sentence in _split_sentences(jd_text):
        has_marker = _NON_DISCRIMINATION.search(sentence) is not None
        scan_text = _redact_non_discrimination_markers(sentence) if has_marker else sentence

        for pattern, reason in _DISQUALIFYING:
            if pattern.search(scan_text):
                return DISQUALIFIED, reason

        # Two-tier sponsor/CPT-OPT check (see _SPONSOR_CLOSE_WINDOW above):
        # close proximity disqualifies outright, wide proximity only
        # escalates to AMBIGUOUS, carrying the quoted sentence for the
        # scoring skill to adjudicate.
        sponsor_match = _SPONSOR_CPT.search(scan_text)
        if sponsor_match:
            gap = len(sponsor_match.group(1))
            if gap <= _SPONSOR_CLOSE_WINDOW:
                return DISQUALIFIED, "employer states it cannot sponsor CPT/OPT"
            if unclear_reason is None:
                unclear_reason = (
                    "employer's 'cannot sponsor' language and a CPT/OPT mention "
                    "are far enough apart that they may belong to two different, "
                    "merged bullets: " + " ".join(sentence.split())[:160]
                )

        # A non-discrimination marker anywhere in the sentence suppresses the
        # AMBIGUOUS fallback for it too: real EEO boilerplate ("regardless of
        # race, ..., citizenship, ...") legitimately contains words like
        # "citizenship" nowhere near any disqualifying frame, and merged HTML
        # blocks can put an unrelated bare "CPT/OPT" mention in the same
        # pseudo-sentence as EEO language without that mention itself
        # implying anything about eligibility.
        if not has_marker and unclear_reason is None and _UNCLEAR.search(sentence):
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
