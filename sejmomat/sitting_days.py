"""Decide whether a scheduled update is worth running today.

The Sejm publishes its calendar (past and planned sittings). Updates run on
sitting days and for GRACE_DAYS after, to pick up late votes and corrections.
Uses only the standard library so CI can call it before installing anything.
"""
import json
import sys
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import TERM

GRACE_DAYS = 2
URL = f"https://api.sejm.gov.pl/sejm/term{TERM}/proceedings"


def sitting_dates():
    with urllib.request.urlopen(URL, timeout=60) as r:
        return {date.fromisoformat(d) for p in json.load(r) for d in p.get("dates", [])}


def should_run(today, dates):
    return any(today - timedelta(days=n) in dates for n in range(GRACE_DAYS + 1))


if __name__ == "__main__":
    today = datetime.now(ZoneInfo("Europe/Warsaw")).date()
    try:
        run = should_run(today, sitting_dates())
    except Exception as e:  # calendar unavailable: better to run than to miss votes
        print(f"calendar check failed ({e}); running anyway", file=sys.stderr)
        run = True
    print("true" if run else "false")
