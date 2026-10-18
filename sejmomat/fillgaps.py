"""Uzupełnij słowo (Sejmdle): excerpts of real speeches with words left out.

Three rounds a day, with 2, 3 and 4 blanks. Each round is a passage of two to
four sentences from a speech an MP actually delivered, the speakers' clubs in
turn (the current clubs, largest first), so no side gets more of the game
than another. The words left out are nouns and adjectives the chamber uses
often enough to be guessed from the context, never the first word of a
sentence or a name. For each blank the game gets the word as said and its
other forms (Morfeusz 2 / SGJP), so the right word in another form earns
partial credit.

A day's puzzles use only speeches from at least two days before it, so new
data does not change days already played. The build writes one small file a
day (api/v1/slowa/<day>.json), from FIRST_DAY to AHEAD days on, since the
site is not rebuilt every day.
"""
import hashlib
import re
from datetime import date, timedelta

from .speeches import STOPWORDS, topic

FIRST_DAY = date(2026, 10, 1)   # as Sejmdle's other daily games (#1)
AHEAD = 60
BLANKS = (2, 3, 4)
MIN_COUNT = 40          # how often the chamber says a word for it to be fair game
MIN_GAP = 3             # words between two blanks
SENTENCES = (2, 4)
LENGTH = (180, 460)     # characters in a passage
# sentences that are forms of address, thanks or procedure, not substance
SKIP = re.compile(r"marszał|wysoka izbo|panie pośle|pani poseł|szanown|dziękuję|oklaski|proszę państwa|pani premier|panie premierze|panie ministrze|pani minister", re.I)
SENTENCE = re.compile(r"(?<=[.!?…])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ„\"])")
WORD = re.compile(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+")
CONTENT_TAGS = {"subst", "adj"}
# passages about parties or people read as one side's attack on another: left out
PARTISAN = re.compile(r"\b(PiS|PO|KO|PSL|Platform\w*|Prawo i Sprawiedliwość|Prawa i Sprawiedliwości|Koalicj\w* Obywatelsk\w*|"
                      r"Konfederac\w*|Lewic\w*|Razem|Polsk\w* 2050|Trzeci\w* Drog\w*|Centrum|Republikan\w*|"
                      r"Tusk\w*|Kaczyńsk\w*|Morawieck\w*|Nawrock\w*|Trzaskowsk\w*|Hołowni\w*|Bosak\w*|Mentzen\w*|"
                      r"Czarzast\w*|Kosiniak\w*|Ziobr\w*|Szydł\w*|Dud\w*)\b")


def _rank(*parts):
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()


class Forms:
    """A word's dictionary form and all its forms, by Morfeusz 2."""

    def __init__(self):
        import morfeusz2
        self.analyser = morfeusz2.Morfeusz(generate=False)
        self.generator = morfeusz2.Morfeusz(generate=True)
        self._forms = {}

    def lemma(self, word):
        """The dictionary form of a noun or adjective reading, or None."""
        for _, _, (orth, lemma, tag, *_rest) in self.analyser.analyse(word):
            if tag.split(":")[0] in CONTENT_TAGS:
                return lemma.split(":")[0].lower()
        return None

    def forms(self, lemma):
        if lemma not in self._forms:
            self._forms[lemma] = sorted({g[0].lower() for g in self.generator.generate(lemma)
                                         if g[2].split(":")[0] in CONTENT_TAGS and len(g[0]) >= 3})
        return self._forms[lemma]


def passage(text, salt, surnames=frozenset()):
    """Two to four sentences from the middle of a speech, or None. Passages
    naming parties, clubs or MPs are left out (see PARTISAN)."""
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    sentences = [s for s in SENTENCE.split(text) if s and not SKIP.search(s)]
    windows = []
    for start in range(len(sentences)):
        for size in range(SENTENCES[0], SENTENCES[1] + 1):
            chunk = " ".join(sentences[start:start + size])
            if start + size <= len(sentences) and LENGTH[0] <= len(chunk) <= LENGTH[1] and not PARTISAN.search(chunk) \
                    and not any(w in surnames for w in WORD.findall(chunk) if w[0].isupper()):
                windows.append(chunk)
    return min(windows, key=lambda w: _rank(salt, w)) if windows else None


def blanks(text, n, vocabulary, forms, salt):
    """`n` words to leave out: [(start, end, word, other forms)], or None."""
    tokens = list(WORD.finditer(text))
    # a word whose dictionary form comes up again in the passage would give itself away
    seen = {}
    for m in tokens:
        lemma = forms.lemma(m.group().lower()) or m.group().lower()
        seen[lemma] = seen.get(lemma, 0) + 1
    candidates = []
    for i, m in enumerate(tokens):
        word = m.group()
        low = word.lower()
        before = text[:m.start()].rstrip()
        if (len(low) < 5 or low in STOPWORDS or word[0].isupper() or not before or before[-1] in ".!?…:"):
            continue
        key = vocabulary.key.get(low)
        if key is None or vocabulary.counts.get(key, 0) < MIN_COUNT:
            continue
        lemma = forms.lemma(low)
        if not lemma or seen.get(lemma, 0) > 1:
            continue
        candidates.append((i, m, lemma))
    chosen = []
    for i, m, lemma in sorted(candidates, key=lambda c: _rank(salt, c[1].start())):
        if all(abs(i - j) > MIN_GAP for j, _, _ in chosen) and lemma not in {l for _, _, l in chosen}:
            chosen.append((i, m, lemma))
        if len(chosen) == n:
            break
    if len(chosen) < n:
        return None
    return [(m.start(), m.end(), m.group(), [f for f in forms.forms(lemma) if f != m.group().lower()])
            for _, m, lemma in sorted(chosen, key=lambda c: c[1].start())]


def puzzles(days, vocabulary, club_rows, club_at, names, today):
    """{day (ISO): [round, round, round]} from FIRST_DAY to AHEAD days after `today`."""
    forms = Forms()
    surnames = frozenset(n.split()[-1] for n in names.values() if n)
    clubs = [c["id"] for c in sorted((c for c in club_rows if c["current"] and len(c["members"]) >= 3),
                                     key=lambda c: -len(c["members"]))]
    by_club = {c: [] for c in clubs}
    for d in days:
        for st in d["statements"]:
            if not st.get("mp") or st.get("unspoken") or st.get("function", "Poseł") not in ("Poseł", "Posłanka"):
                continue
            if len(st.get("text") or "") < 600:
                continue
            club = club_at(int(st["mp"]), d["date"])
            if club in by_club:
                by_club[club].append((d["date"], st))
    out = {}
    day, last = FIRST_DAY, today + timedelta(days=AHEAD)
    while day <= last:
        number = (day - FIRST_DAY).days
        until = (day - timedelta(days=2)).isoformat()   # only speeches from at least two days before
        rounds = []
        for k, n in enumerate(BLANKS):
            for shift in range(len(clubs)):
                club = clubs[(number * len(BLANKS) + k + shift) % len(clubs)]
                pool = sorted((x for x in by_club[club] if x[0] <= until), key=lambda x: _rank(day, k, x[0], x[1]["num"]))
                found = None
                for when, st in pool[:200]:
                    text = passage(st["text"], f"{day}|{k}", surnames)
                    picked = text and blanks(text, n, vocabulary, forms, f"{day}|{k}")
                    if picked:
                        found = (when, st, text, picked)
                        break
                if found:
                    break
            if not found:
                continue
            when, st, text, picked = found
            parts, pos = [], 0
            for b, (start, end, _, _) in enumerate(picked):
                parts += [text[pos:start], b]
                pos = end
            parts.append(text[pos:])
            mp = int(st["mp"])
            rounds.append({
                "parts": parts,
                "blanks": [{"answer": word, "forms": other} for _, _, word, other in picked],
                "who": {"mp": mp, "name": names.get(mp, st.get("name") or ""), "club": club, "date": when, "topic": topic(st)},
            })
        out[day.isoformat()] = rounds
        day += timedelta(days=1)
    return out
