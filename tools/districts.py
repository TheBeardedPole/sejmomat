"""The Sejm's 41 constituencies by place, into data/districts.json: for each constituency the
cities with powiat rights, the powiats and their seats, so a reader can find the MPs of a
town that is not the constituency's seat (Grudziądz is in no. 5, "Toruń"; Gliwice in no. 29,
"Katowice"). Used by the MP list and the seating plan's search (sejmomat/interests.py).

    python tools/districts.py          # the constituencies not yet in the file
    python tools/districts.py --all    # every one again

Read once from Polish Wikipedia: each constituency's article names its cities and powiats
(as in the Electoral Code's annex), and each powiat's article its seat. About 400 requests,
a few minutes; redo it if the constituencies are redrawn. Prints anything it could not read.
"""
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "districts.json"
API = "https://pl.wikipedia.org/w/api.php"
session = requests.Session()
session.headers["User-Agent"] = "sejmomat (open data viewer; https://sejmomat.pl)"


def wikitext(title):
    for attempt in range(3):
        try:
            r = session.get(API, params={"action": "parse", "page": title, "prop": "wikitext", "redirects": 1,
                                         "format": "json"}, timeout=30)
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                return None
            return data["parse"]["wikitext"]["*"]
        except requests.RequestException:
            time.sleep(2 + attempt * 3)
    return None


LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]")


def district(num):
    """The cities with powiat rights and the powiats (their article titles) of one constituency."""
    text = wikitext(f"Okręg wyborczy nr {num} do Sejmu Rzeczypospolitej Polskiej")
    if not text:
        return None
    # the sentence that begins "Okręg … obejmuje obszar …" up to the voivodeship in brackets
    m = re.search(r"obejmuje(.*?)\(\[\[województwo", text, re.S)
    if not m:
        # a whole voivodeship ("obejmuje obszar [[Województwo lubuskie|…]]"): its powiats, whose
        # seats include its cities with powiat rights
        whole = re.search(r"obejmuje obszar \[\[[Ww]ojewództwo ([^\]|]+)", text)
        return ([], voivodeship_powiats(whole.group(1).strip())) if whole else None
    cities, powiats = [], []
    for title in LINK_RE.findall(m.group(1)):
        t = title.strip()
        if t.lower().startswith("powiat"):
            powiats.append(t[0].upper() + t[1:])
        elif not t.lower().startswith(("województwo", "miasto na prawach", "statek", "zagranic")):
            cities.append(t)
    return cities, powiats


def voivodeship_powiats(name):
    """The powiats of a voivodeship ("lubuskie"), from Wikipedia's category of them."""
    locative = {"lubuskie": "lubuskim", "opolskie": "opolskim", "podlaskie": "podlaskim", "świętokrzyskie": "świętokrzyskim"}
    r = session.get(API, params={"action": "query", "list": "categorymembers", "cmlimit": 100, "format": "json",
                                 "cmtitle": f"Kategoria:Powiaty w województwie {locative.get(name, name)}"}, timeout=30)
    return [m["title"] for m in r.json()["query"]["categorymembers"] if m["ns"] == 0 and m["title"].startswith("Powiat ")]


def seat(powiat):
    """A powiat's seat, from its article's infobox."""
    text = wikitext(powiat)
    m = text and re.search(r"\|\s*siedziba\s*=\s*\[\[([^\]|]+)", text)
    return m.group(1).strip() if m else None


def town(title):
    """The town's name from its article's title: "Brodnica (miasto)" → "Brodnica"."""
    return re.sub(r"\s*\(.*\)$", "", title)


def main():
    # constituencies already read are kept (python tools/districts.py --all reads them all again)
    out = {} if "--all" in sys.argv or not OUT.exists() else json.loads(OUT.read_text(encoding="utf-8"))
    missing = []
    for num in range(1, 42):
        if str(num) in out:
            continue
        got = district(num)
        if not got:
            missing.append(f"constituency {num}")
            continue
        cities, powiats = got
        seats = []
        for p in powiats:
            s = seat(p)
            if s:
                seats.append(town(s))
            else:
                missing.append(f"{num}: seat of {p}")
            time.sleep(0.2)
        out[str(num)] = {"cities": sorted({town(c) for c in cities}), "powiats": sorted(town(p).split(" ", 1)[1] for p in powiats),
                    "seats": sorted(set(seats))}
        print(num, len(cities), "cities,", len(powiats), "powiats", file=sys.stderr)
    out = dict(sorted(out.items(), key=lambda kv: int(kv[0])))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for m in missing:
        print("not read:", m)


if __name__ == "__main__":
    main()
