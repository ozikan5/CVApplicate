"""Read-only access to a mailbox, and parsing of the messages in it.

This module is the only code in the project that touches IMAP. It never
changes the mailbox: folders are opened with EXAMINE and every fetch uses
BODY.PEEK, so messages are never marked read, moved, flagged or deleted.
"""

from __future__ import annotations

import email
import hashlib
import imaplib
import re
import socket
import ssl
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


HEADERS_SPEC = "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])"
FULL_SPEC = "(BODY.PEEK[])"
FETCH_BATCH = 200


class MailboxError(Exception):
    """Configuration or authentication problem. Not retried."""

    exit_code = 2


class MailboxUnavailable(Exception):
    """Network problem. Retried on the next run."""

    exit_code = 4


_LIST_RE = re.compile(r'^\((?P<flags>[^)]*)\)\s+(?P<delim>"[^"]*"|NIL)\s+(?P<name>.+)$')


def find_all_mail_folder(conn):
    """Find the folder carrying the \\All special-use flag.

    Resolved by flag, not by name: Gmail localizes folder names. The raw name is
    returned unchanged, so a modified-UTF-7 name never needs decoding.
    """
    typ, data = conn.list()
    if typ != "OK":
        return None
    for line in data or []:
        if isinstance(line, bytes):
            line = line.decode("utf-8", "replace")
        if not isinstance(line, str):
            continue
        match = _LIST_RE.match(line.strip())
        if match and "\\All" in match.group("flags").split():
            return match.group("name").strip()
    return None


def open_folder(conn):
    warnings = []
    folder = find_all_mail_folder(conn)
    if folder is None:
        folder = "INBOX"
        warnings.append(
            "no \\All mailbox found; searching INBOX only, so archived or "
            "filtered mail will be missed"
        )
    typ, _ = conn.select(folder, readonly=True)
    if typ != "OK":
        raise MailboxError(f"could not open {folder} read-only")
    return folder, warnings


def search_since(conn, day):
    typ, data = conn.search(None, "SINCE", imap_since(day))
    if typ != "OK":
        raise MailboxError("IMAP search failed")
    if not data or not data[0]:
        return []
    return [seq.decode() for seq in data[0].split()]


def fetch_parsed(conn, seqs, spec):
    results = []
    for start in range(0, len(seqs), FETCH_BATCH):
        batch = seqs[start:start + FETCH_BATCH]
        typ, data = conn.fetch(",".join(batch), spec)
        if typ != "OK":
            raise MailboxError("IMAP fetch failed")
        for item in data or []:
            if not isinstance(item, tuple) or len(item) < 2:
                continue
            seq = item[0].split(b" ", 1)[0].decode()
            try:
                parsed = parse_message(item[1])
            except Exception as error:
                digest = hashlib.sha1(bytes(item[1])[:500]).hexdigest()
                parsed = {
                    "message_id": f"unparseable:{digest[:20]}",
                    "from": "", "from_address": "", "received": None,
                    "subject": "", "body": "",
                    "unparseable": type(error).__name__,
                }
            parsed["seq"] = seq
            results.append(parsed)
    return results


def connect(host, user, password):
    """Log in over IMAPS. Error messages never include the password."""
    try:
        conn = imaplib.IMAP4_SSL(host, timeout=30, ssl_context=ssl.create_default_context())
        conn.login(user, password)
        return conn
    except imaplib.IMAP4.error:
        raise MailboxError(
            "IMAP login failed. Check that IMAP is enabled (Gmail -> Settings -> "
            "Forwarding and POP/IMAP -> Enable IMAP) and that SMTP_APP_PASSWORD "
            "is a current app password."
        ) from None
    except (socket.timeout, OSError) as error:
        raise MailboxUnavailable(
            f"could not reach {host}: {type(error).__name__}"
        ) from None
