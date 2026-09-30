"""Append a submitted application to a Google Sheets tracker.

Standard library only: OAuth (installed-app flow with PKCE, refresh-token
grant) and the Sheets REST API are both plain HTTPS + JSON, so this adds no
dependency. Every network call goes through a ``transport`` callable so tests
never touch the network.

The sheet's own header row decides where each value lands: columns are found
by header name (case- and whitespace-insensitive), so the tracker's layout can
change without a code change. Columns the config does not name are left blank.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request

import yaml

SCOPE = "https://www.googleapis.com/auth/spreadsheets"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_ROOT = "https://sheets.googleapis.com/v4/spreadsheets"

FIELDS = ("company", "role", "date_applied", "status")
DEFAULT_COLUMNS = {
    "company": "Company",
    "role": "Role",
    "date_applied": "Date Applied",
    "status": "Status",
}
DEFAULT_STATUS = "Applied"
DEFAULT_DATE_FORMAT = "%Y-%m-%d"

_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_URL_ID_RE = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)")
_FORMULA_PREFIXES = ("=", "+", "-", "@")
_TIMEOUT = 30


class SheetsError(Exception):
    """A problem the user must fix: config, credentials, sheet layout, or the API."""


# --- config -----------------------------------------------------------------

def load_config(path: str):
    """Read sheets.local.yaml. Returns None when the file does not exist."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as error:
        raise SheetsError(f"could not read {path}: {error}") from None
    if not isinstance(raw, dict):
        raise SheetsError(f"{path} must be a mapping with a 'spreadsheet' key")

    spreadsheet = str(raw.get("spreadsheet") or "").strip()
    match = _URL_ID_RE.search(spreadsheet)
    spreadsheet_id = match.group(1) if match else spreadsheet
    if not _ID_RE.match(spreadsheet_id):
        raise SheetsError(
            f"{path}: 'spreadsheet' must be the sheet's URL or its id")

    columns = dict(DEFAULT_COLUMNS)
    overrides = raw.get("columns") or {}
    if not isinstance(overrides, dict):
        raise SheetsError(f"{path}: 'columns' must be a mapping")
    for key, header in overrides.items():
        if key not in DEFAULT_COLUMNS:
            raise SheetsError(
                f"{path}: unknown column key {key!r} (expected one of "
                f"{', '.join(FIELDS)})")
        if not str(header or "").strip():
            raise SheetsError(f"{path}: column {key!r} needs a header name")
        columns[key] = str(header).strip()

    tab = raw.get("tab")
    return {
        "spreadsheet_id": spreadsheet_id,
        "tab": str(tab).strip() if tab else None,
        "status": str(raw.get("status") or DEFAULT_STATUS),
        "date_format": str(raw.get("date_format") or DEFAULT_DATE_FORMAT),
        "columns": columns,
    }


# --- token file -------------------------------------------------------------

