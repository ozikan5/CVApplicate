from __future__ import annotations

import yaml

REQUIRED_KEYS = {"name", "slug", "ats"}


class ConfigError(Exception):
    pass


def load_companies(path: str) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigError(
            f"{path} not found. Copy companies.example.yaml to {path} and fill in "
            "the companies you want to track."
        )

    if not data:
        raise ConfigError(f"{path} is empty. Add at least one company entry.")

    for entry in data:
        missing = REQUIRED_KEYS - entry.keys()
        if missing:
            raise ConfigError(f"company entry {entry!r} is missing required keys: {missing}")

    return data
