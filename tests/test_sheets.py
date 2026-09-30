from __future__ import annotations

import datetime
import json
import os
import stat
import urllib.parse

import pytest

from job_fetcher import sheets
from job_fetcher.sheets import SheetsError


# --- config -----------------------------------------------------------------

def test_load_config_accepts_a_url_and_fills_defaults(tmp_path):
    path = tmp_path / "sheets.local.yaml"
    path.write_text(
        "spreadsheet: https://docs.google.com/spreadsheets/d/abc123_-XYZ/edit?gid=0#gid=0\n",
        encoding="utf-8",
    )
    config = sheets.load_config(str(path))
    assert config["spreadsheet_id"] == "abc123_-XYZ"
    assert config["tab"] is None
    assert config["status"] == "Applied"
    assert config["date_format"] == "%Y-%m-%d"
    assert config["columns"] == {
        "company": "Company",
        "role": "Role",
        "date_applied": "Date Applied",
        "status": "Status",
    }


def test_load_config_accepts_a_bare_id_and_overrides(tmp_path):
    path = tmp_path / "sheets.local.yaml"
    path.write_text(
        "spreadsheet: abc123\n"
        "tab: Internships\n"
        "status: Submitted\n"
        "date_format: '%m/%d/%Y'\n"
        "columns:\n"
        "  role: Position\n",
        encoding="utf-8",
    )
    config = sheets.load_config(str(path))
    assert config["spreadsheet_id"] == "abc123"
    assert config["tab"] == "Internships"
    assert config["status"] == "Submitted"
    assert config["date_format"] == "%m/%d/%Y"
    assert config["columns"]["role"] == "Position"
    assert config["columns"]["company"] == "Company"


def test_load_config_missing_file_returns_none(tmp_path):
    assert sheets.load_config(str(tmp_path / "nope.yaml")) is None


@pytest.mark.parametrize("body", [
    "tab: x\n",
    "spreadsheet: 'not a sheet!'\n",
    "- a list\n",
    "spreadsheet: abc\ncolumns:\n  salary: Pay\n",
])
def test_load_config_rejects_bad_files(tmp_path, body):
    path = tmp_path / "sheets.local.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(SheetsError):
        sheets.load_config(str(path))


# --- row building -----------------------------------------------------------

COLUMNS = {
    "company": "Company",
    "role": "Role",
    "date_applied": "Date Applied",
    "status": "Status",
}


def test_build_row_places_values_under_their_headers_and_blanks_the_rest():
    headers = ["Company", "Link", " role ", "Status", "Notes", "Date applied"]
    row = sheets.build_row(headers, COLUMNS, {
        "company": "Two Sigma",
        "role": "SWE Intern",
        "date_applied": "2026-09-30",
        "status": "Applied",
    })
    assert row == ["Two Sigma", "", "SWE Intern", "Applied", "", "2026-09-30"]


def test_build_row_names_every_missing_header():
    with pytest.raises(SheetsError) as excinfo:
        sheets.build_row(["Company", "Notes"], COLUMNS, {
            "company": "a", "role": "b", "date_applied": "c", "status": "d",
        })
    message = str(excinfo.value)
    assert "Role" in message and "Date Applied" in message and "Status" in message


def test_build_row_rejects_duplicate_headers():
    with pytest.raises(SheetsError):
        sheets.build_row(["Company", "Role", "Company", "Date Applied", "Status"],
                         COLUMNS, {"company": "a", "role": "b",
                                   "date_applied": "c", "status": "d"})


@pytest.mark.parametrize("value", ["=HYPERLINK(\"x\")", "+1", "-2", "@x"])
def test_build_row_neutralises_formula_prefixes(value):
    row = sheets.build_row(["Company", "Role", "Date Applied", "Status"], COLUMNS, {
        "company": value, "role": "r", "date_applied": "d", "status": "s",
    })
    assert row[0] == "'" + value


def test_column_letter():
    assert sheets.column_letter(0) == "A"
    assert sheets.column_letter(25) == "Z"
    assert sheets.column_letter(26) == "AA"
    assert sheets.column_letter(51) == "AZ"
    assert sheets.column_letter(52) == "BA"


def test_next_row_follows_the_last_filled_company_cell():
    values = [
        ["Company", "Role"],
        ["A", "x"],
        ["", "stray note"],
        ["B", "y"],
        [],
        ["", ""],
    ]
    assert sheets.next_row(values, 0) == 5


def test_next_row_on_header_only_sheet():
    assert sheets.next_row([["Company", "Role"]], 0) == 2


def test_find_duplicate_matches_case_and_space_insensitively():
    values = [
        ["Company", "Role", "Date Applied"],
        ["Two Sigma ", "swe intern", "2026-09-30"],
    ]
    indexes = {"company": 0, "role": 1, "date_applied": 2}
    assert sheets.find_duplicate(values, indexes, {
        "company": "two sigma", "role": "SWE Intern", "date_applied": "2026-09-30",
    }) == 2
    assert sheets.find_duplicate(values, indexes, {
        "company": "two sigma", "role": "SWE Intern", "date_applied": "2026-10-01",
    }) is None


# --- token file -------------------------------------------------------------

def test_save_and_load_token_is_owner_only(tmp_path):
    path = tmp_path / "sheets-token.local.json"
    sheets.save_refresh_token(str(path), "r-token")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert sheets.load_refresh_token(str(path)) == "r-token"


def test_load_token_missing_returns_none(tmp_path):
    assert sheets.load_refresh_token(str(tmp_path / "none.json")) is None


def test_load_token_corrupt_raises(tmp_path):
    path = tmp_path / "t.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SheetsError):
        sheets.load_refresh_token(str(path))