def save_refresh_token(path: str, refresh_token: str) -> None:
    """Write the refresh token owner-read/write only, never world-readable."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"refresh_token": refresh_token}, f)
    os.chmod(path, 0o600)


def load_refresh_token(path: str):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        raise SheetsError(
            f"{path} is unreadable; run ./pipeline.py sheet-auth again") from None
    token = data.get("refresh_token") if isinstance(data, dict) else None
    if not token:
        raise SheetsError(
            f"{path} has no refresh token; run ./pipeline.py sheet-auth again")
    return token


# --- OAuth ------------------------------------------------------------------

def pkce_pair():
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return verifier, challenge


def consent_url(client_id: str, redirect_uri: str, challenge: str, state: str) -> str:
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    })


def exchange_code(code, verifier, redirect_uri, client_id, client_secret,
                  transport=None) -> str:
    """Trade the consent-screen code for a refresh token."""
    transport = transport or http_transport
    status, reply = transport("POST", TOKEN_URL,
                              {"Content-Type": "application/x-www-form-urlencoded"},
                              urllib.parse.urlencode({
                                  "code": code,
                                  "code_verifier": verifier,
                                  "redirect_uri": redirect_uri,
                                  "client_id": client_id,
                                  "client_secret": client_secret,
                                  "grant_type": "authorization_code",
                              }))
    token = reply.get("refresh_token") if status == 200 else None
    if not token:
        raise SheetsError(
            f"Google refused the authorization code ({_describe(status, reply)})")
    return token


def access_token(client_id, client_secret, refresh_token, transport) -> str:
    status, reply = transport("POST", TOKEN_URL,
                              {"Content-Type": "application/x-www-form-urlencoded"},
                              urllib.parse.urlencode({
                                  "client_id": client_id,
                                  "client_secret": client_secret,
                                  "refresh_token": refresh_token,
                                  "grant_type": "refresh_token",
                              }))
    token = reply.get("access_token") if status == 200 else None
    if not token:
        raise SheetsError(
            "Google rejected the saved sheet authorization "
            f"({_describe(status, reply)}); run ./pipeline.py sheet-auth again")
    return token


# --- HTTP -------------------------------------------------------------------

def http_transport(method, url, headers=None, body=None):
    """Real transport: returns (status, parsed JSON body or {})."""
    data = body.encode("utf-8") if isinstance(body, str) else body
    request = urllib.request.Request(url, data=data, method=method,
                                     headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            return response.status, _json_or_empty(response.read())
    except urllib.error.HTTPError as error:
        return error.code, _json_or_empty(error.read())
    except (urllib.error.URLError, OSError) as error:
        raise SheetsError(f"could not reach Google: {error}") from None


def _json_or_empty(raw: bytes):
    try:
        parsed = json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _describe(status, reply) -> str:
    error = reply.get("error") if isinstance(reply, dict) else None
    if isinstance(error, dict):
        error = error.get("message") or error.get("status")
    return f"HTTP {status}" + (f": {error}" if error else "")


# --- sheet layout -----------------------------------------------------------

def _norm(text) -> str:
    return " ".join(str(text or "").split()).casefold()


def column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def header_indexes(headers, columns):
    """Map each field to its column index, by header name."""
    positions = {}
    for i, header in enumerate(headers):
        key = _norm(header)
        if key:
            positions.setdefault(key, []).append(i)
    indexes, missing = {}, []
    for field in FIELDS:
        found = positions.get(_norm(columns[field]), [])
        if not found:
            missing.append(columns[field])
        elif len(found) > 1:
            raise SheetsError(
                f"the header {columns[field]!r} appears more than once in row 1")
        else:
            indexes[field] = found[0]
    if missing:
        raise SheetsError(
            "the sheet's header row has no column named "
            + ", ".join(repr(m) for m in missing)
            + " (rename the column, or map it under 'columns' in sheets.local.yaml)")
    return indexes


def _cell(value: str) -> str:
    # USER_ENTERED would evaluate these as formulas; a leading quote keeps
    # them literal text.
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


def build_row(headers, columns, values):
    indexes = header_indexes(headers, columns)
    row = [""] * len(headers)
    for field, index in indexes.items():
        row[index] = _cell(str(values[field]))
    return row


def _get(row, index) -> str:
    return str(row[index]) if index < len(row) else ""


def next_row(values, company_index: int) -> int:
    """1-based row number just below the last row with a Company value."""
    last = 1
    for number, row in enumerate(values, start=1):
        if number > 1 and _get(row, company_index).strip():
            last = number
    return last + 1


def find_duplicate(values, indexes, application):
    want = tuple(_norm(application[f]) for f in ("company", "role", "date_applied"))
    for number, row in enumerate(values, start=1):
        if number == 1:
            continue
        have = tuple(_norm(_get(row, indexes[f]))
                     for f in ("company", "role", "date_applied"))
        if have == want:
            return number
    return None


# --- append -----------------------------------------------------------------

def _as_date(value):
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value).strip())
    except ValueError:
        raise SheetsError(
            f"date_applied must be YYYY-MM-DD, got {value!r}") from None


def _quote_tab(tab: str) -> str:
    return "'" + tab.replace("'", "''") + "'"


def append_application(config, application, *, client_id, client_secret,
                       refresh_token, transport=None):
    """Write one row for a submitted application; skip it if already present."""
    transport = transport or http_transport
    company = str(application.get("company") or "").strip()
    role = str(application.get("role") or "").strip()
    if not company or not role:
        raise SheetsError("company and role are both required")
    day = _as_date(application.get("date_applied"))

    token = access_token(client_id, client_secret, refresh_token, transport)
    auth = {"Authorization": f"Bearer {token}"}
    base = f"{API_ROOT}/{urllib.parse.quote(config['spreadsheet_id'], safe='')}"

    status, meta = transport("GET", base + "?fields=sheets.properties.title", auth)
    if status != 200:
        raise SheetsError(f"could not open the spreadsheet ({_describe(status, meta)})")
    titles = [s.get("properties", {}).get("title") for s in meta.get("sheets", [])]
    tab = config.get("tab") or (titles[0] if titles else None)
    if not tab or tab not in titles:
        raise SheetsError(
            f"the spreadsheet has no tab named {config.get('tab')!r} "
            f"(tabs: {', '.join(t for t in titles if t)})")

    read_range = urllib.parse.quote(_quote_tab(tab), safe="")
    status, reply = transport("GET", f"{base}/values/{read_range}", auth)
    if status != 200:
        raise SheetsError(f"could not read the sheet ({_describe(status, reply)})")
    values = reply.get("values") or []
    if not values or not any(str(h).strip() for h in values[0]):
        raise SheetsError(f"tab {tab!r} has no header row")
    headers = values[0]

    record = {
        "company": company,
        "role": role,
        "date_applied": day.strftime(config["date_format"]),
        "status": config["status"],
    }
    indexes = header_indexes(headers, config["columns"])
    duplicate = find_duplicate(values, indexes, record)
    if duplicate:
        return {"appended": False, "reason": "duplicate", "tab": tab, "row": duplicate}

    row_values = build_row(headers, config["columns"], record)
    number = next_row(values, indexes["company"])
    target = (f"{_quote_tab(tab)}!A{number}:"
              f"{column_letter(len(headers) - 1)}{number}")
    body = json.dumps({"range": target, "majorDimension": "ROWS",
                       "values": [row_values]})
    url = (f"{base}/values/{urllib.parse.quote(target, safe='')}"
           "?valueInputOption=USER_ENTERED")
    status, reply = transport("PUT", url,
                              dict(auth, **{"Content-Type": "application/json"}), body)
    if status != 200:
        raise SheetsError(f"could not write the row ({_describe(status, reply)})")
    return {
        "appended": True,
        "tab": tab,
        "row": number,
        "values": {config["columns"][f]: record[f] for f in FIELDS},
    }
