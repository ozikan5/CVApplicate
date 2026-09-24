"""Read-only access to a mailbox, and parsing of the messages in it.

This module is the only code in the project that touches IMAP. It never
changes the mailbox: folders are opened with EXAMINE and every fetch uses
BODY.PEEK, so messages are never marked read, moved, flagged or deleted.
"""

from __future__ import annotations

import email
import hashlib
from email import policy
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

from job_fetcher.htmltext import strip_html

BODY_LIMIT = 1500

# IMAP requires English month abbreviations. strftime("%b") is locale-dependent
# and yields e.g. "Ağu" on a Turkish locale, which the server rejects.
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def imap_since(day) -> str:
    return f"{day.day:02d}-{_MONTHS[day.month - 1]}-{day.year}"


def _decode(value) -> str:
    if value is None:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def _part_text(part) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _body_text(msg) -> str:
    plain = None
    html = None
    for part in msg.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain" and plain is None:
            plain = _part_text(part)
        elif content_type == "text/html" and html is None:
            html = _part_text(part)
    if plain and plain.strip():
        return " ".join(plain.split())
    if html:
        return strip_html(html)
    return ""


def parse_message(raw: bytes) -> dict:
    msg = email.message_from_bytes(raw, policy=policy.compat32)
    subject = " ".join(_decode(msg.get("Subject")).split())
    sender = " ".join(_decode(msg.get("From")).split())
    _, address = parseaddr(sender)
    date_raw = msg.get("Date")
    try:
        received = parsedate_to_datetime(date_raw).date().isoformat()
    except (TypeError, ValueError, IndexError, AttributeError):
        received = None
    message_id = (msg.get("Message-ID") or "").strip()
    if not message_id:
        digest = hashlib.sha1(
            f"{sender}|{date_raw}|{subject}".encode("utf-8", "replace")
        ).hexdigest()
        message_id = f"sha1:{digest[:20]}"
    return {
        "message_id": message_id,
        "from": sender,
        "from_address": address.lower(),
        "received": received,
        "subject": subject,
        "body": _body_text(msg)[:BODY_LIMIT],
    }
