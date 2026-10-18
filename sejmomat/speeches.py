"""Speeches in the chamber: who spoke, when, on which agenda item, and what
they said, from the Sejm's transcripts (stenogramy), plus the day's video.

    python -m sejmomat speeches      # fetch what is missing (the first run takes hours)

One file per sitting day, data/speeches/<date>.json:

    {"date", "sitting", "day" (the sitting's 1st, 2nd... day),
     "videos": [{"start", "end", "link"}],   # the day's plenary stream(s)
     "statements": [{"num", "mp" (MP id or null), "name", "function",
                     "start", "end", "unspoken", "rapporteur",
                     "point" ("29. i 30."), "agenda": [item, ...],
                     "prints": [print numbers cited by the items], "text"}]}

"unspoken" speeches were handed in in writing ("tekst niewygłoszony"): they
have text but no video. The chair's running commentary (statement 0, a
transcript of its own for the whole day) is left out.

A day that is already stored is not fetched again, except the most recent
ones (REFRESH_DAYS), which get the statements published since; the text of
a statement is never fetched twice.
"""
import html
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import api
from .config import DATA
from .fetch import _write_json
from .refs import prints_in_title

SPEECHES = DATA / "speeches"
REFRESH_DAYS = 3
WORKERS = 4   # parallel requests: kind to the Sejm's server, yet hours rather than a day for a whole term

_PUNKT_RE = re.compile(r'<h2 class="punkt">(.*?)</h2>', re.S)
_TITLE_RE = re.compile(r'<p class="punkt-tytul">(.*?)</p>', re.S)
_SPEAKER_RE = re.compile(r'<h2 class="mowca">.*?</h2>', re.S)
_PARA_RE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.S)


