from __future__ import annotations

import pytest

from job_fetcher import notify


def test_build_summary_email_formats_postings():
    postings = [
        {
            "company": "Acme",
            "title": "Engineer",
            "location": "Remote",
            "url": "https://example.com/1",
        }
    ]

    subject, body = notify.build_summary_email(postings)

    assert subject == "1 new job posting(s)"
    assert "Acme: Engineer (Remote) — https://example.com/1" in body


def test_smtp_config_from_env_reads_all_values(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "me@example.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "secret")
    monkeypatch.setenv("NOTIFY_TO", "me@example.com")

    config = notify.smtp_config_from_env()

    assert config == {
        "host": "smtp.example.com",
        "port": 587,
        "user": "me@example.com",
        "password": "secret",
        "to": "me@example.com",
    }


def test_smtp_config_from_env_raises_when_missing(monkeypatch):
    for key in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_APP_PASSWORD", "NOTIFY_TO"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(notify.NotifyConfigError):
        notify.smtp_config_from_env()


def test_send_email_uses_starttls_login_and_sends(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=10):
            calls.append(("init", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, message):
            calls.append(("send", message["Subject"], message["To"]))

    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)

    config = {
        "host": "smtp.example.com",
        "port": 587,
        "user": "me@example.com",
        "password": "secret",
        "to": "friend@example.com",
    }

    notify.send_email("Subject line", "Body text", config)

    assert ("init", "smtp.example.com", 587) in calls
    assert ("starttls",) in calls
    assert ("login", "me@example.com", "secret") in calls
    assert ("send", "Subject line", "friend@example.com") in calls
