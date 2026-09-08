from __future__ import annotations

import yaml

VALID_SEEKING = ("internship", "new-grad", "full-time")
VALID_AUTHORIZATION = ("cpt-opt", "citizen-or-pr", "unrestricted")


class ProfileError(Exception):
    pass


def load_profile(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except FileNotFoundError:
        raise ProfileError(
            f"{path} not found. Copy profile.example.yaml to {path} and fill in what "
            "you are seeking and eligible for."
        )

    if data is None:
        raise ProfileError(f"{path} is empty. See profile.example.yaml for the shape.")
    if not isinstance(data, dict):
        raise ProfileError(
            f"{path} must be a mapping of settings. See profile.example.yaml."
        )

    seeking = data.get("seeking", "internship")
    if seeking not in VALID_SEEKING:
        raise ProfileError(
            f"seeking: {seeking!r} is not one of {', '.join(VALID_SEEKING)}"
        )

    authorization = data.get("work_authorization")
    if authorization is not None and authorization not in VALID_AUTHORIZATION:
        raise ProfileError(
            f"work_authorization: {authorization!r} is not one of "
            f"{', '.join(VALID_AUTHORIZATION)} (omit the key to disable the rule)"
        )

    locations = data.get("locations") or []
    if not isinstance(locations, list):
        raise ProfileError("locations: must be a list of location strings")

    return {
        "seeking": seeking,
        "graduation": data.get("graduation"),
        "locations": locations,
        "max_years_experience_required": data.get("max_years_experience_required"),
        "work_authorization": authorization,
    }
