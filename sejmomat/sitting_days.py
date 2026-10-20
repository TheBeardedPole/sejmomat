"""Decide whether a scheduled update is worth running today.

The Sejm publishes its calendar (past and planned sittings). Updates run on
sitting days and for GRACE_DAYS after, to pick up late votes and corrections,
and in the LEAD_DAYS before a sitting, when its agenda is published and
changes. The hourly run (`python -m sejmomat.sitting_days hourly`) goes ahead
only on a sitting day itself, in HOURLY_HOURS (Warsaw time; the hours after
midnight count with the day before, as late sittings run past it).
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
HOURLY_HOURS = set(range(8, 24)) | {0, 1}
URL = f"https://api.sejm.gov.pl/sejm/term{TERM}/proceedings"


def sitting_dates():
    with urllib.request.urlopen(URL, timeout=60) as r:
        return {date.fromisoformat(d) for p in json.load(r) for d in p.get("dates", [])}


def should_run(today, dates):
    return any(today + timedelta(days=n) in dates for n in range(-GRACE_DAYS, LEAD_DAYS + 1))


def should_run_hourly(now, dates):
    """On a sitting day, in HOURLY_HOURS; 0:00–1:59 belongs to the day before."""
    day = (now - timedelta(hours=2)).date() if now.hour < 2 else now.date()
    return now.hour in HOURLY_HOURS and day in dates


def paused(today, until):
    """Scheduled runs are skipped before the date in PAUSE_SCHEDULED_UNTIL
    (a repository variable, YYYY-MM-DD); a past or malformed date is ignored."""
    try:
        return bool(until) and today < date.fromisoformat(until.strip())
    except ValueError:
        return False


if __name__ == "__main__":
    now = datetime.now(ZoneInfo("Europe/Warsaw")).replace(tzinfo=None)
    hourly = sys.argv[1:] == ["hourly"]
    if paused(now.date(), os.environ.get("PAUSE_SCHEDULED_UNTIL", "")):
        print("false")
        sys.exit()
    try:
        dates = sitting_dates()
        run = should_run_hourly(now, dates) if hourly else should_run(now.date(), dates)
    except Exception as e:  # calendar unavailable: better to run than to miss votes (but not every hour)
        print(f"calendar check failed ({e}); {'skipping' if hourly else 'running anyway'}", file=sys.stderr)
        run = not hourly
    print("true" if run else "false")
