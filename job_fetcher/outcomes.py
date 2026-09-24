"""Deterministic rules for turning recruiting mail into outcome proposals.

Nothing here touches the network or the mailbox; job_fetcher.mailbox does that.
"""

from __future__ import annotations

import os
import re
import yaml

ATS_DOMAINS = (
    "greenhouse.io", "greenhouse-mail.io", "lever.co", "myworkday.com",
    "myworkdayjobs.com", "ashbyhq.com", "smartrecruiters.com", "icims.com",
    "taleo.net",
)
ASSESSMENT_DOMAINS = ("hackerrank.com", "codesignal.com", "hirevue.com")


def sender_domain(address: str) -> str:
    if "@" not in (address or ""):
        return ""
    return address.rsplit("@", 1)[1].strip().lower()


def _domain_in(domain: str, known) -> bool:
    return any(domain == k or domain.endswith("." + k) for k in known)


def company_aliases(company: str) -> list:
    """'Chicago Trading Company (CTC)' -> full name, compacted name, acronym."""
    acronyms = [a.strip().lower() for a in re.findall(r"\(([^)]*)\)", company or "")]
    base = re.sub(r"\([^)]*\)", "", company or "").strip().lower()
    base = " ".join(base.split())
    aliases = []
    for alias in [base, base.replace(" ", "")] + acronyms:
        if alias and alias not in aliases:
            aliases.append(alias)
    return aliases


def _whole_word(alias: str, text: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def candidate_applications(message: dict, applications: list) -> list:
    haystack = f"{message.get('from', '')} {message.get('from_address', '')} " \
               f"{message.get('subject', '')}".lower()
    return [
        app["id"] for app in applications
        if any(_whole_word(alias, haystack) for alias in company_aliases(app.get("company", "")))
    ]


def is_candidate(message: dict, applications: list) -> bool:
    domain = sender_domain(message.get("from_address", ""))
    if _domain_in(domain, ATS_DOMAINS) or _domain_in(domain, ASSESSMENT_DOMAINS):
        return True
    return bool(candidate_applications(message, applications))


STAGES = ("pending", "assessment", "interview", "offer")
PROPOSABLE = ("assessment", "interview", "offer", "rejected")
KNOWN_OUTCOMES = STAGES + ("rejected", "no_response")


def regresses(current: str, proposed: str) -> bool:
    """True when applying `proposed` would move an application backward.

    Stages only move forward. `rejected` may follow any stage. A positive stage
    after `rejected` needs a human. `no_response` may be followed by anything,
    since a late reply is progress.

    Any value outside the recognised set counts as a regression: an unknown
    `proposed` or `current` needs a human, so it must not be treated as safe.
    """
    if proposed not in PROPOSABLE or current not in KNOWN_OUTCOMES:
        return True
    if proposed == current:
        return False
    if proposed == "rejected":
        return False
    if current == "rejected":
        return True
    if current in STAGES and proposed in STAGES:
        return STAGES.index(proposed) < STAGES.index(current)
    return False


def default_answer(proposal: dict, current: str) -> bool:
    """Yes only for a high-confidence, single-application, forward proposal.

    Anything else defaults to no, so it can never be accepted just by pressing
    through the list.
    """
    proposed_outcome = proposal.get("proposed_outcome")
    return (
        proposal.get("confidence") == "high"
        and proposal.get("application_id") is not None
        and proposed_outcome in PROPOSABLE
        and current in KNOWN_OUTCOMES
        and not regresses(current, proposed_outcome)
    )


def load_pending(path: str) -> dict:
    if not os.path.exists(path):
        return {"seen": [], "proposals": []}
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        return {"seen": [], "proposals": []}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a mapping with 'seen' and 'proposals' keys")
    seen = data.get("seen")
    if seen is not None and not isinstance(seen, list):
        raise ValueError(f"{path}: 'seen' must be a list")
    proposals = data.get("proposals")
    if proposals is not None and not isinstance(proposals, list):
        raise ValueError(f"{path}: 'proposals' must be a list")
    return {"seen": list(seen or []), "proposals": list(proposals or [])}


def seen_ids(pending: dict) -> set:
    return set(pending.get("seen") or [])
