# Postman Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read recruiting mail nightly and propose application outcomes, which the user confirms in one interactive pass before anything is written to `applications/log.yaml`.

**Architecture:** `job_fetcher/mailbox.py` is the only code that touches IMAP and is read-only by construction. `job_fetcher/outcomes.py` holds the deterministic rules — prefilter, company matching, stage ordering. Two new `pipeline.py` subcommands expose them to skills: `mail` fetches and narrows candidates, `review` annotates proposals for confirmation. An unattended skill writes proposals; an interactive skill confirms them and makes the only commit.

**Tech Stack:** Python 3 standard library (`imaplib`, `email`, `socket`, `subprocess`) plus PyYAML, pytest. No new third-party dependencies.

## Global Constraints

- **Python 3.9 compatible.** `from __future__ import annotations` in every module; no `match`; no `X | Y` unions outside annotations. Every task runs both `.venv/bin/python -m pytest -q` (3.14.6) and `.venv39/bin/python -m pytest -q` (3.9.6).
- **No new dependencies.** `requirements.txt` stays `PyYAML>=6.0` and `pytest>=7.0`.
- **No network and no real mail in tests.** No test may read the repository's real `.env`, `postings.local.yaml`, `outcomes.pending.yaml` or `applications/log.yaml`. Point every path constant at `tmp_path`.
- **The mailbox is read-only by construction.** Open folders only with `select(folder, readonly=True)`; every `FETCH` uses `BODY.PEEK[…]`; never issue `STORE`, `COPY`, `MOVE`, `EXPUNGE`, `APPEND`, `DELETE`, `CREATE`, `RENAME` or `UID`.
- **The app password never appears in stdout, stderr, or an exception message.**
- **The unattended runner cannot write history or the log.** `postman.sh` grants no git write and no `Edit` on `applications/log.yaml`.
- **stdout is machine-readable JSON only**; human messages go to stderr. Use `json.dumps(..., default=str)` wherever YAML-loaded dates may appear.
- **Commits are authored `ozikan5 <ozankan32@gmail.com>` with NO `Co-Authored-By` trailer of any kind.** Check `git config user.name` before committing. This is the repository owner's explicit rule and overrides any default attribution.
- **Shell:** the user's shell is zsh. Write `"${var}:path"`, never `"$var:path"` — zsh's `:c` modifier eats the variable.
- **Reference spec:** `docs/superpowers/specs/2026-09-24-postman-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `job_fetcher/mailbox.py` | **New.** Message parsing, the locale-safe IMAP date, and read-only IMAP access |
| `job_fetcher/outcomes.py` | **New.** Company aliases, the prefilter, stage ordering, default answers, pending-file reading |
| `pipeline.py` | Modify: `mail` and `review` subcommands |
| `tests/mail_fixtures.py` | **New.** Builds structurally genuine test messages with the `email` library |
| `tests/test_mailbox.py`, `tests/test_outcomes.py` | **New.** |
| `tests/test_pipeline.py` | Modify: `mail` and `review` tests |
| `plugins/cvapplicate/skills/cv-check-mail/SKILL.md` | **New.** Unattended: classify candidates, write proposals |
| `plugins/cvapplicate/skills/cv-review-outcomes/SKILL.md` | **New.** Interactive: confirm proposals, commit |
| `plugins/cvapplicate/skills/cv-log-outcome/SKILL.md` | Modify: accept `assessment` |
| `postman.sh`, `launchd/com.cvapplicate.postman.plist.example` | **New.** Runner and schedule |
| `.gitignore`, `.env.example`, `README.md` | Modify |

`mailbox.py` knows nothing about applications; `outcomes.py` knows nothing about IMAP. Each is testable without the other, and only `pipeline.py` joins them.

---

### Task 1: Message parsing and the locale-safe IMAP date

**Files:**
- Create: `job_fetcher/mailbox.py`, `tests/mail_fixtures.py`, `tests/test_mailbox.py`

**Interfaces:**
- Consumes: `strip_html` from `job_fetcher.htmltext`.
- Produces: `BODY_LIMIT = 1500`; `parse_message(raw: bytes) -> dict` with keys `message_id`, `from`, `from_address`, `received` (ISO date string or `None`), `subject`, `body`; `imap_since(day: datetime.date) -> str`; and in `tests/mail_fixtures.py`, `build_message(...) -> bytes`, `build_q_encoded_subject() -> bytes`, `DEFAULT_DATE`.

- [ ] **Step 1: Create the fixture builders**

Create `tests/mail_fixtures.py`. Building messages through the standard library, instead of hand-writing `.eml` text, guarantees they are messages a real client could have produced:

```python
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
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_mailbox.py`:

```python
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_mailbox.py -q`
Expected: FAIL — `ImportError: cannot import name 'mailbox' from 'job_fetcher'`

- [ ] **Step 4: Write the implementation**

Create `job_fetcher/mailbox.py`:

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_mailbox.py -q`
Expected: 13 passed (or 12 passed, 1 skipped if no Turkish locale is installed — on macOS it is)

- [ ] **Step 6: Run both suites and commit**

Run: `.venv/bin/python -m pytest -q` then `.venv39/bin/python -m pytest -q`
Expected: 218 passed in both (205 + 13)

```bash
git add job_fetcher/mailbox.py tests/mail_fixtures.py tests/test_mailbox.py
git commit -m "Add mail parsing and a locale-safe IMAP date"
```

---

### Task 2: Read-only IMAP access

**Files:**
- Modify: `job_fetcher/mailbox.py`, `tests/test_mailbox.py`

