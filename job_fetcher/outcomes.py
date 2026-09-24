"""Deterministic rules for turning recruiting mail into outcome proposals.

Nothing here touches the network or the mailbox; job_fetcher.mailbox does that.
"""

from __future__ import annotations

import re

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
