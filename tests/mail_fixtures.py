"""Structurally genuine email fixtures, built with the standard library.

The wording is invented; the structure — multipart layout, encoded headers,
transfer encodings, charsets — is real, because the email package produces it.
"""

from __future__ import annotations

import datetime
from email.message import EmailMessage, Message
from email.utils import format_datetime

DEFAULT_DATE = datetime.datetime(2026, 9, 2, 14, 30, tzinfo=datetime.timezone.utc)


def build_message(
    *,
    sender,
    subject,
    plain=None,
    html=None,
    date=DEFAULT_DATE,
    message_id="<fixture-1@mail.example.com>",
    charset="utf-8",
    cte=None,
):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = "candidate@example.com"
    msg["Subject"] = subject
    msg["Date"] = format_datetime(date)
    if message_id is not None:
        msg["Message-ID"] = message_id
    if plain is not None:
        msg.set_content(plain, charset=charset, cte=cte)
        if html is not None:
            msg.add_alternative(html, subtype="html", charset=charset)
    elif html is not None:
        msg.set_content(html, subtype="html", charset=charset, cte=cte)
    return msg.as_bytes()


def build_q_encoded_subject():
    """A pre-encoded RFC 2047 Q-encoded subject, kept verbatim by compat32 Message."""
    msg = Message()
    msg["From"] = "Citadel Recruiting <no-reply@citadel.com>"
    msg["Subject"] = "=?UTF-8?Q?Your_application_=E2=80=94_next_steps?="
    msg["Date"] = format_datetime(DEFAULT_DATE)
    msg["Message-ID"] = "<q-encoded@mail.citadel.com>"
    msg["Content-Type"] = 'text/plain; charset="utf-8"'
    msg.set_payload("Thank you for applying.")
    return msg.as_bytes()
