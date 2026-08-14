from __future__ import annotations

import pytest

from job_fetcher import config


def test_load_companies_happy_path(tmp_path):
    path = tmp_path / "companies.local.yaml"
    path.write_text(
        "- name: Acme\n  slug: acme\n  ats: greenhouse\n"
        "- name: Beta Inc\n  slug: beta\n  ats: lever\n"
    )

    result = config.load_companies(str(path))

    assert result == [
        {"name": "Acme", "slug": "acme", "ats": "greenhouse"},
        {"name": "Beta Inc", "slug": "beta", "ats": "lever"},
    ]


def test_load_companies_missing_file_raises_config_error(tmp_path):
    with pytest.raises(config.ConfigError):
        config.load_companies(str(tmp_path / "missing.yaml"))


def test_load_companies_empty_file_raises_config_error(tmp_path):
    path = tmp_path / "companies.local.yaml"
    path.write_text("")

    with pytest.raises(config.ConfigError):
        config.load_companies(str(path))


def test_load_companies_missing_required_key_raises_config_error(tmp_path):
    path = tmp_path / "companies.local.yaml"
    path.write_text("- name: Acme\n  slug: acme\n")  # missing ats

    with pytest.raises(config.ConfigError):
        config.load_companies(str(path))


def test_load_companies_non_list_raises_config_error(tmp_path):
    path = tmp_path / "companies.local.yaml"
    path.write_text("name: Acme\nslug: acme\nats: greenhouse\n")  # missing list syntax

    with pytest.raises(config.ConfigError):
        config.load_companies(str(path))


def test_load_companies_non_dict_entry_raises_config_error(tmp_path):
    path = tmp_path / "companies.local.yaml"
    path.write_text("- 42\n")  # non-dict entry

    with pytest.raises(config.ConfigError):
        config.load_companies(str(path))