**Interfaces:**
- Consumes: `parse_message`, `imap_since` (Task 1).
- Produces: `HEADERS_SPEC`, `FULL_SPEC`, `FETCH_BATCH = 200`; `MailboxError` (`exit_code = 2`), `MailboxUnavailable` (`exit_code = 4`); `find_all_mail_folder(conn) -> str | None`; `open_folder(conn) -> tuple[str, list[str]]` returning `(folder, warnings)`; `search_since(conn, day) -> list[str]` of sequence numbers; `fetch_parsed(conn, seqs, spec) -> list[dict]` (each dict is `parse_message`'s output plus `"seq"`); `connect(host, user, password)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mailbox.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_mailbox.py -q`
Expected: FAIL — `AttributeError: module 'job_fetcher.mailbox' has no attribute 'open_folder'`

- [ ] **Step 3: Write the implementation**

In `job_fetcher/mailbox.py`, add `import imaplib`, `import re` and `import socket` to the imports, then append:

```python
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
        conn = imaplib.IMAP4_SSL(host, timeout=30)
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
```

`from None` suppresses the chained exception, so no library message can carry anything sensitive into a traceback.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_mailbox.py -q`
Expected: 25 passed (13 from Task 1 + 12 new; one may skip without a Turkish locale)

- [ ] **Step 5: Run both suites and commit**

Run: `.venv/bin/python -m pytest -q` then `.venv39/bin/python -m pytest -q`
Expected: 230 passed in both

```bash
git add job_fetcher/mailbox.py tests/test_mailbox.py
git commit -m "Add read-only IMAP access, enforced by a recording fake"
```

---

### Task 3: Company aliases and the prefilter

**Files:**
- Create: `job_fetcher/outcomes.py`, `tests/test_outcomes.py`

**Interfaces:**
- Produces: `ATS_DOMAINS`, `ASSESSMENT_DOMAINS`; `sender_domain(address: str) -> str`; `company_aliases(company: str) -> list[str]`; `candidate_applications(message: dict, applications: list[dict]) -> list[str]` returning application ids; `is_candidate(message: dict, applications: list[dict]) -> bool`. An application dict has at least `id` and `company`; a message dict has at least `from`, `from_address`, `subject`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_outcomes.py`:

```python
from __future__ import annotations

from job_fetcher import outcomes

APPLICATIONS = [
    {"id": "ctc-swe-2026-08", "company": "Chicago Trading Company (CTC)"},
    {"id": "hrt-swe-2026-08", "company": "Hudson River Trading (HRT)"},
    {"id": "janestreet-a", "company": "Jane Street"},
    {"id": "janestreet-b", "company": "Jane Street"},
    {"id": "microsoft-a", "company": "Microsoft"},
    {"id": "microsoft-b", "company": "Microsoft"},
    {"id": "microsoft-c", "company": "Microsoft"},
    {"id": "citadel-swe-2026-08", "company": "Citadel"},
]


def _message(sender, subject=""):
    address = sender.split("<")[-1].rstrip(">").strip().lower()
    return {"from": sender, "from_address": address, "subject": subject}


def test_company_aliases_splits_a_parenthesized_acronym():
    assert outcomes.company_aliases("Chicago Trading Company (CTC)") == [
        "chicago trading company", "chicagotradingcompany", "ctc",
    ]


def test_company_aliases_for_a_single_word():
    assert outcomes.company_aliases("Microsoft") == ["microsoft"]


def test_sender_domain():
    assert outcomes.sender_domain("no-reply@mail.citadel.com") == "mail.citadel.com"
    assert outcomes.sender_domain("not-an-address") == ""


def test_an_ats_subdomain_is_a_candidate():
    msg = _message("Greenhouse <no-reply@us.greenhouse-mail.io>", "Application update")

    assert outcomes.is_candidate(msg, APPLICATIONS)


def test_an_assessment_platform_is_a_candidate_even_without_a_company_name():
    msg = _message("HackerRank <support@hackerrank.com>", "Your assessment is ready")

    assert outcomes.is_candidate(msg, APPLICATIONS)
    assert outcomes.candidate_applications(msg, APPLICATIONS) == []


def test_a_whole_word_acronym_in_the_subject_matches():
    msg = _message("Recruiting <jobs@example.com>", "Your CTC application")

    assert outcomes.candidate_applications(msg, APPLICATIONS) == ["ctc-swe-2026-08"]


def test_an_acronym_inside_another_word_does_not_match():
    """Short aliases are the risk: 'ctc' must not match 'ctcarrier.com'."""
    msg = _message("CT Carrier <news@ctcarrier.com>", "Shipping update")

    assert not outcomes.is_candidate(msg, APPLICATIONS)


def test_a_company_with_three_applications_yields_all_three():
    msg = _message("Microsoft <no-reply@microsoft.com>", "Thank you for applying")

    assert outcomes.candidate_applications(msg, APPLICATIONS) == [
        "microsoft-a", "microsoft-b", "microsoft-c",
    ]


def test_a_compacted_name_matches_a_domain():
    """Company domains are usually the name without spaces."""
    msg = _message("recruiting@janestreet.com", "Next steps")

    assert outcomes.candidate_applications(msg, APPLICATIONS) == [
        "janestreet-a", "janestreet-b",
    ]


def test_a_display_name_matches():
    msg = _message("Hudson River Trading <jobs@example.org>", "Update")

    assert outcomes.candidate_applications(msg, APPLICATIONS) == ["hrt-swe-2026-08"]


def test_unrelated_mail_is_not_a_candidate():
    msg = _message("A Friend <friend@gmail.com>", "dinner on friday?")

    assert not outcomes.is_candidate(msg, APPLICATIONS)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_outcomes.py -q`
Expected: FAIL — `ImportError: cannot import name 'outcomes'`

- [ ] **Step 3: Write the implementation**

Create `job_fetcher/outcomes.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_outcomes.py -q`
Expected: 11 passed

- [ ] **Step 5: Run both suites and commit**

Run: `.venv/bin/python -m pytest -q` then `.venv39/bin/python -m pytest -q`
Expected: 241 passed in both

```bash
git add job_fetcher/outcomes.py tests/test_outcomes.py
git commit -m "Add company matching and the recruiting-mail prefilter"
```

---

### Task 4: Stage ordering, default answers and the pending file

**Files:**
- Modify: `job_fetcher/outcomes.py`, `tests/test_outcomes.py`

**Interfaces:**
- Produces: `STAGES = ("pending", "assessment", "interview", "offer")`; `PROPOSABLE = ("assessment", "interview", "offer", "rejected")`; `regresses(current: str, proposed: str) -> bool`; `default_answer(proposal: dict, current: str) -> bool`; `load_pending(path: str) -> dict` returning `{"seen": [...], "proposals": [...]}`; `seen_ids(pending: dict) -> set`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_outcomes.py`:

```python
import pytest


@pytest.mark.parametrize("current,proposed,expected", [
    ("pending", "assessment", False),
    ("assessment", "interview", False),
    ("interview", "offer", False),
    ("interview", "assessment", True),   # an old OA email after an interview
    ("offer", "interview", True),
    ("pending", "rejected", False),      # rejected is reachable from anything
    ("interview", "rejected", False),
    ("rejected", "interview", True),     # a positive after a rejection needs a human
    ("no_response", "interview", False), # they replied late
    ("interview", "interview", False),
])
def test_regresses(current, proposed, expected):
    assert outcomes.regresses(current, proposed) is expected


def _proposal(**overrides):
    proposal = {"proposed_outcome": "rejected", "application_id": "citadel-swe-2026-08",
                "confidence": "high"}
    proposal.update(overrides)
    return proposal


def test_default_answer_is_yes_only_for_a_clear_single_match():
    assert outcomes.default_answer(_proposal(), "pending") is True


def test_default_answer_is_no_for_low_confidence():
    assert outcomes.default_answer(_proposal(confidence="medium"), "pending") is False


def test_default_answer_is_no_when_ambiguous():
    assert outcomes.default_answer(_proposal(application_id=None), "pending") is False


def test_default_answer_is_no_for_a_regression():
    assert outcomes.default_answer(
        _proposal(proposed_outcome="assessment"), "interview"
    ) is False


def test_load_pending_returns_empty_state_for_a_missing_file(tmp_path):
    assert outcomes.load_pending(str(tmp_path / "absent.yaml")) == {
        "seen": [], "proposals": [],
    }


def test_load_pending_and_seen_ids(tmp_path):
    path = tmp_path / "outcomes.pending.yaml"
    path.write_text(
        "seen:\n  - '<a@x.com>'\nproposals:\n  - message_id: '<a@x.com>'\n"
        "    proposed_outcome: rejected\n",
        encoding="utf-8",
    )

    pending = outcomes.load_pending(str(path))

    assert outcomes.seen_ids(pending) == {"<a@x.com>"}
    assert pending["proposals"][0]["proposed_outcome"] == "rejected"


def test_load_pending_rejects_a_malformed_file(tmp_path):
    path = tmp_path / "outcomes.pending.yaml"
    path.write_text("- not\n- a mapping\n", encoding="utf-8")

    with pytest.raises(ValueError):
        outcomes.load_pending(str(path))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_outcomes.py -q`
Expected: FAIL — `AttributeError: module 'job_fetcher.outcomes' has no attribute 'regresses'`

- [ ] **Step 3: Write the implementation**

In `job_fetcher/outcomes.py`, add `import os` and `import yaml` to the imports, then append:

```python
STAGES = ("pending", "assessment", "interview", "offer")
PROPOSABLE = ("assessment", "interview", "offer", "rejected")


def regresses(current: str, proposed: str) -> bool:
    """True when applying `proposed` would move an application backward.

    Stages only move forward. `rejected` may follow any stage. A positive stage
    after `rejected` needs a human. `no_response` may be followed by anything,
    since a late reply is progress.
    """
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
    return (
        proposal.get("confidence") == "high"
        and proposal.get("application_id") is not None
        and not regresses(current, proposal.get("proposed_outcome", ""))
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
    return {"seen": list(data.get("seen") or []), "proposals": list(data.get("proposals") or [])}


def seen_ids(pending: dict) -> set:
    return set(pending.get("seen") or [])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_outcomes.py -q`
Expected: 28 passed (11 + 10 parametrized + 7)

- [ ] **Step 5: Run both suites and commit**

Run: `.venv/bin/python -m pytest -q` then `.venv39/bin/python -m pytest -q`
Expected: 258 passed in both

```bash
git add job_fetcher/outcomes.py tests/test_outcomes.py
git commit -m "Add stage ordering, default answers and pending-file reading"
```

---

### Task 5: `pipeline.py mail`

**Files:**
- Modify: `pipeline.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything in `job_fetcher.mailbox` (Tasks 1-2) and `job_fetcher.outcomes` (Tasks 3-4); `load_dotenv` from `job_fetcher.env`.
- Produces: `pipeline.py mail`, printing JSON `{"folder", "since", "warnings", "applications", "candidates", "remaining"}`. Each candidate has `message_id`, `from`, `received`, `subject`, `body`, `candidate_ids`. Also module attributes `LOG_REF`, `PENDING_PATH`, `ENV_PATH`, `MAIL_CANDIDATE_LIMIT = 200`, `DEFAULT_IMAP_HOST`, `_read_log_text()`, `_load_applications()`, and `_connect` (bound to `mailbox.connect`, patched in tests).

Two design points the spec left implicit, fixed here:
- **Headers first, bodies second.** A search since the earliest application matches every email received since then. Fetch headers for all of them, prefilter on headers, then fetch full bodies only for candidates.
- **The log is read from `main`**, via `git show main:applications/log.yaml`. The file is deliberately absent from industry branches, so reading it as a path would fail whenever the user has `swe` checked out.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pipeline.py`:

```python
import imaplib
import re as _re

import pytest

from job_fetcher import mailbox
from tests.mail_fixtures import build_message

LOG_YAML = """
- id: citadel-swe-2026-08
  company: "Citadel"
  role: "Software Engineering Intern"
  date_applied: 2026-08-19
  outcome: pending
- id: microsoft-a
  company: "Microsoft"
  role: "SWE Intern, AI/ML"
  date_applied: 2026-08-24
  outcome: pending
"""

PASSWORD = "s3cr3t-p4ss-XYZ"


class FakeIMAP:
    def __init__(self, messages, list_lines=None):
        self.messages = messages
        self.list_lines = list_lines or [b'(\\HasNoChildren \\All) "/" "[Gmail]/All Mail"']
        self.logged_out = False

    def list(self, *args):
        return "OK", self.list_lines

    def select(self, mailbox="INBOX", readonly=False):
        assert readonly is True
        return "OK", [b"1"]

    def search(self, charset, *criteria):
        return "OK", [" ".join(self.messages).encode()]

    def fetch(self, message_set, spec):
        assert "PEEK" in spec
        data = []
        for seq in message_set.split(","):
            raw = self.messages[seq]
            if "HEADER.FIELDS" in spec:
                raw = _re.split(rb"\r?\n\r?\n", raw, maxsplit=1)[0] + b"\r\n\r\n"
            data.append((f"{seq} (BODY[] {{{len(raw)}}}".encode(), raw))
            data.append(b")")
        return "OK", data

    def logout(self):
        self.logged_out = True
        return "BYE", []

    def __getattr__(self, name):
        raise AssertionError(f"forbidden IMAP command issued: {name}")


def _mail_project(tmp_path, monkeypatch, messages=None, log_yaml=LOG_YAML):
    _chdir_project(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "PENDING_PATH", str(tmp_path / "outcomes.pending.yaml"))
    monkeypatch.setattr(cli, "ENV_PATH", str(tmp_path / "absent.env"))
    monkeypatch.setattr(cli, "_read_log_text", lambda: log_yaml)
    monkeypatch.setenv("SMTP_USER", "me@gmail.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", PASSWORD)
    fake = FakeIMAP(messages or {})
    monkeypatch.setattr(cli, "_connect", lambda host, user, password: fake)
    return fake


def _three_messages():
    return {
        "1": build_message(sender="Citadel <no-reply@citadel.com>", subject="Your application",
                           plain="Unfortunately, we will not be moving forward.",
                           message_id="<rej@citadel.com>"),
        "2": build_message(sender="A Friend <friend@example.org>", subject="dinner?",
                           plain="Friday?", message_id="<friend@example.org>"),
        "3": build_message(sender="Me <me@gmail.com>", subject="Citadel follow-up",
                           plain="note to self", message_id="<self@gmail.com>"),
    }


def test_mail_returns_only_recruiting_candidates(tmp_path, monkeypatch, capsys):
    fake = _mail_project(tmp_path, monkeypatch, _three_messages())

    exit_code = cli.main(["pipeline.py", "mail"])

    out = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert out["folder"] == '"[Gmail]/All Mail"'
    assert out["since"] == "2026-08-19"
    assert [c["message_id"] for c in out["candidates"]] == ["<rej@citadel.com>"]
    assert out["candidates"][0]["candidate_ids"] == ["citadel-swe-2026-08"]
    assert "not be moving forward" in out["candidates"][0]["body"]
    assert out["remaining"] == 0
    assert fake.logged_out


def test_mail_skips_already_seen_messages(tmp_path, monkeypatch, capsys):
    _mail_project(tmp_path, monkeypatch, _three_messages())
    (tmp_path / "outcomes.pending.yaml").write_text(
        "seen:\n  - '<rej@citadel.com>'\nproposals: []\n", encoding="utf-8"
    )

    cli.main(["pipeline.py", "mail"])

    assert json.loads(capsys.readouterr().out)["candidates"] == []


def test_mail_caps_candidates_and_reports_the_remainder(tmp_path, monkeypatch, capsys):
    messages = {
        "1": build_message(sender="Citadel <a@citadel.com>", subject="One", plain="x",
                           message_id="<1@citadel.com>"),
        "2": build_message(sender="Citadel <b@citadel.com>", subject="Two", plain="x",
                           message_id="<2@citadel.com>"),
    }
    _mail_project(tmp_path, monkeypatch, messages)
    monkeypatch.setattr(cli, "MAIL_CANDIDATE_LIMIT", 1)

    cli.main(["pipeline.py", "mail"])

    out = json.loads(capsys.readouterr().out)
    assert len(out["candidates"]) == 1
    assert out["remaining"] == 1


def test_mail_never_prints_the_password_on_success(tmp_path, monkeypatch, capsys):
    _mail_project(tmp_path, monkeypatch, _three_messages())

    cli.main(["pipeline.py", "mail"])

    captured = capsys.readouterr()
    assert PASSWORD not in captured.out
    assert PASSWORD not in captured.err


class _AuthFailSSL:
    def __init__(self, *args, **kwargs):
        pass

    def login(self, user, password):
        raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")


def test_mail_auth_failure_exits_2_without_leaking_the_password(tmp_path, monkeypatch, capsys):
    _mail_project(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "_connect", mailbox.connect)
    monkeypatch.setattr(mailbox.imaplib, "IMAP4_SSL", _AuthFailSSL)

    exit_code = cli.main(["pipeline.py", "mail"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "Enable IMAP" in captured.err
    assert PASSWORD not in captured.err


def test_mail_network_failure_exits_4(tmp_path, monkeypatch, capsys):
    _mail_project(tmp_path, monkeypatch)

    def unreachable(host, user, password):
        raise mailbox.MailboxUnavailable("could not reach imap.gmail.com: timeout")

    monkeypatch.setattr(cli, "_connect", unreachable)

    assert cli.main(["pipeline.py", "mail"]) == 4
    assert capsys.readouterr().out == ""


def test_mail_missing_credentials_exits_2(tmp_path, monkeypatch, capsys):
    _mail_project(tmp_path, monkeypatch)
    monkeypatch.delenv("SMTP_APP_PASSWORD")

    assert cli.main(["pipeline.py", "mail"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "SMTP_APP_PASSWORD" in captured.err


def test_mail_unreadable_log_exits_2(tmp_path, monkeypatch, capsys):
    _mail_project(tmp_path, monkeypatch)

    def no_log():
        raise FileNotFoundError("main:applications/log.yaml not found")

    monkeypatch.setattr(cli, "_read_log_text", no_log)

    assert cli.main(["pipeline.py", "mail"]) == 2
    assert capsys.readouterr().out == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -q`
Expected: FAIL — `AttributeError: module 'pipeline' has no attribute 'PENDING_PATH'`

- [ ] **Step 3: Write the implementation**

In `pipeline.py`:

(a) Extend the imports:

```python
import datetime
import subprocess

from job_fetcher import mailbox, outcomes
from job_fetcher.env import load_dotenv
```

(b) Add below `OUTBOX_PATH`:

```python
LOG_REF = "main:applications/log.yaml"
PENDING_PATH = "outcomes.pending.yaml"
ENV_PATH = ".env"
MAIL_CANDIDATE_LIMIT = 200
DEFAULT_IMAP_HOST = "imap.gmail.com"

_connect = mailbox.connect
```

(c) Add these functions above `main`:

```python
def _read_log_text() -> str:
    """Read the application log from main.

    applications/log.yaml is tracked on main only and deliberately absent from
    industry branches, so reading it as a path would fail whenever an industry
    branch is checked out.
    """
    result = subprocess.run(["git", "show", LOG_REF], capture_output=True, text=True)
    if result.returncode != 0:
        raise FileNotFoundError(f"{LOG_REF} not found: {result.stderr.strip()}")
    return result.stdout


def _load_applications() -> list:
    entries = yaml.safe_load(_read_log_text()) or []
    applications = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id"):
            applications.append({
                "id": entry["id"],
                "company": entry.get("company", ""),
                "role": entry.get("role", ""),
                "outcome": entry.get("outcome") or "pending",
                "date_applied": entry.get("date_applied"),
            })
    return applications


def _as_date(value):
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value))


def mail_mode() -> int:
    load_dotenv(ENV_PATH)
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_APP_PASSWORD")
    if not user or not password:
        print("error: SMTP_USER and SMTP_APP_PASSWORD must be set in .env", file=sys.stderr)
        return 2
    host = os.environ.get("IMAP_HOST") or DEFAULT_IMAP_HOST

    try:
        applications = _load_applications()
        pending = outcomes.load_pending(PENDING_PATH)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    dated = [a for a in applications if a.get("date_applied")]
    if not dated:
        print(json.dumps({"folder": None, "since": None, "warnings": [],
                          "applications": [], "candidates": [], "remaining": 0}))
        return 0
    since = min(_as_date(a["date_applied"]) for a in dated)
    seen = outcomes.seen_ids(pending)

    conn = None
    try:
        conn = _connect(host, user, password)
        folder, warnings = mailbox.open_folder(conn)
        seqs = mailbox.search_since(conn, since)
        headers = mailbox.fetch_parsed(conn, seqs, mailbox.HEADERS_SPEC)
        own = user.lower()
        fresh = [h for h in headers
                 if h.get("from_address") != own and h["message_id"] not in seen]
        matched = [h for h in fresh if outcomes.is_candidate(h, applications)]
        selected = matched[:MAIL_CANDIDATE_LIMIT]
        bodies = {}
        if selected:
            for full in mailbox.fetch_parsed(conn, [h["seq"] for h in selected],
                                             mailbox.FULL_SPEC):
                bodies[full["seq"]] = full
    except mailbox.MailboxError as error:
        print(f"error: {error}", file=sys.stderr)
        return error.exit_code
    except mailbox.MailboxUnavailable as error:
        print(f"error: {error}", file=sys.stderr)
        return error.exit_code
    finally:
        if conn is not None:
            try:
                conn.logout()
            except Exception:
                pass

    candidates = []
    for header in selected:
        full = bodies.get(header["seq"], header)
        candidates.append({
            "message_id": header["message_id"],
            "from": header["from"],
            "received": header["received"],
            "subject": header["subject"],
            "body": full.get("body", ""),
            "candidate_ids": outcomes.candidate_applications(header, applications),
        })

    print(json.dumps({
        "folder": folder,
        "since": since.isoformat(),
        "warnings": warnings,
        "applications": [{k: a[k] for k in ("id", "company", "role", "outcome")}
                         for a in applications],
        "candidates": candidates,
        "remaining": len(matched) - len(selected),
    }, default=str))
    return 0
```

(d) Route it in `main`, before the usage fallback:

```python
    if len(arguments) == 1 and arguments[0] == "mail":
        return mail_mode()
```

(e) Add `       pipeline.py mail\n` to `USAGE`. In the module docstring, add `    ./pipeline.py mail` to the Usage block, add this paragraph after the `packet-path` one:

```
mail         Reads recruiting mail since the earliest logged application,
             read-only (EXAMINE, BODY.PEEK), and prints the candidates that
             pass the prefilter as JSON: folder, since, warnings, applications,
             candidates, remaining. Credentials come from .env and are never
             printed.
```

and change the exit-code line to: `Exit codes: 0 = success, 2 = usage, invalid posting id, missing credentials or an unreadable log, 4 = posting id not found, or the mail server unreachable.`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -q`
Expected: all pass, 8 new

- [ ] **Step 5: Run both suites and commit**

Run: `.venv/bin/python -m pytest -q` then `.venv39/bin/python -m pytest -q`
Expected: 266 passed in both

```bash
git add pipeline.py tests/test_pipeline.py
git commit -m "Add pipeline.py mail: read-only fetch of recruiting candidates"
```

---

### Task 6: `pipeline.py review`

**Files:**
- Modify: `pipeline.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `_load_applications`, `PENDING_PATH` (Task 5); `load_pending`, `regresses`, `default_answer` (Task 4).
- Produces: `pipeline.py review`, printing `{"proposals": [...]}` where each proposal is the pending entry plus `current_outcome`, `application_missing`, `regresses`, `default_answer`.

`regresses` and the default answer are deterministic rules, so they are computed here in tested Python rather than written into the pending file by the model.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pipeline.py`:

```python
def _review_project(tmp_path, monkeypatch, pending_yaml, log_yaml=LOG_YAML):
    _chdir_project(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "PENDING_PATH", str(tmp_path / "outcomes.pending.yaml"))
    monkeypatch.setattr(cli, "_read_log_text", lambda: log_yaml)
    (tmp_path / "outcomes.pending.yaml").write_text(pending_yaml, encoding="utf-8")


def test_review_annotates_a_clear_proposal(tmp_path, monkeypatch, capsys):
    _review_project(tmp_path, monkeypatch, """
seen: []
proposals:
  - message_id: "<rej@citadel.com>"
    received: 2026-09-02
    proposed_outcome: rejected
    application_id: citadel-swe-2026-08
    confidence: high
""")

    assert cli.main(["pipeline.py", "review"]) == 0

    proposal = json.loads(capsys.readouterr().out)["proposals"][0]
    assert proposal["current_outcome"] == "pending"
    assert proposal["regresses"] is False
    assert proposal["default_answer"] is True
    assert proposal["received"] == "2026-09-02"


def test_review_flags_a_regression(tmp_path, monkeypatch, capsys):
    log = LOG_YAML.replace("  outcome: pending\n- id: microsoft-a", "  outcome: interview\n- id: microsoft-a", 1)
    _review_project(tmp_path, monkeypatch, """
proposals:
  - message_id: "<oa@citadel.com>"
    proposed_outcome: assessment
    application_id: citadel-swe-2026-08
    confidence: high
""", log_yaml=log)

    cli.main(["pipeline.py", "review"])

    proposal = json.loads(capsys.readouterr().out)["proposals"][0]
    assert proposal["current_outcome"] == "interview"
    assert proposal["regresses"] is True
    assert proposal["default_answer"] is False


def test_review_defaults_an_ambiguous_proposal_to_no(tmp_path, monkeypatch, capsys):
    _review_project(tmp_path, monkeypatch, """
proposals:
  - message_id: "<m@microsoft.com>"
    proposed_outcome: rejected
    application_id: null
    candidates: [microsoft-a]
    confidence: high
""")

    cli.main(["pipeline.py", "review"])

    proposal = json.loads(capsys.readouterr().out)["proposals"][0]
    assert proposal["current_outcome"] is None
    assert proposal["default_answer"] is False


def test_review_marks_a_proposal_for_a_deleted_application(tmp_path, monkeypatch, capsys):
    _review_project(tmp_path, monkeypatch, """
proposals:
  - message_id: "<x@gone.com>"
    proposed_outcome: rejected
    application_id: no-longer-in-the-log
    confidence: high
""")

    cli.main(["pipeline.py", "review"])

    proposal = json.loads(capsys.readouterr().out)["proposals"][0]
    assert proposal["application_missing"] is True
    assert proposal["default_answer"] is False


def test_review_with_no_pending_file(tmp_path, monkeypatch, capsys):
    _chdir_project(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "PENDING_PATH", str(tmp_path / "absent.yaml"))
    monkeypatch.setattr(cli, "_read_log_text", lambda: LOG_YAML)

    assert cli.main(["pipeline.py", "review"]) == 0
    assert json.loads(capsys.readouterr().out) == {"proposals": []}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -q`
Expected: FAIL — `review` falls through to usage and exits 2

- [ ] **Step 3: Write the implementation**

Add above `main` in `pipeline.py`:

```python
def review_mode() -> int:
    try:
        pending = outcomes.load_pending(PENDING_PATH)
        applications = {a["id"]: a for a in _load_applications()}
    except (FileNotFoundError, ValueError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    annotated = []
    for proposal in pending["proposals"]:
        application_id = proposal.get("application_id")
        missing = application_id is not None and application_id not in applications
        current = applications[application_id]["outcome"] if application_id in applications else None
        proposed = proposal.get("proposed_outcome", "")
        annotated.append(dict(
            proposal,
            current_outcome=current,
            application_missing=missing,
            regresses=outcomes.regresses(current, proposed) if current else False,
            default_answer=(not missing) and current is not None
                           and outcomes.default_answer(proposal, current),
        ))
    print(json.dumps({"proposals": annotated}, default=str))
    return 0
```

Route it in `main` with `if len(arguments) == 1 and arguments[0] == "review": return review_mode()`, add `       pipeline.py review\n` to `USAGE`, add `    ./pipeline.py review` to the docstring's Usage block, and add this paragraph after the `mail` one:

```
review       Reads outcomes.pending.yaml and the application log, and prints
             each proposal annotated with current_outcome, application_missing,
             regresses and default_answer. Read-only.
```

- [ ] **Step 4: Run both suites and commit**

Run: `.venv/bin/python -m pytest -q` then `.venv39/bin/python -m pytest -q`
Expected: 271 passed in both

```bash
git add pipeline.py tests/test_pipeline.py
git commit -m "Add pipeline.py review: annotate proposals for confirmation"
```

---

### Task 7: `cv-check-mail`, and `assessment` in `cv-log-outcome`

**Files:**
- Create: `plugins/cvapplicate/skills/cv-check-mail/SKILL.md`
- Modify: `plugins/cvapplicate/skills/cv-log-outcome/SKILL.md`

No test cycle: instructions for a model. Verification is the frontmatter parse and a read-through against the spec.

- [ ] **Step 1: Read the sibling skill for house style**

Run: `cat plugins/cvapplicate/skills/cv-score-postings/SKILL.md`

It is the closest sibling: unattended, driven by a runner, writing one gitignored file.

- [ ] **Step 2: Write the skill**

Create `plugins/cvapplicate/skills/cv-check-mail/SKILL.md`:

```markdown
---
name: cv-check-mail
description: Read recent recruiting mail and propose outcomes (assessment, interview, offer, rejected) for logged applications, writing proposals with evidence to outcomes.pending.yaml. Never changes the mailbox or the application log. Normally run nightly and unattended by postman.sh.
---

# CV Check Mail

Turns recruiting email into outcome **proposals**. It never decides an outcome:
`cv-review-outcomes` is where the user confirms, and it is the only step that writes
`applications/log.yaml`.

## Inputs needed

None. Everything comes from `python3 pipeline.py mail`.

## Procedure

1. Run `python3 pipeline.py mail` and read its exit code.
   - **2** — configuration or authentication problem. Report the message and stop.
   - **4** — the mail server was unreachable. Report it and stop; the next run retries.
   - **0** — continue.
2. Read the JSON. Report every string in `warnings` — in particular a fallback to
   INBOX means archived or filtered mail was not searched.
3. For each entry in `candidates`, decide what it is:
   - **`rejected`** — the employer is not proceeding.
   - **`assessment`** — an online assessment or coding challenge (HackerRank,
     CodeSignal, a take-home), including a reminder about one.
   - **`interview`** — an invitation to speak with a person: phone screen, technical
     interview, superday, final round.
   - **`offer`** — an offer of employment.
   - **not an outcome** — an application-received receipt, a newsletter, a job alert,
     marketing from a company's product, an event invitation.

   Judge from the subject and body together. "Thank you for your interest" opens
   rejections and invitations alike; read on. If the message is genuinely unclear,
   propose it with `confidence: low` rather than guessing a firm outcome.
4. Decide which application it concerns:
   - If `candidate_ids` has exactly one id, use it.
   - If it has several — the same company, more than one application — pick one only
     when the message names the role, team or requisition number of exactly one of
     them, using `applications` to see each one's `role`. Otherwise leave
     `application_id: null` and copy all of them into `candidates`. **Never guess
     between applications at the same company.**
   - If it is empty — typically assessment-platform mail — identify the employer from
     the body and match it against `applications`. If you cannot, leave
     `application_id: null` with an empty `candidates` list.
5. Assign `confidence`: `high` only when both the outcome and the application are
   unambiguous; `medium` when one of them needed judgement; `low` when you are unsure.
6. Write `outcomes.pending.yaml` in **one** edit:
   - Append every candidate's `message_id` to `seen` — outcomes and non-outcomes alike,
     so nothing is ever reprocessed.
   - Append one proposal per outcome message, in this shape:
     ```yaml
     - message_id: "<abc123@mail.citadel.com>"
       received: 2026-09-02
       from: "Citadel Recruiting <no-reply@citadel.com>"
       subject: "Your Citadel Application"
       proposed_outcome: rejected
       application_id: citadel-swe-2026-08
       candidates: []
       evidence: "Unfortunately, we will not be moving forward with your application"
       confidence: high
     ```
   - `evidence` is a **verbatim** quote from the message body, the shortest one that
     justifies the outcome. Never paraphrase it: the user confirms against it.
   - Create the file with `seen:` and `proposals:` keys if it does not exist. Never
     remove existing entries — `cv-review-outcomes` owns removal.
7. If `remaining` is greater than zero, say so: that many more candidates wait for the
   next run.
8. Report: how many messages were examined, how many proposals were written by outcome
   type, how many were ambiguous, and any warnings.

## Error handling

- Never edit `applications/log.yaml`. Never run any `git` command. Never compute
  `regresses` or a default answer — `pipeline.py review` does that at confirm time.
- If writing `outcomes.pending.yaml` fails, say so plainly: those messages were not
  marked seen and will be offered again next run, which is safe.
- Never include the contents of `.env`, or any credential, in a report.

## Permission scope

```
Read Edit(/outcomes.pending.yaml) Bash(python3 pipeline.py:*)
```

No git grant and no `Edit` on `applications/log.yaml`, so this skill cannot change the
application log even if it misbehaves.
```

- [ ] **Step 3: Add `assessment` to `cv-log-outcome`**

In `plugins/cvapplicate/skills/cv-log-outcome/SKILL.md`, make exactly two edits.

Line 3, the frontmatter `description`, from:

```
description: Record the outcome of a job application (interview, offer, rejection, no response) in the application log. Use when the user reports hearing back from a company they applied to.
```

to:

```
description: Record the outcome of a job application (assessment, interview, offer, rejection, no response) in the application log. Use when the user reports hearing back from a company they applied to.
```

Lines 15-17, from:

```
2. **Outcome** — one of: `interview`, `rejected`, `offer`, `no_response`. If the user
   describes it in other words (e.g. "got an OA", "ghosted"), map it to the closest
   of these four and confirm with the user if it's not obvious.
```

to:

```
2. **Outcome** — one of: `assessment`, `interview`, `rejected`, `offer`,
   `no_response`. An online assessment or coding challenge ("got an OA",
   "HackerRank invite") is `assessment`, not `interview`. If the user describes the
   outcome in other words (e.g. "ghosted"), map it to the closest of these five and
   confirm with the user if it's not obvious.
```

Keep everything else unchanged.

Verify: `grep -n "assessment" plugins/cvapplicate/skills/cv-log-outcome/SKILL.md` shows the new value, and `grep -n "OA" plugins/cvapplicate/skills/cv-log-outcome/SKILL.md` no longer maps it to `interview`.

- [ ] **Step 4: Verify both frontmatters parse, and commit**

```bash
for s in cv-check-mail cv-log-outcome; do .venv/bin/python -c "
import pathlib, yaml, sys
text = pathlib.Path('plugins/cvapplicate/skills/' + sys.argv[1] + '/SKILL.md').read_text()
print('frontmatter OK:', yaml.safe_load(text.split('---')[1])['name'])
" "$s"; done
git add plugins/cvapplicate/skills/cv-check-mail/SKILL.md plugins/cvapplicate/skills/cv-log-outcome/SKILL.md
git commit -m "Add cv-check-mail and an assessment outcome"
```

---

### Task 8: `cv-review-outcomes`

**Files:**
- Create: `plugins/cvapplicate/skills/cv-review-outcomes/SKILL.md`

- [ ] **Step 1: Read the sibling skill**

Run: `cat plugins/cvapplicate/skills/cv-log-outcome/SKILL.md` — this skill does the same log edit, in bulk, with confirmation.

- [ ] **Step 2: Write the skill**

Create `plugins/cvapplicate/skills/cv-review-outcomes/SKILL.md`:

```markdown
---
name: cv-review-outcomes
description: Walk through the outcome proposals cv-check-mail found in your recruiting mail, confirm or reject each, and record the confirmed ones in applications/log.yaml in one commit. Use when the user wants to review or apply pending application outcomes.
---

# CV Review Outcomes

The only step in the mail flow that writes the application log. Nothing reaches
`applications/log.yaml` without the user saying yes.

## Inputs needed

None. Proposals come from `outcomes.pending.yaml`.

## Procedure

1. Run `git status`. If the working tree is not clean, stop and say what is
   uncommitted.
2. `git checkout main`.
3. Run `python3 pipeline.py review` and read the JSON. If there are no proposals, say
   so and stop.
4. Present the proposals one at a time. For each, show: the company and role (or the
   candidate applications, if ambiguous), `current_outcome` → `proposed_outcome`, the
   `received` date, the sender and subject, and the `evidence` quote verbatim. Show
   the **default answer** from `default_answer`, and say why when it is no — low
   confidence, `regresses`, ambiguous, or `application_missing`.
5. Take the user's answer:
   - **yes** — accept as proposed. An ambiguous proposal cannot be accepted with a
     plain yes; ask which of the candidate applications it concerns.
   - **no** — discard the proposal.
   - **edit** — change the outcome, or pick the application.
   Never accept a proposal on the user's behalf, and never apply one whose
   `application_missing` is true.
6. When several accepted proposals concern the same application, keep only the
   furthest-forward stage (`pending < assessment < interview < offer`, with `rejected`
   final) and tell the user which were superseded.
7. For each accepted proposal, set that entry's `outcome` and set `outcome_date` to
   the proposal's **`received` date, not today** — the email date is when the outcome
   actually happened.
8. Commit once: `git add applications/log.yaml && git commit -m "Log outcomes: <N> applications"`.
9. Remove every handled proposal — accepted, edited or discarded — from
   `outcomes.pending.yaml`. Keep the `seen` list intact.
10. Report what was recorded, what was discarded, and what remains pending.

## Error handling

- Dirty working tree → stop before any checkout.
- If the commit fails, leave `outcomes.pending.yaml` untouched so nothing is lost, and
  report the error.
- Never edit an application entry's fields other than `outcome` and `outcome_date`.
```

- [ ] **Step 3: Verify the frontmatter parses, and commit**

```bash
.venv/bin/python -c "
import pathlib, yaml
text = pathlib.Path('plugins/cvapplicate/skills/cv-review-outcomes/SKILL.md').read_text()
print('frontmatter OK:', yaml.safe_load(text.split('---')[1])['name'])
"
git add plugins/cvapplicate/skills/cv-review-outcomes/SKILL.md
git commit -m "Add cv-review-outcomes"
```

---

### Task 9: Runner, configuration and docs

**Files:**
- Create: `postman.sh`, `launchd/com.cvapplicate.postman.plist.example`
- Modify: `.gitignore`, `.env.example`, `README.md`

- [ ] **Step 1: Write the runner**

Create `postman.sh`, matching `score-postings.sh`'s house style:

```bash
#!/bin/bash
# Reads recent recruiting mail and proposes application outcomes into
# outcomes.pending.yaml, via the cv-check-mail skill. Confirm them later with
# cv-review-outcomes, which is the only step that writes applications/log.yaml.
#
# Never changes the mailbox or the application log. The grant below has no git
# rights and no edit rights on the log, so a misbehaving run cannot alter either.
#
# Designed to run once a day via launchd (see
# launchd/com.cvapplicate.postman.plist.example). Requires the `claude` CLI on
# PATH, and IMAP enabled for the Gmail account in .env.
set -euo pipefail
cd "$(dirname "$0")"

claude -p "Run cv-check-mail." \
  --permission-mode acceptEdits \
  --allowedTools "Read Edit(/outcomes.pending.yaml) Bash(python3 pipeline.py:*)"
```

Then:

```bash
chmod +x postman.sh
grep -E 'git |Edit\([^)]*log\.yaml|python3 -c' postman.sh | grep -v '^#' && echo "FAIL" || echo "OK: no git, no log edit, no python3 -c"
```

Expected: `OK: no git, no log edit, no python3 -c`

- [ ] **Step 2: Write the launchd example**

Create `launchd/com.cvapplicate.postman.plist.example`, running at 21:00:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>com.cvapplicate.postman</string>
	<key>ProgramArguments</key>
	<array>
		<string>/ABSOLUTE/PATH/TO/CVApplicate/postman.sh</string>
	</array>
	<key>WorkingDirectory</key>
	<string>/ABSOLUTE/PATH/TO/CVApplicate</string>
	<key>StartCalendarInterval</key>
	<dict>
		<key>Hour</key>
		<integer>21</integer>
		<key>Minute</key>
		<integer>0</integer>
	</dict>
	<key>StandardOutPath</key>
	<string>/ABSOLUTE/PATH/TO/CVApplicate/postman.log</string>
	<key>StandardErrorPath</key>
	<string>/ABSOLUTE/PATH/TO/CVApplicate/postman.log</string>
</dict>
</plist>
```

- [ ] **Step 3: Configuration**

Append `outcomes.pending.yaml` to `.gitignore` (it is not covered by `*.local.yaml`). Confirm with `git check-ignore -q outcomes.pending.yaml && echo ignored`, and confirm `postman.log` is covered by an existing `*.log` pattern, adding it if not.

Append to `.env.example`:

```
# IMAP server for reading recruiting mail (Postman). Uses the same Gmail
# account and app password as above; IMAP must be enabled in Gmail settings.
IMAP_HOST=imap.gmail.com
```

- [ ] **Step 4: README**

Run `grep -n "ten skills\|All ten" README.md`. Change each to "twelve", and in `## Status` change only the implemented count — "six are validated end-to-end" stays, since the new skills are unvalidated. Add two rows to the Skills table:

```markdown
| **cv-check-mail** | Reads recent recruiting mail and proposes outcomes for logged applications — never changes the mailbox or the log |
| **cv-review-outcomes** | Walks you through proposed outcomes and records the ones you confirm, in one commit |
```

Add a section after "Building a packet to submit":

```markdown
## Tracking outcomes from your inbox

`postman.sh` reads recruiting mail since your earliest logged application and writes
**proposals** to `outcomes.pending.yaml` — rejections, online assessments, interview
invitations and offers, each with the sentence that justifies it. It never changes your
mailbox: folders are opened read-only and messages stay unread.

Nothing is written to your application log until you confirm it:

```
Run cv-review-outcomes
```

Each proposal comes with a default answer. It is only "yes" for a confident proposal
concerning exactly one application; anything ambiguous — a Microsoft email that could
be about any of three applications — needs you to choose. Confirmed outcomes are
recorded with the email's date and committed in one go.

Enable IMAP for the Gmail account in `.env` first: Gmail → Settings → Forwarding and
POP/IMAP → Enable IMAP.
```

- [ ] **Step 5: Verify and commit**

```bash
grep -n "ten skills" README.md && echo "STILL STALE" || echo "clean"
.venv/bin/python -m pytest -q
.venv39/bin/python -m pytest -q
git add postman.sh launchd/com.cvapplicate.postman.plist.example .gitignore .env.example README.md
git commit -m "Add the Postman runner and document the outcome flow"
```

Expected: `clean`, and 271 passed in both suites.

---

## Deferred

- **Fixtures from real mail.** When the user supplies exported `.eml` files in `~/Desktop/mail-samples/`: for each, run it through `mailbox.parse_message` and `outcomes.is_candidate`; trim it; replace the user's name, address, phone, candidate IDs and tokenized links; show the trimmed version to the user; and only then commit it under `tests/fixtures/mail/` with a test asserting its parsed subject, sender and body. Any failure is a real parsing bug.
- **Rescanning headers every night.** Each run fetches headers for all mail since the earliest application. That is cheap for a recruiting season but grows without bound. A stored last-run date would bound it; not needed yet.
- **Plugin distribution of the Python pipeline.** This phase adds two more root-level modules, so the manual sync into the data repo grows again.
