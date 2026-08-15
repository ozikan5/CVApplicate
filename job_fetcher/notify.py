from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


class NotifyConfigError(Exception):
    pass


def build_summary_email(new_postings: list[dict]) -> tuple[str, str]:
    subject = f"{len(new_postings)} new job posting(s)"
    lines = [
        f"- {p['company']}: {p['title']} ({p['location']}) — {p['url']}"
        for p in new_postings
    ]
    body = "\n".join(lines)
    return subject, body


def smtp_config_from_env() -> dict:
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_APP_PASSWORD", "NOTIFY_TO"]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise NotifyConfigError(f"missing required .env values: {', '.join(missing)}")
    return {
        "host": os.environ["SMTP_HOST"],
        "port": int(os.environ["SMTP_PORT"]),
        "user": os.environ["SMTP_USER"],
        "password": os.environ["SMTP_APP_PASSWORD"],
        "to": os.environ["NOTIFY_TO"],
    }


def send_email(subject: str, body: str, config: dict) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["user"]
    message["To"] = config["to"]
    message.set_content(body)

    with smtplib.SMTP(config["host"], config["port"], timeout=10) as server:
        server.starttls()
        server.login(config["user"], config["password"])
        server.send_message(message)
