"""The Sejm's seating plan (the PDF the Chancellery publishes, "stan na …"), read into
data/seating.json: every MP's seat with its place in the hall, for the plan on the home
page (static/hall.js). Clubs come from the site's own data, not the plan's colours.

    python tools/seating.py ~/Downloads/stan_26.10.pdf

The plan is a vector drawing: pdftotext -bbox gives every label with its position.
Seats 34-501 are the MPs' (the others are guests, the government and staff); each name
is printed just above its seat's number. A name is matched to an MP by surname, with
the initials the plan adds where surnames repeat ("M. Suski", "M.M. Kołodziejczak").
Prints what it could not place, so a new plan can be checked by eye.
"""
import html
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "seating.json"
SEATS = range(34, 502)
UPPER = "A-ZĄĆĘŁŃÓŚŹŻ"


def fold(s):
    s = unicodedata.normalize("NFD", s.lower().replace("ł", "l"))
    return "".join(c for c in s if not unicodedata.combining(c)).replace(" ", "").replace("-", "")


def words(pdf):
    out = subprocess.run(["pdftotext", "-bbox", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    page = re.search(r'<page width="([\d.]+)" height="([\d.]+)"', out)
    ws = [(float(a), float(b), float(c), float(d), html.unescape(t)) for a, b, c, d, t in
          re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', out)]
    return ws, float(page.group(1)), float(page.group(2))


class Matcher:
    def __init__(self, mps):
        self.by_last, self.by_part = {}, {}
        for m in mps:
            last = m["lastName"]
            self.by_last.setdefault(fold(last), []).append(m)
            # a double surname the plan may print by one half ("Wiśniewska" for Uznańska-Wiśniewska)
            for p in last.split("-") if "-" in last else []:
                self.by_part.setdefault(fold(p), []).append(m)

    def __call__(self, label):
        """The MPs a label can name (one when it is clear)."""
        m = re.match(rf"^((?:[{UPPER}]\.\s?)+)?\s*(.+)$", label.strip())
        initials, last = re.findall(rf"[{UPPER}]", m.group(1) or ""), m.group(2)
        cands = self.by_last.get(fold(last), []) or self.by_part.get(fold(last), [])
        if not cands and " " in last:   # a first name written out ("Paweł Kowal")
            first, rest = last.split(" ", 1)
            cands = [x for x in self.by_last.get(fold(rest), []) if fold(x["firstLastName"]).startswith(fold(first))]
        if len(cands) > 1:
            given = lambda x: [p[0] for p in x["firstLastName"].split()[:-1]]   # noqa: E731
            if initials:
                # the initials are the first given names, in order ("M.M." = Magdalena Małgorzata)
                exact = [x for x in cands if given(x)[:len(initials)] == initials]
                # as many given names as initials first ("K. Bosak" is not Karina Anna, "K. A. Bosak")
                cands = [x for x in exact if len(given(x)) == len(initials)] or exact or cands
            else:
                # no initials where others have them: the one the plan does not mark
                cands = [x for x in cands if len(given(x)) and not any(
                    re.match(rf"^{given(x)[0]}\.", lab) for lab in self.marked.get(fold(last), []))] or cands
        return cands


def labels(ws):
    """Names: words on one line joined when the gap is a word space; a hyphen at a line's end
    joins the next line ("Semeniuk-" / "Patkowska")."""
    text = [w for w in ws if not re.fullmatch(r"[\d,]+", w[4])]
    rows = {}
    for w in text:
        rows.setdefault(round(w[1] * 2) / 2, []).append(w)
    groups = []
    for _, row in sorted(rows.items()):
        row.sort(key=lambda w: w[0])
        cur = [row[0]]
        for w in row[1:]:
            if w[0] - cur[-1][2] < 1.8 or cur[-1][4].endswith("-") or w[4].startswith("-"):
                cur.append(w)
            else:
                groups.append(cur)
                cur = [w]
        groups.append(cur)
    out = []
    for g in groups:
        t = " ".join(w[4] for w in g).replace("- ", "-").replace(" -", "-")
        out.append([t, (g[0][0] + g[-1][2]) / 2, (g[0][1] + g[0][3]) / 2])
    # a word ending in "-" with its other half on the line below
    for a in out:
        if a[0].endswith("-"):
            b = min((b for b in out if b is not a and 3 < b[2] - a[2] < 9 and abs(b[1] - a[1]) < 25),
                    key=lambda b: abs(b[1] - a[1]) + abs(b[2] - a[2]), default=None)
            if b:
                a[0] += b[0]
                a[2] = b[2]
                b[0] = ""
    return [tuple(x) for x in out if x[0]]


def main():
    pdf = Path(sys.argv[1]).expanduser()
    ws, width, height = words(pdf)
    mps = [m for m in json.loads((ROOT / "data" / "mps.json").read_text()) if m.get("active")]
    seats = {}
    for a, b, c, d, t in ws:
        # MPs' seats; not the legend's counts (top right), nor the front rows' labels (61-63 at the far left)
        if re.fullmatch(r"\d{2,3}", t) and int(t) in SEATS and not (a > 0.85 * width and b < 0.19 * height) \
                and not (int(t) in (61, 62, 63) and a < 0.052 * width):
            seats.setdefault(int(t), ((a + c) / 2, (b + d) / 2))
    match = Matcher(mps)
    labs = labels(ws)
    match.marked = {}
    for t, _, _ in labs:
        m = re.match(rf"^((?:[{UPPER}]\.\s?)+)\s*(.+)$", t)
        if m:
            match.marked.setdefault(fold(m.group(2)), []).append(t)
    # two neighbours printed as one line ("Zgorzelski Paszyk"): split where both halves are MPs
    named = []
    for t, x, y in labs:
        if match(t):
            named.append((t, x, y))
            continue
        parts = t.split(" ")
        for k in range(1, len(parts)):
            left, right = " ".join(parts[:k]), " ".join(parts[k:])
            if match(left) and match(right):
                named += [(left, x - 8, y), (right, x + 8, y)]
                break
    # each name with the seat just below it, nearest first; then the rest a little further
    pairs = []
    for i, (t, x, y) in enumerate(named):
        for n, (sx, sy) in seats.items():
            dx, dy = sx - x, sy - y
            if -6 < dy < 20 and abs(dx) < 26:
                pairs.append((abs(dx) * 1.2 + abs(dy - 7), i, n))
    pairs.sort()
    used_l, used_s, seat_of = set(), set(), {}
    for _, i, n in pairs:
        if i in used_l or n in used_s:
            continue
        used_l.add(i)
        used_s.add(n)
        seat_of[n] = i
    # names printed beside their seat (the hall's edges): the nearest free seat, a little further off
    late = sorted((abs(seats[n][0] - x) + abs(seats[n][1] - y), i, n) for i, (t, x, y) in enumerate(named) if i not in used_l
                  for n in seats if n not in used_s and abs(seats[n][0] - x) < 45 and -14 < seats[n][1] - y < 26)
    for _, i, n in late:
        if i in used_l or n in used_s:
            continue
        used_l.add(i)
        used_s.add(n)
        seat_of[n] = i
    out, placed, unclear = {}, set(), []
    for n, i in sorted(seat_of.items()):
        cands = [m for m in match(named[i][0]) if m["id"] not in placed]
        if len(cands) != 1:
            unclear.append((n, named[i][0], [m["firstLastName"] for m in cands]))
            continue
        placed.add(cands[0]["id"])
        x, y = seats[n]
        out[str(n)] = {"mp": cands[0]["id"], "x": round(x / width, 4), "y": round(y / height, 4), "label": named[i][0]}
    for n in seats:
        if str(n) not in out:   # an empty seat, or one we could not name: kept for the drawing
            x, y = seats[n]
            out.setdefault(str(n), {"mp": None, "x": round(x / width, 4), "y": round(y / height, 4)})
    OUT.write_text(json.dumps({"source": pdf.name, "aspect": round(width / height, 4), "seats": out},
                              ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    missing = [m["firstLastName"] for m in mps if m["id"] not in placed]
    print(f"{OUT.relative_to(ROOT)}: {len(seats)} seats, {len(placed)} MPs placed")
    print("unclear:", unclear)
    print("names without a seat:", [named[i][0] for i in range(len(named)) if i not in used_l])
    print(f"active MPs not on the plan ({len(missing)}):", missing)


if __name__ == "__main__":
    main()
