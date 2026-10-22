"""Legislative processes: every bill and draft resolution of the term with
the dated stages it has been through, from the API's processes records.

data/processes.json: {number: {"number", "title", "type", "submitted"
(processStartDate), "changed" (changeDate), "closed" (closureDate or None),
"passed", "urgency", "description" (what the bill is about, from the
Sejm), "prints" (considered jointly), "stages": [{"date",
"name", "decision", "committee", "depth"}]}}. A process is fetched again
only when the list gives it a newer changeDate; the first run asks for every
process (about 1,750 requests, run locally).

`frozen()` finds bills held up: not sent to a first reading by the Marshal,
or not taken up or not reported on by the committees they were sent to.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from . import api
from .config import DATA

PATH = DATA / "processes.json"
PAGE = 1000
WORKERS = 4
# types of process looked at for frozen bills: bills and draft resolutions
KINDS = {"BILL": "projekt ustawy", "DRAFT_RESOLUTION": "projekt uchwały"}


def _stages(stages, depth=0):
    out = []
    for s in stages or []:
        out.append({"date": s.get("date"), "name": s.get("stageName") or "", "decision": s.get("decision") or "",
                    "committee": s.get("committeeCode") or "", "depth": depth})
        out += _stages(s.get("children"), depth + 1)
    return out


def _one(summary):
    full = api.get(f"processes/{summary['number']}") or {}
    return {
        "number": summary["number"], "title": summary.get("title") or "",
        "type": summary.get("documentTypeEnum"), "submitted": summary.get("processStartDate"),
        "changed": summary.get("changeDate"), "closed": summary.get("closureDate"),
        "passed": bool(summary.get("passed")), "urgency": full.get("urgencyStatus"),
        "description": full.get("description") or "",
        "prints": summary.get("printsConsideredJointly") or [],
        "stages": _stages(full.get("stages")),
    }


def fetch():
    from .fetch import _write_json
    stored = load()
    listed, offset = [], 0
    while True:
        page = api.get(f"processes?limit={PAGE}&offset={offset}") or []
        listed += page
        if len(page) < PAGE:
            break
        offset += PAGE
    # also open ones stored before descriptions were kept (closed ones need none)
    todo = [p for p in listed if p.get("documentTypeEnum") in KINDS
            and (p["number"] not in stored or stored[p["number"]]["changed"] != p.get("changeDate")
                 or ("description" not in stored[p["number"]] and not p.get("closureDate")))]

    def save():
        _write_json(PATH, dict(sorted(stored.items(), key=lambda kv: (int(kv[0].split("-")[0]) if kv[0][:1].isdigit() else 0, kv[0]))))

    with ThreadPoolExecutor(WORKERS) as pool:
        for i, p in enumerate(pool.map(_one, todo), 1):
            stored[p["number"]] = p
            if i % 100 == 0:   # the first run is long: keep what is done
                save()
                print(f"processes: {i} of {len(todo)}", flush=True)
    save()
    print(f"processes: {len(listed)} listed, {len(todo)} fetched")


def load():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
