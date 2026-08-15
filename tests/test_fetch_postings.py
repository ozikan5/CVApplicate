from __future__ import annotations

import importlib.util
import pathlib


def _load_fetch_postings_module():
    spec = importlib.util.spec_from_file_location(
        "fetch_postings_script",
        pathlib.Path(__file__).parent.parent / "fetch-postings.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FAKE_POSTING = {
    "id": "examplecorp-1",
    "company": "Example Corp",
    "title": "Software Engineer",
    "url": "https://boards.greenhouse.io/examplecorp/jobs/1",
    "location": "Remote",
    "posted_date": "2026-08-10",
}


def _write_companies_file(tmp_path):
    companies_file = tmp_path / "companies.local.yaml"
    companies_file.write_text(
        "- name: Example Corp\n  slug: examplecorp\n  ats: greenhouse\n"
    )
    return companies_file


def test_main_writes_new_postings_and_marks_notified(tmp_path, monkeypatch):
    module = _load_fetch_postings_module()

    companies_file = _write_companies_file(tmp_path)
    postings_file = tmp_path / "postings.local.yaml"

    monkeypatch.setattr(module, "COMPANIES_PATH", str(companies_file))
    monkeypatch.setattr(module, "POSTINGS_PATH", str(postings_file))
    monkeypatch.setattr(module, "DELAY_BETWEEN_COMPANIES_SECONDS", 0)
    monkeypatch.setattr(module, "fetch_postings_for_company", lambda company: [FAKE_POSTING])

    sent = {}

    def fake_send_email(subject, body, config):
        sent["subject"] = subject

    monkeypatch.setattr(module, "send_email", fake_send_email)
    monkeypatch.setattr(module, "smtp_config_from_env", lambda: {})

    exit_code = module.main()

    assert exit_code == 0
    assert "1 new job posting" in sent["subject"]

    saved = module.load_postings(str(postings_file))
    assert len(saved) == 1
    assert saved[0]["notified"] is True


def test_main_leaves_notified_false_when_email_fails(tmp_path, monkeypatch):
    module = _load_fetch_postings_module()

    companies_file = _write_companies_file(tmp_path)
    postings_file = tmp_path / "postings.local.yaml"

    monkeypatch.setattr(module, "COMPANIES_PATH", str(companies_file))
    monkeypatch.setattr(module, "POSTINGS_PATH", str(postings_file))
    monkeypatch.setattr(module, "DELAY_BETWEEN_COMPANIES_SECONDS", 0)
    monkeypatch.setattr(module, "fetch_postings_for_company", lambda company: [FAKE_POSTING])

    def failing_send_email(subject, body, config):
        raise RuntimeError("smtp unreachable")

    monkeypatch.setattr(module, "send_email", failing_send_email)
    monkeypatch.setattr(module, "smtp_config_from_env", lambda: {})

    exit_code = module.main()

    assert exit_code == 0
    saved = module.load_postings(str(postings_file))
    assert saved[0]["notified"] is False


def test_main_returns_error_code_when_companies_config_missing(tmp_path, monkeypatch):
    module = _load_fetch_postings_module()

    monkeypatch.setattr(module, "COMPANIES_PATH", str(tmp_path / "missing.yaml"))
    monkeypatch.setattr(module, "POSTINGS_PATH", str(tmp_path / "postings.local.yaml"))

    exit_code = module.main()

    assert exit_code == 2
