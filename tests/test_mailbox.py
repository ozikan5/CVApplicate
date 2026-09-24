from __future__ import annotations

import datetime
import locale
import re

import pytest

from job_fetcher import mailbox
from tests.mail_fixtures import build_message, build_q_encoded_subject

SENDER = "Citadel Recruiting <no-reply@citadel.com>"


def test_parse_message_prefers_plain_over_html():
    raw = build_message(
        sender=SENDER, subject="Update", plain="Plain body wins.", html="<p>HTML body</p>"
    )

    assert mailbox.parse_message(raw)["body"] == "Plain body wins."


def test_parse_message_strips_an_html_only_body():
    raw = build_message(
        sender=SENDER,
        subject="Update",
        html="<p>Unfortunately, we will <b>not</b> be moving forward.</p>",
    )

    assert mailbox.parse_message(raw)["body"] == (
        "Unfortunately, we will not be moving forward."
    )


def test_parse_message_decodes_an_encoded_turkish_sender():
    raw = build_message(sender="Özge Şahin <recruiting@ctc.com>", subject="Hi", plain="x")

    assert b"=?utf-8?" in raw.lower()  # proves the header really was encoded
    parsed = mailbox.parse_message(raw)
    assert "Özge Şahin" in parsed["from"]
    assert parsed["from_address"] == "recruiting@ctc.com"


def test_parse_message_decodes_a_q_encoded_subject():
    parsed = mailbox.parse_message(build_q_encoded_subject())

    assert parsed["subject"] == "Your application — next steps"


def test_parse_message_decodes_a_base64_body():
    text = "Your HackerRank assessment is ready."
    raw = build_message(sender=SENDER, subject="Assessment", plain=text, cte="base64")

    assert text.encode() not in raw  # proves the body really was base64-encoded
    assert mailbox.parse_message(raw)["body"] == text


def test_parse_message_decodes_a_quoted_printable_body():
    text = "Merhaba — değerlendirme hazır."
    raw = build_message(sender=SENDER, subject="QP", plain=text, cte="quoted-printable")

    assert text.encode() not in raw  # proves quoted-printable encoding happened
    assert mailbox.parse_message(raw)["body"] == text


def test_parse_message_decodes_a_latin_1_body():
    raw = build_message(
        sender=SENDER, subject="Latin-1", plain="Résumé reçu.", charset="iso-8859-1"
    )

    assert mailbox.parse_message(raw)["body"] == "Résumé reçu."


def test_parse_message_truncates_the_body():
    raw = build_message(sender=SENDER, subject="Long", plain="word " * 2000)

    assert len(mailbox.parse_message(raw)["body"]) == mailbox.BODY_LIMIT


def test_parse_message_falls_back_to_a_stable_id_without_message_id():
    first = mailbox.parse_message(
        build_message(sender=SENDER, subject="No id", plain="x", message_id=None)
    )
    again = mailbox.parse_message(
        build_message(sender=SENDER, subject="No id", plain="x", message_id=None)
    )
    other = mailbox.parse_message(
        build_message(sender=SENDER, subject="Different", plain="x", message_id=None)
    )

    assert first["message_id"].startswith("sha1:")
    assert first["message_id"] == again["message_id"]
    assert first["message_id"] != other["message_id"]


def test_parse_message_extracts_address_and_iso_date():
    parsed = mailbox.parse_message(
        build_message(sender="Citadel <No-Reply@Citadel.com>", subject="x", plain="x")
    )

    assert parsed["from_address"] == "no-reply@citadel.com"
    assert parsed["received"] == "2026-09-02"


def test_parse_message_tolerates_a_bad_date():
    raw = build_message(sender=SENDER, subject="x", plain="x")
    raw = re.sub(rb"(?m)^Date: .*$", b"Date: not a real date", raw)

    assert mailbox.parse_message(raw)["received"] is None


def test_imap_since_uses_english_months():
    assert mailbox.imap_since(datetime.date(2026, 8, 14)) == "14-Aug-2026"
    assert mailbox.imap_since(datetime.date(2026, 1, 3)) == "03-Jan-2026"


def test_imap_since_ignores_the_process_locale():
    """strftime('%b') is locale-dependent: on a Turkish locale it yields 'Ağu',
    which an IMAP server rejects. imap_since must not depend on it."""
    saved = locale.setlocale(locale.LC_TIME)
    for candidate in ("tr_TR.UTF-8", "tr_TR.utf8", "tr_TR"):
        try:
            locale.setlocale(locale.LC_TIME, candidate)
            break
        except locale.Error:
            continue
    else:
        pytest.skip("no Turkish locale installed")
    try:
        day = datetime.date(2026, 8, 14)
        assert day.strftime("%b") != "Aug"  # proves the locale really is non-English
        assert mailbox.imap_since(day) == "14-Aug-2026"
    finally:
        locale.setlocale(locale.LC_TIME, saved)
