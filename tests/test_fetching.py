from __future__ import annotations

import urllib.error

import pytest

from job_fetcher import fetching


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_exit_codes_are_stable():
    assert fetching.UsageError("x").exit_code == 2
    assert fetching.NeedsBrowser("x").exit_code == 3
    assert fetching.FetchError("x").exit_code == 4
    assert fetching.UnresolvableError("x").exit_code == 5


def test_adapter_parse_error_is_not_a_resolve_error():
    assert not issubclass(fetching.AdapterParseError, fetching.ResolveError)


def test_http_get_returns_decoded_body(monkeypatch):
    monkeypatch.setattr(
        fetching.urllib.request, "urlopen",
        lambda request, timeout=None: _FakeResponse(b'{"ok": true}'),
    )

    assert fetching.http_get("https://example.com/x") == '{"ok": true}'


def test_http_get_raises_stale_message_on_404(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError("https://example.com/x", 404, "Not Found", {}, None)

    monkeypatch.setattr(fetching.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(fetching.FetchError) as excinfo:
        fetching.http_get("https://example.com/x")

    assert "no longer available" in str(excinfo.value)


def test_http_get_does_not_retry_on_404(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(1)
        raise urllib.error.HTTPError("https://example.com/x", 404, "Not Found", {}, None)

    monkeypatch.setattr(fetching.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(fetching.time, "sleep", lambda seconds: None)

    with pytest.raises(fetching.FetchError):
        fetching.http_get("https://example.com/x")

    assert len(calls) == 1


def test_http_get_retries_once_on_500_then_succeeds(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError("https://example.com/x", 500, "Boom", {}, None)
        return _FakeResponse(b"second try")

    monkeypatch.setattr(fetching.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(fetching.time, "sleep", lambda seconds: None)

    assert fetching.http_get("https://example.com/x") == "second try"
    assert len(calls) == 2


def test_http_get_gives_up_after_second_failure(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("dns is down")

    monkeypatch.setattr(fetching.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(fetching.time, "sleep", lambda seconds: None)

    with pytest.raises(fetching.FetchError):
        fetching.http_get("https://example.com/x")
