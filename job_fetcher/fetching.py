from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request

from job_fetcher.ats import USER_AGENT

TIMEOUT_SECONDS = 10
RETRY_BACKOFF_SECONDS = 2
MAX_ATTEMPTS = 2


class ResolveError(Exception):
    """Base for failures that map onto a CLI exit code."""

    exit_code = 5


class UsageError(ResolveError):
    exit_code = 2


class NeedsBrowser(ResolveError):
    exit_code = 3


class FetchError(ResolveError):
    exit_code = 4


class UnresolvableError(ResolveError):
    exit_code = 5


class AdapterParseError(Exception):
    """An adapter matched but its response did not parse.

    Deliberately not a ResolveError: this triggers degradation to the
    generic path rather than an exit code.
    """


def http_get(url: str, accept: str = "application/json") -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept}
    )
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise FetchError(f"posting no longer available (HTTP 404): {url}")
            if error.code < 500 or attempt == MAX_ATTEMPTS:
                raise FetchError(f"HTTP {error.code} fetching {url}")
        except urllib.error.URLError as error:
            if attempt == MAX_ATTEMPTS:
                raise FetchError(f"network error fetching {url}: {error.reason}")
        except (socket.timeout, TimeoutError):
            if attempt == MAX_ATTEMPTS:
                raise FetchError(f"timed out fetching {url}")
        time.sleep(RETRY_BACKOFF_SECONDS)
    raise FetchError(f"failed to fetch {url}")