# --- auth URL ---------------------------------------------------------------

def test_consent_url_requests_offline_sheets_access_with_pkce():
    url = sheets.consent_url("cid", "http://127.0.0.1:5555/", "challenge", "state1")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query["client_id"] == ["cid"]
    assert query["redirect_uri"] == ["http://127.0.0.1:5555/"]
    assert query["scope"] == [sheets.SCOPE]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["code_challenge"] == ["challenge"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"] == ["state1"]


def test_pkce_pair_is_s256():
    import base64
    import hashlib
    verifier, challenge = sheets.pkce_pair()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    assert challenge == expected
    assert 43 <= len(verifier) <= 128


# --- append flow (fake transport) -------------------------------------------

class FakeTransport:
    """Records requests and replies like the token endpoint and Sheets API."""

    def __init__(self, values, tabs=("Sheet1",), token_status=200):
        self.values = values
        self.tabs = list(tabs)
        self.token_status = token_status
        self.calls = []

    def __call__(self, method, url, headers=None, body=None):
        self.calls.append((method, url, headers or {}, body))
        if url == sheets.TOKEN_URL:
            if self.token_status != 200:
                return self.token_status, {"error": "invalid_grant"}
            return 200, {"access_token": "access-1", "expires_in": 3600}
        if method == "GET" and "/values/" not in url:
            return 200, {"sheets": [{"properties": {"title": t}} for t in self.tabs]}
        if method == "GET":
            return 200, {"values": self.values}
        if method == "PUT":
            return 200, {"updatedRange": "x", "updatedCells": 4}
        return 500, {}


CONFIG = {
    "spreadsheet_id": "sheet-id",
    "tab": None,
    "status": "Applied",
    "date_format": "%Y-%m-%d",
    "columns": dict(COLUMNS),
}

APPLICATION = {"company": "Two Sigma", "role": "SWE Intern",
               "date_applied": datetime.date(2026, 9, 30)}


def _append(transport, config=CONFIG, application=APPLICATION):
    return sheets.append_application(
        config, application, client_id="cid", client_secret="secret",
        refresh_token="refresh", transport=transport)


def test_append_writes_one_row_after_the_last_company():
    transport = FakeTransport([
        ["Company", "Link", "Role", "Date Applied", "Status"],
        ["Citadel", "", "SWE", "2026-08-20", "Applied"],
    ])
    result = _append(transport)
    assert result == {"appended": True, "tab": "Sheet1", "row": 3,
                      "values": {"Company": "Two Sigma", "Role": "SWE Intern",
                                 "Date Applied": "2026-09-30", "Status": "Applied"}}
    method, url, headers, body = transport.calls[-1]
    assert method == "PUT"
    assert headers["Authorization"] == "Bearer access-1"
    assert "/values/" + urllib.parse.quote("'Sheet1'!A3:E3", safe="") in url
    assert "valueInputOption=USER_ENTERED" in url
    assert json.loads(body) == {
        "range": "'Sheet1'!A3:E3",
        "majorDimension": "ROWS",
        "values": [["Two Sigma", "", "SWE Intern", "2026-09-30", "Applied"]],
    }


def test_append_uses_the_configured_tab_and_date_format():
    transport = FakeTransport([["Company", "Role", "Date Applied", "Status"]],
                              tabs=("Other", "Apps"))
    config = dict(CONFIG, tab="Apps", date_format="%m/%d/%Y")
    result = _append(transport, config)
    assert result["tab"] == "Apps"
    assert result["row"] == 2
    assert result["values"]["Date Applied"] == "09/30/2026"


def test_append_unknown_tab_fails():
    transport = FakeTransport([["Company"]], tabs=("Sheet1",))
    with pytest.raises(SheetsError, match="Apps"):
        _append(transport, dict(CONFIG, tab="Apps"))


def test_append_skips_a_duplicate_without_writing():
    transport = FakeTransport([
        ["Company", "Role", "Date Applied", "Status"],
        ["Two Sigma", "SWE Intern", "2026-09-30", "Applied"],
    ])
    result = _append(transport)
    assert result == {"appended": False, "reason": "duplicate", "tab": "Sheet1", "row": 2}
    assert all(call[0] != "PUT" for call in transport.calls)


def test_append_missing_header_writes_nothing():
    transport = FakeTransport([["Company", "Role", "Status"]])
    with pytest.raises(SheetsError, match="Date Applied"):
        _append(transport)
    assert all(call[0] != "PUT" for call in transport.calls)


def test_append_empty_sheet_fails():
    transport = FakeTransport([])
    with pytest.raises(SheetsError, match="header"):
        _append(transport)


def test_append_revoked_refresh_token_says_to_reauthorise():
    transport = FakeTransport([["Company"]], token_status=400)
    with pytest.raises(SheetsError, match="sheet-auth"):
        _append(transport)


@pytest.mark.parametrize("missing", ["company", "role"])
def test_append_requires_company_and_role(missing):
    application = dict(APPLICATION)
    application[missing] = "  "
    with pytest.raises(SheetsError):
        _append(FakeTransport([["Company"]]), application=application)


def test_append_accepts_an_iso_date_string():
    transport = FakeTransport([["Company", "Role", "Date Applied", "Status"]])
    result = _append(transport, application=dict(APPLICATION, date_applied="2026-09-30"))
    assert result["values"]["Date Applied"] == "2026-09-30"


def test_append_rejects_a_bad_date():
    with pytest.raises(SheetsError):
        _append(FakeTransport([["Company"]]),
                application=dict(APPLICATION, date_applied="yesterday"))
