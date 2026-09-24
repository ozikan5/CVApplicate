from __future__ import annotations

import datetime
import locale
import re
import ssl

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


import imaplib
import socket

from tests.mail_fixtures import build_message as _build

ALL_MAIL_LIST = [
    b'(\\HasNoChildren) "/" "INBOX"',
    b'(\\HasNoChildren \\All) "/" "[Gmail]/All Mail"',
]


class RecordingIMAP:
    """Records every command. Anything not explicitly implemented is a command
    that could change the mailbox, so __getattr__ turns it into a test failure."""

    def __init__(self, list_lines, messages):
        self.calls = []
        self._list = list_lines
        self._messages = messages  # {"1": raw_bytes, ...}

    def list(self, *args):
        self.calls.append(("list", args, {}))
        return "OK", self._list

    def select(self, mailbox="INBOX", readonly=False):
        self.calls.append(("select", (mailbox,), {"readonly": readonly}))
        return "OK", [str(len(self._messages)).encode()]

    def search(self, charset, *criteria):
        self.calls.append(("search", criteria, {}))
        return "OK", [" ".join(self._messages).encode()]

    def fetch(self, message_set, spec):
        self.calls.append(("fetch", (message_set, spec), {}))
        data = []
        for seq in message_set.split(","):
            raw = self._messages[seq]
            if "HEADER.FIELDS" in spec:
                raw = re.split(rb"\r?\n\r?\n", raw, maxsplit=1)[0] + b"\r\n\r\n"
            data.append((f"{seq} (BODY[] {{{len(raw)}}}".encode(), raw))
            data.append(b")")
        return "OK", data

    def logout(self):
        self.calls.append(("logout", (), {}))
        return "BYE", []

    def __getattr__(self, name):
        raise AssertionError(f"forbidden IMAP command issued: {name}")


def _two_messages():
    return {
        "1": _build(sender="Citadel <no-reply@citadel.com>", subject="Update",
                    plain="Unfortunately, we will not be moving forward.",
                    message_id="<a@citadel.com>"),
        "2": _build(sender="HackerRank <support@hackerrank.com>", subject="Assessment",
                    plain="Your assessment is ready.", message_id="<b@hackerrank.com>"),
    }


def test_the_mailbox_is_only_ever_read():
    """The most important test in this file."""
    conn = RecordingIMAP(ALL_MAIL_LIST, _two_messages())

    mailbox.open_folder(conn)
    seqs = mailbox.search_since(conn, datetime.date(2026, 8, 14))
    mailbox.fetch_parsed(conn, seqs, mailbox.HEADERS_SPEC)
    mailbox.fetch_parsed(conn, seqs, mailbox.FULL_SPEC)

    selects = [c for c in conn.calls if c[0] == "select"]
    assert selects and all(c[2]["readonly"] is True for c in selects)
    fetches = [c for c in conn.calls if c[0] == "fetch"]
    assert fetches and all("PEEK" in c[1][1] for c in fetches)
    assert {c[0] for c in conn.calls} <= {"list", "select", "search", "fetch"}


def test_the_recording_fake_really_catches_a_write():
    """Guards the guard: if __getattr__ stopped raising, the test above would pass
    against code that stores flags."""
    conn = RecordingIMAP(ALL_MAIL_LIST, _two_messages())

    with pytest.raises(AssertionError):
        conn.store("1", "+FLAGS", "\\Seen")


def test_both_fetch_specs_peek():
    assert "PEEK" in mailbox.HEADERS_SPEC
    assert "PEEK" in mailbox.FULL_SPEC


def test_find_all_mail_folder_uses_the_all_flag():
    conn = RecordingIMAP(ALL_MAIL_LIST, {})

    assert mailbox.find_all_mail_folder(conn) == '"[Gmail]/All Mail"'


def test_find_all_mail_folder_handles_a_localized_name():
    """Gmail localizes folder names, in modified UTF-7. Resolving by the \\All
    flag and passing the raw name back means the name never has to be decoded."""
    localized = [b'(\\HasNoChildren \\All) "/" "[Gmail]/T&APw-m Postalar"']
    conn = RecordingIMAP(localized, {})

    folder, warnings = mailbox.open_folder(conn)

    assert folder == '"[Gmail]/T&APw-m Postalar"'
    assert warnings == []
    assert conn.calls[-1][1] == ('"[Gmail]/T&APw-m Postalar"',)


