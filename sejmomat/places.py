"""Towns by constituency, so a reader can find the MPs of a town that is not their
constituency's seat (Grudziądz is in no. 5, "Toruń"): data/districts.json, the cities with
powiat rights and the powiat seats of each constituency, read by tools/districts.py. The MP
list (templates/mps.html) and the seating plan's search (dane/sala.json, static/home.js) use it."""
import json

from .config import DATA


def by_district():
    """{constituency number: [town, …]} sorted; {} without the file."""
    path = DATA / "districts.json"
    if not path.exists():
        return {}
    districts = json.loads(path.read_text(encoding="utf-8"))
    return {int(num): sorted(set(d.get("cities", [])) | set(d.get("seats", []))) for num, d in districts.items()}
