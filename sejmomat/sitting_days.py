"""Decide whether a scheduled update is worth running today.

The Sejm publishes its calendar (past and planned sittings). Updates run on
sitting days and for GRACE_DAYS after, to pick up late votes and corrections,
and in the LEAD_DAYS before a sitting, when its agenda is published and
changes.
Uses only the standard library so CI can call it before installing anything.
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import TERM

GRACE_DAYS = 2
LEAD_DAYS = 7
URL = f"https://api.sejm.gov.pl/sejm/term{TERM}/proceedings"


def sitting_dates():
    with urllib.request.urlopen(URL, timeout=60) as r:
        return {date.fromisoformat(d) for p in json.load(r) for d in p.get("dates", [])}


def should_run(today, dates):
    return any(today + timedelta(days=n) in dates for n in range(-GRACE_DAYS, LEAD_DAYS + 1))


def paused(today, until):
    """Scheduled runs are skipped before the date in PAUSE_SCHEDULED_UNTIL
    (a repository variable, YYYY-MM-DD); a past or malformed date is ignored."""
    try:
        return bool(until) and today < date.fromisoformat(until.strip())
    except ValueError:
        return False


if __name__ == "__main__":
    today = datetime.now(ZoneInfo("Europe/Warsaw")).date()
    if paused(today, os.environ.get("PAUSE_SCHEDULED_UNTIL", "")):
        print("false")
        sys.exit()
    try:
        run = should_run(today, sitting_dates())
    except Exception as e:  # calendar unavailable: better to run than to miss votes
        print(f"calendar check failed ({e}); running anyway", file=sys.stderr)
        run = True
    print("true" if run else "false")
