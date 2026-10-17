"""Interpellations and written questions (zapytania poselskie): who asked
whom, when, and when and whether the government answered.

Both lists come 500 to a request, so the whole term is fetched each time
(some 50 requests): replies keep arriving for old questions. Kept in
data/questions.json without the texts, which stay on the Sejm's site.
A minister has 21 days to answer; the API gives how many days a reply is
overdue (answerDelayedDays) for each recipient.
"""
import json
from datetime import date

from . import api
from .config import DATA

PATH = DATA / "questions.json"
KINDS = {"interpellations": "int", "writtenQuestions": "zap"}   # API list, kind on the Sejm's site
PAGE = 500


def _compact(q):
    web = next((l["href"] for l in q.get("links") or [] if l.get("rel") == "web-description"), None)
    return {
        "num": q["num"], "title": q.get("title") or "",
        "from": [int(x) for x in q.get("from") or [] if str(x).isdigit()],
        "to": [r["name"] for r in q.get("recipientDetails") or []] or q.get("to") or [],
        "received": q.get("receiptDate"), "sent": q.get("sentDate"),
        "late": {r["name"]: r.get("answerDelayedDays") or 0 for r in q.get("recipientDetails") or []},
        "replies": [{"date": r.get("receiptDate"), "from": r.get("from"), "prolongation": bool(r.get("prolongation"))}
                    for r in q.get("replies") or []],
        "web": web,
    }


def fetch():
    out = {}
    for kind in KINDS:
        items, offset = [], 0
        while True:
            page = api.get(f"{kind}?limit={PAGE}&offset={offset}&sort_by=num") or []
            items += [_compact(q) for q in page]
            if len(page) < PAGE:
                break
            offset += PAGE
        out[kind] = items
    from .fetch import _write_json
    _write_json(PATH, out)
    print(f"questions: {len(out['interpellations'])} interpellations, {len(out['writtenQuestions'])} written questions")


def load():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {k: [] for k in KINDS}


def answered(q):
    """A real answer, not only a notice that the deadline was extended."""
    return any(not r["prolongation"] for r in q["replies"])


def days_to_answer(q):
    """Days from sending the question to the first real answer, or None."""
    first = min((r["date"] for r in q["replies"] if not r["prolongation"] and r["date"]), default=None)
    start = q["sent"] or q["received"]
    if not first or not start:
        return None
    return (date.fromisoformat(first) - date.fromisoformat(start)).days
