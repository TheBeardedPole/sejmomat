"""MPs' professions in fields. The Sejm's API gives each MP's profession as they stated it ("prawnik",
"nauczyciel akademicki", "dziennikarz, prawnik": 161 wordings among 460 MPs), so for counts they are
put in a dozen fields by the first profession named, by the words in it, in the order below (the first
rule that matches wins: "inżynier rolnik" is farming before engineering). The profession as stated
is always shown beside the field."""
import re

# (field, words that put a profession in it), in order
FIELDS = [
    ("Polityka", r"parlamentarzyst|polityk|poseł|posłank|senator|działacz\w*\s+(?:\w+\s+)?polityczn"),
    ("Prawo", r"prawnik|prawniczk|adwokat|radc\w*\s+prawn|sędzi|prokurator|notariusz|komornik|aplikant|legislator|administratywist|prawo|syndyk|nadzorc\w*\s+sądow"),
    ("Zdrowie", r"lekar|pielęgniar|farmaceut|ratownik\s+medyczn|fizjoterapeut|stomatolog|dentyst|weteryn|położn|diagnost|psychiatr|chirurg|medyk"),
    ("Nauka", r"nauczyciel\w*\s+akademick|profesor|naukow|adiunkt|badacz|pracownik\s+naukow"),
    ("Edukacja", r"nauczyciel|pedagog|wychowaw|katechet|logoped|oligofrenopedagog|dyrektor\s+szkoły"),
    ("Rolnictwo", r"rolni|zootechnik|ogrodni|sadowni|leśni|hodowc|agronom|weterynaryjn"),
    ("Gospodarka i biznes", r"ekonomist|przedsiębior|menedżer|menadżer|manager|doradc\w*\s+podatkow|księgow|bankow|finans|handl|kontroling|"
                            r"rewident|marketing|analityk|kupiec|biznes|właściciel|prezes|przedsiębiorstw|logisty|ubezpiecze|specjalist\w*\s+(?:ds|do\s+spraw)|zarządza|konsultant|sprzedaw"),
    ("Administracja i samorząd", r"urzędni|administracj|administracyjn|administratyw|samorząd|wójt|burmistrz|prezydent|starost|dyplomat|sekretarz|wojewod"),
    ("Inżynieria i technika", r"inżynier|informatyk|programist|technolog|technik|mechanik|elektr|architekt|geodet|budowl|energetyk|automatyk|mechatronik|chemik|fizyk|matematyk"),
    ("Nauki społeczne i humanistyczne", r"politolog|socjolog|historyk|filolog|psycholog|filozof|kulturoznaw|europeist|stosunk|teolog|polonist|"
                                        r"archeolog|geograf|anglist|germanist|rusycyst|bibliotek|filoloż|teatrolo|archiwist|muzealn|pedagog\w*\s+społ|pracownik\s+socjaln|ekolog|biolog"),
    ("Media i kultura", r"dziennikar|aktor|muzyk|artyst|reżyser|wydawc|redaktor|publicyst|piosenkar|plastyk|fotograf|scenograf|pisarz|kompozytor"),
    ("Służby mundurowe", r"żołnierz|oficer|policjant|strażak|funkcjonariusz|wojskow|komandos|pilot|celnik|straż"),
    ("Sport", r"sportow|trener|piłkar|lekkoatlet|olimpij"),
]
_RULES = [(name, re.compile(words, re.I)) for name, words in FIELDS]
OTHER, UNKNOWN = "Inne", "Brak danych"
ORDER = [name for name, _ in FIELDS] + [OTHER, UNKNOWN]


def field(profession):
    """The field of a profession as stated (by its first profession), "Inne" or "Brak danych"."""
    p = (profession or "").strip()
    if not p:
        return UNKNOWN
    first = re.split(r"[,;/]|\s+i\s+", p)[0]
    for text in (first, p):     # the first profession named, else any word in the whole
        for name, rule in _RULES:
            if rule.search(text):
                return name
    return OTHER