def _plain(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_statement(page):
    """(point, agenda items, text) of one statement's transcript page.

    The page names the agenda item(s) ("29. i 30. punkt porządku dziennego:"
    followed by their titles, one per line), then the speaker, then the
    speech as paragraphs, interjections from the floor included as printed.
    """
    point = _PUNKT_RE.search(page)
    point = re.sub(r"\s*punkt\w* porządku dziennego:?\s*$", "", _plain(point[1])) if point else ""
    title = _TITLE_RE.search(page)
    agenda = [_plain(line) for line in re.split(r"<br\s*/?>", title[1], flags=re.I)] if title else []
    agenda = [line for line in agenda if line]
    speech = _SPEAKER_RE.split(page, maxsplit=1)
    paragraphs = [_plain(p) for p in _PARA_RE.findall(speech[1])] if len(speech) > 1 else []
    return point, agenda, "\n".join(p for p in paragraphs if p)


def _statement(meta, page):
    point, agenda, text = parse_statement(page) if page else ("", [], "")
    return {
        "num": meta["num"], "mp": meta.get("memberID") or None, "name": meta.get("name"),
        "function": meta.get("function") or "", "start": meta.get("startDateTime"), "end": meta.get("endDateTime"),
        "unspoken": bool(meta.get("unspoken")), "rapporteur": bool(meta.get("rapporteur")),
        "point": point, "agenda": agenda, "prints": prints_in_title(" ".join(agenda)), "text": text,
    }


def _videos(day):
    """The day's plenary video: the stream address takes a start and stop time."""
    return [{"start": v["startDateTime"], "end": v.get("endDateTime"), "link": v["videoLink"].split("?")[0]}
            for v in api.get(f"videos/{day}") or [] if v.get("type") == "posiedzenie" and v.get("videoLink")]


def fetch_day(sitting, day, old=None, number=None):
    """Fetch one day; statements already in `old` keep their text. None if
    the transcript is not published yet."""
    listing = api.get(f"proceedings/{sitting}/{day}/transcripts") or {}
    metas = [m for m in listing.get("statements") or [] if m.get("num")]
    if not metas:
        return None
    known = {s["num"]: s for s in (old or {}).get("statements", []) if s["text"]}
    todo = [m for m in metas if m["num"] not in known]
    with ThreadPoolExecutor(WORKERS) as pool:
        pages = dict(zip((m["num"] for m in todo),
                         pool.map(lambda m: api.get(f"proceedings/{sitting}/{day}/transcripts/{m['num']}", text=True), todo)))
    statements = [known[m["num"]] if m["num"] in known else _statement(m, pages[m["num"]]) for m in metas]
    return {"date": day, "sitting": sitting, "day": number, "videos": _videos(day), "statements": statements}


def fetch(limit=None):
    """Fetch every sitting day not stored yet (newest first), and refresh the
    latest stored ones. `limit`: at most this many days (for a test run)."""
    today = datetime.now(ZoneInfo("Europe/Warsaw")).date().isoformat()
    days = sorted(((d, p["number"], i) for p in api.get("proceedings") or [] if p.get("number")
                   for i, d in enumerate(sorted(p.get("dates") or []), 1) if d <= today), reverse=True)
    stored = sorted(p.stem for p in SPEECHES.glob("*.json"))
    refresh = set(stored[-REFRESH_DAYS:])
    done = 0
    for day, sitting, number in days:
        path = SPEECHES / f"{day}.json"
        if path.exists() and day not in refresh:
            stored_day = api.json_file(path)
            if stored_day.get("day") != number:  # files from before "day" was kept
                _write_json(path, {**stored_day, "day": number})
            continue
        old = api.json_file(path) if path.exists() else None
        out = fetch_day(sitting, day, old, number)
        if out is None:
            print(f"speeches {day}: no transcript yet")
            continue
        _write_json(path, out)
        new = len(out["statements"]) - len((old or {}).get("statements", []))
        print(f"speeches {day} (sitting {sitting}): {len(out['statements'])} statements, {new} new")
        done += 1
        if limit and done >= limit:
            break

# ------------------------------------------------------------- for the site

CLIP_PAD = 5  # seconds around a speech: its recorded times can be a few seconds off the video
PREVIEW = 300  # characters of a speech shown before "full text"
WARSAW = ZoneInfo("Europe/Warsaw")


def load():
    """Every stored sitting day, oldest first."""
    return [api.json_file(p) for p in sorted(SPEECHES.glob("*.json"))]


def topic(statement):
    """What a statement was about, short: its first agenda item without the
    item number and the print references."""
    item = statement["agenda"][0] if statement["agenda"] else ""
    item = re.sub(r"\s*\((?:druk|druki)\b[^)]*\)", "", re.sub(r"^\d+\.\s*", "", item))
    return item.rstrip(" .") or "—"


def _when(text):
    return datetime.fromisoformat(text).replace(tzinfo=WARSAW)


def clip(statement, videos):
    """Address of the day's video cut to this speech, or None (a speech handed
    in in writing, or no video for that time)."""
    if statement["unspoken"] or not statement["start"] or not statement["end"]:
        return None
    start, end = _when(statement["start"]), _when(statement["end"])
    # the listed times of a video are its scheduled ones: a speech may begin a little before
    slack = timedelta(minutes=2)
    video = next((v for v in videos if _when(v["start"]) - slack <= start
                  and (not v["end"] or end <= _when(v["end"]) + slack)), None)
    if not video:
        return None
    ms = lambda t: int(t.timestamp() * 1000)
    return f"{video['link']}?start={ms(start - timedelta(seconds=CLIP_PAD))}&stop={ms(end + timedelta(seconds=CLIP_PAD))}"


def _entry(d, st, bill, vote_for):
    """One speech as the site lists it."""
    seconds = None
    if not st["unspoken"] and st["start"] and st["end"]:
        seconds = max(0, int((_when(st["end"]) - _when(st["start"])).total_seconds()))
    return {
        "date": d["date"], "sitting": d["sitting"], "day": d.get("day"), "num": st["num"],
        "function": st["function"], "unspoken": st["unspoken"], "topic": topic(st), "agenda": st["agenda"],
        "bill": bill, "vote": vote_for(bill, d["sitting"]) if bill else None,
        "seconds": seconds, "clip": clip(st, d["videos"]), "text": st["text"],
    }


def bills_of(st, bill_of_print):
    """The bill pages a statement belongs to (a joint debate can cover two)."""
    return list(dict.fromkeys(b for b in map(bill_of_print, st["prints"]) if b))


def by_mp(days, bill_of_print, vote_for=lambda bill, sitting: None):
    """{MP id: [speech, ...] newest first}. bill_of_print(print number) gives
    the bill page's root print or None; vote_for(bill, sitting) the vote that
    settled the bill at that sitting, if any."""
    out = {}
    for d in days:
        for st in d["statements"]:
            if st["mp"] and st["text"]:
                bill = next(iter(bills_of(st, bill_of_print)), None)
                out.setdefault(st["mp"], []).append(_entry(d, st, bill, vote_for))
    for speeches in out.values():
        speeches.sort(key=lambda x: (x["date"], x["num"]), reverse=True)
    return out


def by_bill(days, bill_of_print, vote_for, club_at):
    """{bill root: [speech, ...] in the order they were given}: every speaker,
    MPs (with "mp" and their club at the time) and others (ministers...)."""
    out = {}
    for d in days:
        for st in d["statements"]:
            if not st["text"]:
                continue
            for bill in bills_of(st, bill_of_print):
                e = _entry(d, st, bill, vote_for)
                e.update({"mp": st["mp"], "name": st["name"],
                          "club": club_at(st["mp"], d["date"]) if st["mp"] else None})
                out.setdefault(bill, []).append(e)
    return out


def split_for_site(items):
    """An MP's speeches as two files: a list with a preview of each text
    (small, loaded first) and {"<date>#<num>": full text} (loaded only for
    a full text or a search in the texts; a busy MP's run to megabytes)."""
    listing, texts = [], {}
    for x in items:
        text = x["text"]
        cut = text if len(text) <= PREVIEW else text[:PREVIEW].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        listing.append({**{k: v for k, v in x.items() if k != "text"}, "key": f"{x['date']}#{x['num']}",
                        "preview": cut.split("\n")[0] if "\n" in cut[:PREVIEW] else cut, "long": cut != text or "\n" in text})
        texts[f"{x['date']}#{x['num']}"] = text
    return listing, texts


# ------------------------------------------------------------- word clouds

# Words that carry no subject: grammar, and the forms of address that open
# nearly every speech. Everything else is weighed against the whole chamber
# (Vocabulary.cloud), so words everyone uses rank low without being listed.
STOPWORDS = set("""
jest oraz które który która którzy których którym którą któremu tego temu tymi tych taki taka takie także
więc ponieważ gdyż kiedy gdzie jeżeli jeśli żeby aby czyli albo lecz jednak tylko nawet bardzo może można
będzie będą było były była został została zostały zostało mamy mają mieć jesteśmy jestem jesteście przez
przed przy pod nad dla bez między wśród według wobec poprzez właśnie teraz dzisiaj tutaj jego ich nich
nimi nami wami wasz nasz nasza nasze naszych naszym naszej naszego wasza wasze waszych waszego swoje swoich
swoim swojej swojego sobie siebie wszystko wszystkie wszystkich wszystkim każdy każda każde każdego coraz
jeszcze nigdy zawsze ktoś coś czego czym kogo komu jaki jaka jakie jakich jakim jakiej tamte tamten ponad
około również natomiast dlatego zatem właściwie oczywiście rzeczywiście naprawdę
panie pani panowie pań marszałku marszałek marszałkini izbo wysoka szanowni szanowny szanowna szanowne
dziękuję proszę oklaski chciałbym chciałabym chciałem chciałam powiedzieć mówić mówimy mówią mówię
chodzi stąd choćby prostu kilka musi musimy powinno powinien powinna będziemy więcej bardziej nadal mimo
ogóle momencie oznacza sposób kolejne kolejny dodatkowe myślę zgodnie związku ramach zarówno celu celem
niech skoro dlaczego godz moje mojego robimy roku latach wyraźnie niemal jasno jednocześnie dziś konkretne
drodzy cześć imieniu stanowisko popiera popieramy przedstawić zaszczyt przyjemność niniejszy wnoszę wnosi
""".split())
# Dictionary forms (see lemmas()) of words just as empty: auxiliary verbs,
# pronouns, degree words.
STOP_LEMMAS = set("""
być mieć móc musieć chcieć zostać stać dać iść wiedzieć powinien robić zrobić mówić powiedzieć uważać
jakiś jakikolwiek inny taki ten który swój nasz wasz mój twój cały sam każdy żaden pewien niektóry
bardzo często dużo wiele bardziej coraz właśnie także również jednak tylko więc
pan pani poseł posłanka sala izba państwo dzięki tysiąc milion miliard
styczeń luty marzec kwiecień maj czerwiec lipiec sierpień wrzesień październik listopad grudzień
""".split())
# Parts of speech that carry no subject: prepositions, conjunctions,
# particles, adverbs, numerals, pronouns, "trzeba"-like predicatives. A form
# is left out when every reading of it is one of these.
STOP_TAGS = {"prep", "conj", "comp", "part", "qub", "adv", "num", "numcol", "pred", "interj",
             "ppron12", "ppron3", "siebie", "aglt", "bedzie", "winien", "burk"}
PERSON = {"imię", "nazwisko"}   # Morfeusz's labels for first names and surnames
CAPITALISED = 0.7   # an MP's surname that is also a word ("Ziobro", "Duda"): left out when this share of its uses are capitalised
# A word's forms are put together by trimming endings (ustawa, ustawy,
# ustawie -> "ustaw"), then the "-ow-" that makes an adjective of a noun
# (podatkowy -> "podatk") and the "e" that comes and goes before a final
# "k" (podatek, podatku -> "podatk"). Crude rules, but enough to count
# subjects rather than grammar.
_ENDINGS = sorted("ami ach ych ich ymi imi owie owi ego emu iej ej ów om em ym im ie ia iu ii ią ię ę ą a y i u e o".split(),
                  key=len, reverse=True)
_WORD_RE = re.compile(r"[a-ząćęłńóśźż]{4,}")


def stem(word):
    for end in _ENDINGS:
        if word.endswith(end) and len(word) - len(end) >= 4:
            word = word[:-len(end)]
            break
    if word.endswith("ow") and len(word) >= 6:   # podatkow(y) -> podatk
        word = word[:-2]
    if word.endswith("ek") and len(word) >= 5:   # podatek -> podatk
        word = word[:-2] + "k"
    return word


def words(text):
    """A speech's words: lower case, without interjections from the floor
    (printed in brackets), short words and STOPWORDS."""
    return [w for w in _WORD_RE.findall(re.sub(r"\([^)]*\)", " ", text).lower()) if w not in STOPWORDS]


def lemmas(form_counts, names=()):
    """({word form: its dictionary form}, forms to leave out) by Morfeusz 2
    with the SGJP dictionary (morfeusz.sgjp.pl, BSD licence), or ({}, set())
    without it. A form with several readings (rolnicy: rolnik or rolnica) gets
    the dictionary form that is more common across all the forms counted.
    Left out: forms that are only function words (STOP_TAGS), only first
    names or surnames, or unknown to the dictionary and an MP's name
    (`names`, lower case: "zandberg", "wiplera")."""
    try:
        import morfeusz2
    except ImportError:
        return {}, set()
    analyser = morfeusz2.Morfeusz(generate=False)
    readings, weight, skip = {}, {}, set()
    for form, count in form_counts.items():
        analysed = [i[2] for i in analyser.analyse(form) if i[0] == 0]
        found = [(a[1].split(":")[0].lower(), a[2].split(":")[0]) for a in analysed if a[2] != "ign"]
        if not found:
            # without the name's last letter, so other forms match too (Wielichowska, Wielichowski)
            if any(form.startswith(n[:-1]) for n in names if len(n) >= 6):
                skip.add(form)
            continue
        known = [a for a in analysed if a[2] != "ign"]
        proper = [a for a in known if a[3] and "nazwa_pospolita" not in a[3]]   # names of people, places, …
        if all(tag in STOP_TAGS for _, tag in found) or (len(proper) == len(known) and any(set(a[3]) & PERSON for a in proper)):
            skip.add(form)
        # a noun over the verbal noun of the same word (pytanie, not pytać)
        if any(tag != "ger" for _, tag in found):
            found = [(lemma, tag) for lemma, tag in found if tag != "ger"]
        found = {lemma for lemma, _ in found}
        readings[form] = found
        for lemma in found:
            weight[lemma] = weight.get(lemma, 0) + count / len(found)
    dictionary = {form: max(found, key=lambda l: (weight[l], l)) for form, found in readings.items() if found}
    return dictionary, skip


def capitalised_names(texts, form_counts, dictionary, names):
    """Forms of MPs' names that are also ordinary words ("ziobro", "duda",
    but also "niedziela") which the speeches mostly write with a capital in
    mid-sentence: there they are surnames, so they are left out."""
    lemma_of = {f: dictionary.get(f, f) for f in form_counts if dictionary.get(f, f) in names}
    if not lemma_of:
        return set()
    upper = {}
    mid = re.compile(r"(?<=[a-ząćęłńóśźż,;] )([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]{3,})")
    for text in texts:
        for w in mid.findall(text):
            w = w.lower()
            if w in lemma_of:
                upper[w] = upper.get(w, 0) + 1
    total, caps = {}, {}
    for form, lemma in lemma_of.items():
        total[lemma] = total.get(lemma, 0) + form_counts[form]
        caps[lemma] = caps.get(lemma, 0) + upper.get(form, 0)
    surnames = {l for l in total if caps[l] >= CAPITALISED * total[l]}
    return {f for f, l in lemma_of.items() if l in surnames}


class Vocabulary:
    """Word counts of the whole chamber, to weigh a speaker's words against.

    Forms of one word count together: each form is taken to its dictionary
    form (lemmas()), then trimmed (stem()), which also joins words made from
    one another (podatkowy, podatek). Without the dictionary, trimming alone."""

    def __init__(self, texts, names=()):
        """`names`: MPs' first names and surnames, which are left out
        (see lemmas() and capitalised_names())."""
        texts = list(texts)
        names = {n.lower() for n in names}
        form_counts = {}
        for text in texts:
            for w in words(text):
                form_counts[w] = form_counts.get(w, 0) + 1
        dictionary, skip = lemmas(form_counts, names)
        skip |= capitalised_names(texts, form_counts, dictionary, names)
        # None: a form left out (a function word, a person's name, or its dictionary form in STOP_LEMMAS)
        self.key = {w: None if w in skip or dictionary.get(w) in STOP_LEMMAS else stem(dictionary.get(w, w))
                    for w in form_counts}
        self.counts, self.forms, self.heads = {}, {}, {}
        for w, c in form_counts.items():
            k = self.key[w]
            if k is None:
                continue
            self.counts[k] = self.counts.get(k, 0) + c
            self.forms.setdefault(k, {})[w] = c
            head = dictionary.get(w, w)  # what to show: the dictionary form
            heads = self.heads.setdefault(k, {})
            heads[head] = heads.get(head, 0) + c
        self.total = sum(form_counts.values())

    def form(self, key):
        """The word to show for a group of forms: its most common dictionary form."""
        return max(self.heads[key].items(), key=lambda kv: (kv[1], kv[0]))[0]

    def all_forms(self, key, limit=12):
        """The stem's most common forms, to search the texts for."""
        return [w for w, _ in sorted(self.forms[key].items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]

    def cloud(self, texts, size=40, min_count=4, min_texts=2, exclude=()):
        """[(word, weight 0-1, forms)] alphabetically: the words a speaker or a
        club uses markedly more than the chamber does (at least 1.5 times as
        often), at least `min_count` times in at least `min_texts` speeches,
        the top `size` by how often and how much more. `exclude`: words to
        leave out (a speaker's own name, which turns up in replies)."""
        exclude = {self.key.get(w.lower(), stem(w.lower())) for w in exclude}
        counts, docs, n = {}, {}, 0
        for text in texts:
            seen = set()
            for w in words(text):
                k = self.key.get(w)
                if k is None:  # left out, or not in the chamber's speeches
                    continue
                counts[k] = counts.get(k, 0) + 1
                seen.add(k)
                n += 1
            for k in seen:
                docs[k] = docs.get(k, 0) + 1
        scored = []
        for k, c in counts.items():
            if c < min_count or docs[k] < min_texts or k in exclude:
                continue
            ratio = (c / n) / ((self.counts.get(k, 0) + 1) / (self.total + 1))
            if ratio >= 1.5:
                scored.append((c * math.log(ratio), k))
        top = sorted(scored, reverse=True)[:size]
        if not top:
            return []
        high, low = top[0][0], top[-1][0]
        cloud = [(self.form(k), (score - low) / (high - low) if high > low else 1.0, self.all_forms(k))
                 for score, k in top]
        return sorted(cloud, key=lambda x: x[0])