def test_open_folder_falls_back_to_inbox_with_a_warning():
    conn = RecordingIMAP([b'(\\HasNoChildren) "/" "INBOX"'], {})

    folder, warnings = mailbox.open_folder(conn)

    assert folder == "INBOX"
    assert warnings and "INBOX" in warnings[0]


def test_search_since_sends_an_english_date():
    conn = RecordingIMAP(ALL_MAIL_LIST, _two_messages())

    seqs = mailbox.search_since(conn, datetime.date(2026, 8, 14))

    assert seqs == ["1", "2"]
    assert conn.calls[-1][1] == ("SINCE", "14-Aug-2026")


def test_fetch_parsed_survives_an_unparseable_message(monkeypatch):
    """A message the parser chokes on must never crash the run. It comes back
    marked, with no sender address, so the prefilter can never pass it on."""
    conn = RecordingIMAP(ALL_MAIL_LIST, _two_messages())

    def boom(raw):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr(mailbox, "parse_message", boom)

    results = mailbox.fetch_parsed(conn, ["1"], mailbox.FULL_SPEC)

    assert results[0]["message_id"].startswith("unparseable:")
    assert results[0]["unparseable"] == "UnicodeDecodeError"
    assert results[0]["from_address"] == ""


def test_fetch_parsed_returns_parsed_messages_with_sequence_numbers():
    conn = RecordingIMAP(ALL_MAIL_LIST, _two_messages())

    headers = mailbox.fetch_parsed(conn, ["1", "2"], mailbox.HEADERS_SPEC)
    full = mailbox.fetch_parsed(conn, ["1"], mailbox.FULL_SPEC)

    assert [h["seq"] for h in headers] == ["1", "2"]
    assert headers[0]["message_id"] == "<a@citadel.com>"
    assert headers[0]["body"] == ""
    assert full[0]["body"] == "Unfortunately, we will not be moving forward."


class _FakeSSL:
    def __init__(self, *args, **kwargs):
        pass

    def login(self, user, password):
        raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")


def test_connect_maps_an_auth_failure_without_leaking_the_password(monkeypatch):
    monkeypatch.setattr(mailbox.imaplib, "IMAP4_SSL", _FakeSSL)

    with pytest.raises(mailbox.MailboxError) as excinfo:
        mailbox.connect("imap.gmail.com", "me@gmail.com", "s3cr3t-p4ss-XYZ")

    assert "Enable IMAP" in str(excinfo.value)
    assert "s3cr3t-p4ss-XYZ" not in str(excinfo.value)
    assert excinfo.value.exit_code == 2


def test_connect_maps_a_socket_timeout(monkeypatch):
    """On Python 3.9 socket.timeout is not a TimeoutError subclass — the defect
    that was Phase A's Critical. Catch it explicitly."""
    def boom(*args, **kwargs):
        raise socket.timeout("timed out")

    monkeypatch.setattr(mailbox.imaplib, "IMAP4_SSL", boom)

    with pytest.raises(mailbox.MailboxUnavailable) as excinfo:
        mailbox.connect("imap.gmail.com", "me@gmail.com", "pw")

    assert excinfo.value.exit_code == 4


def test_connect_maps_a_refused_connection(monkeypatch):
    def boom(*args, **kwargs):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(mailbox.imaplib, "IMAP4_SSL", boom)

    with pytest.raises(mailbox.MailboxUnavailable):
        mailbox.connect("imap.gmail.com", "me@gmail.com", "pw")


class _FakeSSLRecordingContext:
    """Records the ssl_context kwarg IMAP4_SSL was constructed with."""

    def __init__(self, *args, **kwargs):
        self.received_ssl_context = kwargs.get("ssl_context")
        _FakeSSLRecordingContext.last_instance = self

    def login(self, user, password):
        return "OK", [b"success"]


def test_connect_verifies_tls_certificates(monkeypatch):
    """imaplib.IMAP4_SSL with no ssl_context falls back to an UNVERIFIED
    context on every Python version. connect() must pass a verifying one
    explicitly, or a hostile network can intercept the app password."""
    monkeypatch.setattr(mailbox.imaplib, "IMAP4_SSL", _FakeSSLRecordingContext)

    mailbox.connect("imap.gmail.com", "me@gmail.com", "pw")

    context = _FakeSSLRecordingContext.last_instance.received_ssl_context
    assert context is not None
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
