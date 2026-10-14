"""Thin client for api.sejm.gov.pl with retries."""
import json
import time

import requests

from .config import TERM

BASE = f"https://api.sejm.gov.pl/sejm/term{TERM}"
ELI = "https://api.sejm.gov.pl/eli"

_session = requests.Session()
_session.headers["User-Agent"] = "sejmomat (open data viewer)"


def get(path, *, binary=False, text=False, retries=5, base=BASE):
    """GET a path under the term base URL (or `base`): JSON, or bytes
    (`binary`), or a string (`text`, e.g. an HTML transcript). None on 404."""
    url = f"{base}/{path}"
    for attempt in range(retries):
        try:
            r = _session.get(url, timeout=60)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            if binary and not r.content.startswith(b"%PDF") and b"<html" in r.content[:200].lower():
                # the API answers some overload errors with an HTML page and 200
                raise requests.HTTPError("HTML error page instead of a document")
            return r.content if binary else r.text if text else r.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def json_file(path):
    return json.loads(path.read_text(encoding="utf-8"))
