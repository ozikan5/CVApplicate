from __future__ import annotations

import os

from job_fetcher import env


def test_load_dotenv_does_nothing_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("FETCHER_TEST_VAR", raising=False)

    env.load_dotenv(str(tmp_path / "missing.env"))

    assert "FETCHER_TEST_VAR" not in os.environ


def test_load_dotenv_sets_values_from_file(tmp_path, monkeypatch):
    monkeypatch.delenv("FETCHER_TEST_VAR", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\n\nFETCHER_TEST_VAR=hello\n")

    env.load_dotenv(str(env_file))

    assert os.environ["FETCHER_TEST_VAR"] == "hello"


def test_load_dotenv_does_not_override_existing_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("FETCHER_TEST_VAR", "original")
    env_file = tmp_path / ".env"
    env_file.write_text("FETCHER_TEST_VAR=from_file\n")

    env.load_dotenv(str(env_file))

    assert os.environ["FETCHER_TEST_VAR"] == "original"
