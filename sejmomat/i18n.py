"""Interface strings for the English edition.

Templates and Python labels are written in Polish; `translator("en")` maps
them to English. Legal text and data from the API (topics, titles, amendment
text) are never translated.
"""
from datetime import datetime

LANGS = ("pl", "en")

MONTHS = {
    "pl": ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca",
           "sierpnia", "września", "października", "listopada", "grudnia"],
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
}

EN = {
    # speeches on MP pages
    "Wystąpienia": "Speeches", "Wszystkie wystąpienia": "All speeches", "Charakterystyczne słowa": "Characteristic words",
    "Szukaj w wystąpieniach": "Search the speeches",
    "Słowa używane w wystąpieniach znacznie częściej niż średnio na sali plenarnej, w formie słownikowej: odmiany i słowa pochodne liczone są razem (słownik Morfeusz 2 / SGJP). Im większe, tym częstsze i bardziej charakterystyczne.":
        "Words used in these speeches markedly more often than in the chamber on average, in their dictionary form: inflected forms and derived words counted together (Morfeusz 2 / SGJP dictionary). The larger, the more frequent and characteristic.",
    "Wystąpienia posłów w czasie, gdy należeli do tego klubu lub koła.": "Speeches by MPs while they belonged to this club or group.",
    "Najczęściej zabierają głos": "Speak most often", "Kto zabierał głos w debatach nad projektem": "Who spoke in the debates on the bill",
    "osoby spoza Sejmu (rząd, goście)": "speakers from outside the Sejm (government, guests)",
    "Szukaj w treści i wśród mówców": "Search the texts and speakers", "Cała debata": "Whole debate",
    "debata nad projektem": "debate on the bill", "wystąpień": "speeches",
    "wystąpień na sali plenarnej": "speeches in the chamber", "Wystąpienia na sali plenarnej": "Speeches in the chamber",
    "wygłoszonych": "delivered", "łącznie": "in all", "godz.": "h", "złożonych na piśmie": "handed in in writing",
    "Najczęstsze tematy": "Most frequent topics", "Nie udało się wczytać wystąpień.": "The speeches could not be loaded.",
    "Spróbuj ponownie": "Try again", "Szukaj w tematach i treści wystąpień": "Search topics and texts of the speeches",
    "Wystąpienia: {n} z {all}": "Speeches: {n} of {all}",
    "Wczytywanie pełnych tekstów do wyszukiwania…": "Loading the full texts to search them…", "Pokaż więcej": "Show more", "Cały tekst": "Full text",
    "Wideo": "Video", "Stenogram": "Transcript", "złożone na piśmie": "handed in in writing",
    "Nie udało się odtworzyć nagrania. Spróbuj w stenogramie na stronie Sejmu.":
        "The video could not be played. Try the transcript on the Sejm's website.",
    "Pokaż wystąpienia: treść i wideo": "Show the speeches: text and video",
    "Tekst ze stenogramów Sejmu; wideo z transmisji Sejmu, przycięte do czasu wystąpienia zapisanego w stenogramie.":
        "Text from the Sejm's transcripts; video from the Sejm's broadcast, cut to the speech's time as recorded in the transcript.",
    # votes by sitting on MP and club pages
    "Głosowania według posiedzeń": "Votes by sitting",
    "Kliknij posiedzenie, aby zobaczyć każde głosowanie: głos posła, linię klubu i opuszczone głosowania.":
        "Click a sitting to see every vote: the MP's ballot, the club line and the votes missed.",
    "Kliknij posiedzenie, aby zobaczyć każde głosowanie i posłów klubu: kto nie głosował, kto wyłamał się z linii.":
        "Click a sitting to see every vote and the club's MPs: who did not vote, who broke the line.",
    "Opuszczone": "Missed", "Wbrew klubowi": "Against club line", "wszystkie opuszczone": "all missed",
    "opuszczonych głosowań": "votes missed", "Wszystkie": "All", "Nr": "No.",
    "Opuszczone głosowanie to takie, w którym poseł był uprawniony do udziału, ale nie oddał głosu.":
        "A missed vote is one the MP was entitled to take part in but cast no ballot.",
    "linia: za": "line: for", "Nieoddane głosy": "Ballots not cast",
    "Nieoddane głosy: odsetek głosów, których posłowie klubu nie oddali, choć byli uprawnieni (nieobecność lub brak udziału w głosowaniu).":
        "Ballots not cast: the share of ballots the club's MPs did not cast although entitled to (absent, or present but not voting).",
    "Posłowie klubu na tym posiedzeniu": "The club's MPs at this sitting", "Wczytywanie…": "Loading…",
    "Nie udało się wczytać głosowań. Kliknij ponownie, aby spróbować jeszcze raz.": "The votes could not be loaded. Click again to retry.",
    "Brak głosowań.": "No votes.",
    "Jak głosowały kluby i ich posłowie na tym posiedzeniu": "How the clubs and their MPs voted at this sitting",
    # day summaries (the posts themselves stay in Polish)
    "Podsumowania dni": "Daily summaries",
    "Podsumowania dni — opis": "The key figures from every voting day in the Sejm: laws passed, amendments adopted and how the clubs voted on the most contested law, with numbers taken straight from the data.",
    "Najważniejsze liczby z każdego dnia głosowań w Sejmie: ile ustaw uchwalono, czyje poprawki przeszły i które głosowanie było najbardziej sporne.":
        "The key figures from every voting day in the Sejm: how many laws were passed, whose amendments got through and which vote was the most contested.",
    "Uchwalone ustawy": "Laws passed", "Podjęte uchwały": "Resolutions adopted", "Odrzucone projekty": "Bills rejected",
    "Głosowania nad poprawkami": "Votes on amendments", "w tym przyjęte": "adopted",
    "Rozstrzygnięcia wbrew rekomendacji komisji": "Decided against the committee's recommendation",
    "Najbardziej sporne głosowanie nad ustawą": "Most contested vote on a law", "Czyje poprawki przeszły?": "Whose amendments passed?",
    "przyjęte / głosowane": "adopted / voted", "Wszystkie głosowania tego dnia": "All votes of the day",
    "Grafika do udostępnienia": "Image to share (in Polish)", "Kadencja": "Term",
    "Przygotowywanie…": "Preparing…", "Nie udało się przygotować grafiki.": "The image could not be made.",
    "Udostępnij": "Share", "Skopiowano link": "Link copied", "Za": "For", "Przeciw": "Against",
    "Gotowe grafiki i wpisy do mediów społecznościowych po każdym dniu głosowań. Liczby i nazwy pochodzą wprost z danych, bez komentarza.":
        "Ready-made images and social media posts after every voting day. Numbers and names come straight from the data, without commentary.",
    "Grafiki i wpisy są po polsku. Przycisk serwisu otwiera go z gotową treścią: nic nie zostanie opublikowane bez Twojego kliknięcia.":
        "The images and posts are in Polish. A service's button opens it with the text filled in: nothing is published without your click.",
    "Wpis do grafiki": "Post to go with the image", "Pobierz grafikę": "Download the image",
    "Udostępnij z grafiką": "Share with the image", "Wersja tekstowa (bez grafiki)": "Text version (no image)",
    "X i Bluesky otwierają się z samym tekstem — grafikę trzeba dołączyć ręcznie.":
        "X and Bluesky open with the text only — the image has to be attached by hand.",
    "Jeden wpis": "Single post", "Nitka": "Thread", "Kopiuj": "Copy", "Skopiowano": "Copied",
    "Kopiuj całą nitkę": "Copy the whole thread", "znaków": "characters",
    "Podsumowania dni głosowań": "Voting day summaries",
    "podsumowania ostatnich dni głosowań: liczby, grafiki i gotowe wpisy do mediów społecznościowych":
        "summaries of the latest voting days: figures, images and ready-made social media posts",
    # navigation & layout
    "Posiedzenia": "Sittings",
    "Ustawy": "Bills",
    "Kluby": "Clubs",
    "Posłowie": "MPs",
    "Skuteczne poprawki": "Adopted amendments",
    "Poprawki": "Amendments", "Wszystkie poprawki": "All amendments",
    "wszystkie głosowane poprawki i wnioski": "every amendment and motion put to a vote",
    "Poprawki — opis": "Every amendment, minority motion and Senate amendment the Sejm voted on this term, adopted or rejected, with its proposer and the committee's recommendation.",
    "projektów rozstrzygniętych w całości": "bills decided as a whole",
    "uchwalonych ustaw i uchwał": "bills and resolutions passed",
    "przyjętych poprawek i wniosków": "amendments and motions adopted",
    "Projekty, nad którymi głosowano w całości": "Bills voted on as a whole",
    "Szukaj": "Search",
    "Metodologia": "Methodology",
    "Głosowania w Sejmie: pokazane jak należy.": "Polish Sejm votes, shown properly.",
    "Poprawki w odpowiednim kontekście, lepsze statystyki, podsumowania danych.":
        "Amendments in their proper context, better statistics, summaries of the data.",
    "Dane": "Data",
    "API Sejmu RP": "Sejm API",
    "kadencja": "term",
    "Treść poprawek wyodrębniana automatycznie z druków sejmowych — w razie wątpliwości rozstrzyga oficjalny druk.":
        "Amendment texts are extracted automatically from Sejm prints — the official print is authoritative. Legal texts are in Polish.",
    "Wygenerowano": "Generated",
    "Kod źródłowy": "Source code",
    "Tryb ciemny": "Dark mode",
    "były członek": "former member", "Byli członkowie": "Former members", "W klubie": "In the club", "Obecnie": "Now",
    "Posłowie, którzy głosowali jako członkowie tego klubu lub koła, a dziś do niego nie należą.":
        "MPs who voted as members of this club or group and no longer belong to it.",
    "Sekcje": "Sections", "Zgodność": "Agreement", "Poprawki i wnioski": "Amendments and motions",
    "Wesprzyj projekt": "Support the project",
    "Prywatność": "Privacy",
    "Prywatność — opis": "Sejmomat uses no cookies, tracking or ads. What the hosting provider logs, what is kept in your browser, and where the data about MPs comes from.",
    "Domyślny opis": "Every vote in the Polish Sejm linked to the amendment it concerns: full text, sponsor, committee recommendation and results by parliamentary club.",
    # votes
    "za": "for", "przeciw": "against", "wstrzymał(a) się": "abstained", "nie głosował(a)": "did not vote",
    "wstrzymanie się": "abstain", "wstrzymało się": "abstained", "nie głosowało": "did not vote",
    "wstrz.": "abst.", "nie gł.": "no vote",
    "Przyjęto": "Passed", "Odrzucono": "Rejected",
    "Poprawka przyjęta": "Amendment adopted", "Poprawka odrzucona": "Amendment rejected",
    "Poprawki przyjęte": "Amendments adopted", "Poprawki odrzucone": "Amendments rejected",
    "Wniosek mniejszości przyjęty": "Minority motion adopted", "Wniosek mniejszości odrzucony": "Minority motion rejected",
    "Wnioski mniejszości przyjęte": "Minority motions adopted", "Wnioski mniejszości odrzucone": "Minority motions rejected",
    "Poprawka Senatu przyjęta": "Senate amendment accepted", "Poprawka Senatu odrzucona": "Senate amendment rejected",
    "wbrew komisji": "against committee",
    "Wynik niezgodny z rekomendacją komisji": "Outcome differs from the committee's recommendation",
    "zwykła większość": "simple majority",
    "bezwzględna większość": "absolute majority",
    "bezwzględna większość ustawowej liczby posłów": "absolute majority of the statutory number of MPs",
    "większość 3/5": "three-fifths majority",
    "większość ustawowej liczby posłów": "majority of the statutory number of MPs",
    "Wymagana": "Required", "głosów": "votes",
    "Poprawka": "Amendment", "Wniosek mniejszości": "Minority motion", "Poprawka Senatu": "Senate amendment",
    "Poprawki": "Amendments", "Wnioski mniejszości": "Minority motions", "Poprawki Senatu": "Senate amendments",
    "przyjąć": "adopt", "odrzucić": "reject",
    "komisja": "committee",
    "Zgłaszający": "Proposed by",
    "rekomendacja komisji": "committee recommendation",
    "oficjalnie": "official",
    "druk nr": "print no.", "Druk nr": "Print no.", "druki": "prints", "Druki": "Prints",
    "Uwaga": "Note",
    "zmiana": "change",
    "głosowanie nr": "vote no.", "nr": "no.",
    "posiedzenie": "sitting",
    "Czego dotyczyło głosowanie": "What was voted on",
    "Nie udało się automatycznie odnaleźć treści.": "The text could not be found automatically.",
    "Zobacz": "See",
    "Zobacz druki": "See prints",
    "Sejm głosuje nad <strong>odrzuceniem</strong> poprawki Senatu: głos „za” oznacza odrzucenie poprawki. Poprawka zostaje przyjęta, jeśli za jej odrzuceniem nie opowie się bezwzględna większość.":
        "The Sejm votes on <strong>rejecting</strong> a Senate amendment: a vote “for” means rejecting the amendment. The amendment stands unless an absolute majority votes to reject it.",
    "Jak głosowały kluby": "How the clubs voted",
    "Kliknij klub, aby zobaczyć głosy imienne.": "Click a club to see how each MP voted.",
    "Klub / koło": "Club / circle",
    "linia klubu": "club line", "Linia klubu": "Club line",
    "podzielony": "split",
    "wyłamanie z linii klubu": "broke the club line",
    "Wyłamali się z linii klubu": "Broke the club line",
    "Poseł": "MP", "Klub": "Club", "Głos": "Vote",
    "Wszyscy głosujący członkowie klubów z wyraźną linią głosowali zgodnie z nią.":
        "All voting members of clubs with a clear line followed it.",
    # sittings & bills
    "Posiedzenia Sejmu": "Sittings of the Sejm",
    "Posiedzenie": "Sitting",
    "Daty głosowań": "Voting dates",
    "Głosowania": "Votes",
    "Głos. nad poprawkami": "Amendment votes",
    "głosowań": "votes",
    "Sprawy proceduralne": "Procedural matters",
    "posiedzenie Sejmu": "sitting of the Sejm",
    "Ustawy i uchwały": "Bills and resolutions",
    "Projekty, nad którymi Sejm głosował w tej kadencji, od ostatnio głosowanych.":
        "Bills and resolutions voted on this term, most recent first.",
    "Projekt": "Bill", "Ostatnie głosowanie": "Last vote", "Nad poprawkami": "On amendments",
    "Poprawki i wnioski według zgłaszających": "Amendments and motions by proposer",
    "przyjęte": "adopted", "odrzucone": "rejected",
    "Liczone są głosowania; jedno głosowanie może obejmować kilka łącznie głosowanych poprawek.":
        "Counted per vote; one vote can cover several amendments voted jointly.",
    "Wszystkie głosowania": "All votes",
    "(nieustalony)": "(unknown)",
    # MPs
    "Kliknij nagłówek kolumny, aby posortować.": "Click a column header to sort.",
    "Definicje wskaźników": "How the figures are defined",
    "Udział w głos.": "Turnout",
    "Wyłamania": "Broke line",
    "% wyłamań": "% broke line",
    "(wygasły)": "(former)",
    "okręg": "constituency",
    "w tej kadencji w klubach": "clubs this term",
    "mandat wygasły": "former MP",
    "udział w głosowaniach": "turnout",
    "z": "of",
    "wyłamań z linii klubu": "votes against the club line",
    "Wyłamania z linii klubu": "Votes against the club line",
    "Data": "Date", "Głosowanie": "Vote",
    "Brak.": "None.",
    # clubs
    "Kluby i koła": "Clubs and circles",
    "Kluby i koła poselskie": "Parliamentary clubs and circles",
    "Spójność": "Cohesion", "spójność": "cohesion",
    "Podziały": "Splits", "Skuteczność": "Effectiveness", "skuteczność": "effectiveness",
    "Spójność to średni odsetek głosujących członków klubu, którzy wybrali tę samą opcję co większość klubu. Skuteczność — jak często linia klubu (za/przeciw) pokrywała się z wynikiem głosowania.":
        "Cohesion is the average share of a club's voting members who chose the same option as the club majority. Effectiveness is how often the club line (for/against) matched the outcome.",
    "(nie istnieje)": "(dissolved)",
    "głosowania od": "votes from", "do": "to",
    "klub/koło już nie istnieje": "club no longer exists",
    "obecnych członków": "current members",
    "głosowań z podziałem": "split votes",
    "Zgodność z innymi klubami": "Agreement with other clubs",
    "Odsetek głosowań, w których oba kluby miały wyraźną linię i była ona taka sama (min. 20 wspólnych głosowań).":
        "Share of votes where both clubs had a clear line and it was the same (min. 20 shared votes).",
    "gł.": "votes",
    "Za mało danych.": "Not enough data.",
    "Członkowie": "Members",
    "Głosowania z podziałem w klubie": "Votes that split the club",
    "Żadna opcja nie uzyskała większości wśród głosujących członków. Najnowsze na górze.":
        "No option won a majority among voting members. Most recent first.",
    # adopted amendments
    "Poprawki przyjęte przez Sejm": "Amendments adopted by the Sejm",
    "Skuteczne poprawki — opis": "Every amendment, minority motion and Senate amendment that the Sejm adopted this term — and who proposed it.",
    "Skuteczność zgłaszających": "Proposers' success rate",
    "Zgłaszający / klub": "Proposer / club",
    "głosowane": "voted", "przyjęte (%)": "adopted (%)",
    "Wszyscy zgłaszający": "All proposers",
    "Tylko wbrew rekomendacji komisji": "Only against the committee's recommendation",
    "Senat": "Senate",
    "Kliknij zgłaszającego, aby przejrzeć wszystkie jego poprawki — także odrzucone.":
        "Click a proposer to browse all of their amendments, including rejected ones.",
    "Wszystkie poprawki i wnioski zgłoszone przez klub": "All amendments and motions proposed by this club",
    "Poprawki i wnioski zgłoszone przez": "Amendments and motions proposed by",
    "Wspólne poprawki kilku klubów są na liście każdego z nich.": "Amendments proposed jointly by several clubs appear in each club's list.",
    "Szukaj w treści, ustawie, temacie…": "Search text, bill, topic…",
    "Wynik": "Outcome", "Wszystkie wyniki": "All outcomes",
    "Posłowie podpisani pod poprawkami i wnioskami": "MPs who signed amendments and motions",
    "Wnioski mniejszości i poprawki zgłaszane imiennie; poprawki zgłaszane przez kluby liczone są wyżej.":
        "Minority motions and amendments signed by named MPs; amendments filed by clubs are counted above.",
    "Podpisane poprawki i wnioski": "Signed amendments and motions",
    "podpisanych poprawek i wniosków przyjętych": "signed amendments and motions adopted",
    "Podpisane wnioski": "Signed motions",
    # API
    "Otwarte API w formacie JSON: głosowania Sejmu powiązane z treścią poprawek, wyniki klubów, głosy imienne, posłowie i zmiany w prawie.":
        "Open JSON API: Sejm votes linked to amendment texts, club results, named votes, MPs and changes to the law.",
    "Pliki są statyczne i odświeżane razem ze stroną; można je pobierać z dowolnej strony WWW (CORS).":
        "Files are static and refreshed with the site; any website can fetch them (CORS enabled).",
    "Adres bazowy": "Base URL", "Endpointy": "Endpoints", "Ścieżka": "Path", "Zawartość": "Contents",
    "lista posiedzeń z liczbą głosowań": "list of sittings with vote counts",
    "głosowania posiedzenia: wynik, temat, druki, powiązane poprawki (bez treści)": "a sitting's votes: result, topic, prints, linked amendments (without text)",
    "pełne głosowanie: treść poprawek, rekomendacja komisji, zmiany w prawie, wyniki klubów, linia klubu, wyłamania, głosy imienne":
        "full vote: amendment text, committee recommendation, changes to the law, club results, club line, line-breakers, named votes",
    "projekty (wg druku otwierającego proces), zmiany w obowiązującym prawie, skuteczność zgłaszających, głosowania":
        "bills (by the print opening the process), changes to existing law, proposers' success, votes",
    "posłowie: udział, wyłamania, podpisane wnioski, historia przynależności klubowej": "MPs: turnout, line-breaking, signed motions, club history",
    "kluby: członkowie, spójność, skuteczność, zgodność z innymi klubami": "clubs: members, cohesion, effectiveness, agreement with other clubs",
    "druk: metadane i sparsowane poprawki / wnioski mniejszości / poprawki Senatu": "print: metadata and parsed amendments / minority motions / Senate amendments",
    "skuteczność zgłaszających (kluby, posłowie) i lista przyjętych poprawek": "proposers' success (clubs, MPs) and adopted amendments",
    "Przykład": "Example", "Zasady": "Conventions",
    "Identyfikatory posłów i klubów są takie same jak w API Sejmu (api.sejm.gov.pl).": "MP and club ids are the same as in the Sejm API (api.sejm.gov.pl).",
    "Głosy: yes / no / abstain / absent. Teksty prawne i etykiety pozostają po polsku.": "Votes: yes / no / abstain / absent. Legal texts and labels are in Polish.",
    "Treść poprawek i porównania z prawem są wyodrębniane automatycznie; pole linked mówi, czy treść udało się powiązać. Wiążący jest oficjalny druk.":
        "Amendment texts and law comparisons are extracted automatically; the linked field says whether the text was found. The official print is authoritative.",
    "Wersja v1 jest stabilna: pola mogą być dodawane, ale nie usuwane ani zmieniane.": "v1 is stable: fields may be added, but not removed or changed.",
    # club history
    "Historia przynależności klubowej": "Club membership history",
    "Od": "From", "Do": "To", "Z": "From",
    "Na podstawie przynależności zapisanej przy każdym głosowaniu; daty to pierwsze i ostatnie głosowanie w danym klubie.":
        "Based on the club recorded with each vote; dates are the first and last vote cast in that club.",
    "Zmiany klubu": "Club changes",
    "zmiana nazwy lub formuły klubu": "club renamed or reorganised",
    "Przejścia między klubami": "Moves between clubs",
    "Liczba posłów, którzy przeszli z jednego klubu lub koła do innego w tej kadencji.":
        "Number of MPs who moved from one club or circle to another during this term.",
    # motions
    "Głosowanie nad wnioskiem o odrzucenie informacji lub sprawozdania: „za” oznacza odrzucenie dokumentu, „przeciw” — jego przyjęcie do wiadomości.":
        "Vote on a motion to reject a report or information: “for” means rejecting the document, “against” means accepting it.",
    "Wniosek przyjęty — dokument odrzucony": "Motion passed — document rejected",
    "Wniosek odrzucony — dokument nie został odrzucony": "Motion failed — document not rejected",
    "Głosowanie nad wnioskiem o odrzucenie projektu: „za” oznacza odrzucenie projektu i koniec prac nad nim, „przeciw” — że projekt trafia do dalszych prac.":
        "Vote on a motion to reject the bill: “for” means rejecting it and ending work on it, “against” means the bill proceeds.",
    "Wniosek przyjęty — projekt odrzucony": "Motion passed — bill rejected",
    "Wniosek odrzucony — projekt trafia do dalszych prac": "Motion failed — the bill proceeds",
    "Głosowanie nad wotum nieufności: „za” oznacza poparcie dla odwołania. Konstruktywne wotum nieufności wobec rządu wymaga większości ustawowej liczby posłów (231 głosów).":
        "Vote of no confidence: “for” supports the dismissal. A constructive vote of no confidence in the government needs a majority of the statutory number of MPs (231 votes).",
    "Wotum nieufności uchwalone": "No-confidence motion passed", "Wotum nieufności nieuchwalone": "No-confidence motion failed",
    "Głosowanie nad wotum zaufania: „za” oznacza poparcie dla rządu.": "Vote of confidence: “for” means supporting the government.",
    "Wotum zaufania udzielone": "Confidence granted", "Wotum zaufania nieudzielone": "Confidence not granted",
    "Głosowanie nad wnioskiem o przyspieszenie prac: „za” oznacza, że projekt od razu przechodzi do kolejnego etapu bez prac w komisji.":
        "Vote on a motion to fast-track: “for” means the bill moves straight to the next stage without committee work.",
    "Wniosek przyjęty — bez kierowania do komisji": "Motion passed — no committee referral",
    "Wniosek odrzucony": "Motion rejected", "Wniosek przyjęty": "Motion passed",
    "Wniosek formalny o przerwę, odroczenie lub zamknięcie posiedzenia: „za” oznacza przerwanie obrad.":
        "Procedural motion to pause, adjourn or close the sitting: “for” means interrupting proceedings.",
    "Głosowanie nad całością projektu: „za” oznacza uchwalenie ustawy lub uchwały w całości. Uchwalona ustawa trafia następnie do Senatu.":
        "Final vote on the whole bill: “for” means passing the bill or resolution. A passed bill then goes to the Senate.",
    "Projekt przyjęty": "Bill passed", "Projekt odrzucony": "Bill rejected",
    "Senat zaproponował odrzucenie ustawy. „Za” oznacza odrzucenie uchwały Senatu — ustawa zostaje przyjęta; potrzebna jest bezwzględna większość. W przeciwnym razie ustawa upada.":
        "The Senate proposed rejecting the bill. “For” means rejecting the Senate's resolution — the bill stands; this needs an absolute majority. Otherwise the bill falls.",
    "Uchwała Senatu odrzucona — ustawa przyjęta": "Senate resolution rejected — bill stands",
    "Uchwała Senatu utrzymana — ustawa odrzucona": "Senate resolution upheld — bill falls",
    # law comparison
    "Zmiany w obowiązującym prawie": "Changes to existing law",
    "Spis zmian": "Index of changes",
    "Autor projektu": "Submitted by", "Autor": "Author",
    "Rada Ministrów": "Government (Council of Ministers)", "Posłowie": "MPs",
    "Obywatele (inicjatywa obywatelska)": "Citizens' initiative", "Komisja sejmowa": "Sejm committee",
    "Prezydent RP": "President of Poland", "Prezydium Sejmu": "Presidium of the Sejm",
    "podpisów posłów": "MPs' signatures",
    "Posłowie podpisani pod projektem": "MPs who signed the bill",
    "Odczytane automatycznie z podpisów na druku; lista może być niepełna.":
        "Read automatically from the signatures on the print; the list may be incomplete.",
    "Spis treści": "Contents", "Pełny tekst — artykuły": "Full text — articles",
    "Obecne brzmienie przepisów porównane z projektem według": "Current provisions compared with the bill as in",
    "druku nr": "print no.",
    "(przed poprawkami z drugiego czytania)": "(before second-reading amendments)",
    "usunięte": "removed", "dodane": "added",
    "zmian": "changes",
    "tekst jednolity": "consolidated text",
    "Uwaga: późniejsze nowelizacje mogą nie być uwzględnione": "Note: later amendments may not be reflected",
    "Tekst ustawy nie został jeszcze pobrany — pokazujemy tylko nowe brzmienie.": "The act's text has not been downloaded yet — only the new wording is shown.",
    "uchylenie": "repeal", "dodanie": "addition",
    "nie odnaleziono przepisu w tekście jednolitym": "provision not found in the consolidated text",
    "Porównanie z projektem według": "Compared with the bill as in",
    "szare — sąsiednie przepisy": "grey — surrounding provisions",
    "przepis dodawany inną zmianą — brak w projekcie": "provision added by another change — not in the bill",
    "nie odnaleziono przepisu w projekcie": "provision not found in the bill",
    # prints
    "strona druku w Sejmie": "print on sejm.gov.pl",
    "Nie głosowano osobno (np. głosowana łącznie z inną poprawką lub bezprzedmiotowa).":
        "Not voted separately (e.g. voted jointly with another amendment, or lapsed).",
    "Głosowania powołujące się na ten druk": "Votes citing this print",
    "Pełny tekst": "Full text",
    "po polsku": "in Polish",
    "Tekst wyodrębniony automatycznie z dokumentu źródłowego; wiążący jest oficjalny druk.":
        "Text extracted automatically from the source document (in Polish); the official print is authoritative.",
    "Tekst tego druku nie został jeszcze pobrany — zobacz": "This print's text has not been downloaded yet — see",
    "oficjalny druk": "the official print",
    "Dokument jest zbyt obszerny, by wyświetlić go w całości — zobacz": "This document is too long to display in full — see",
    # index
    "Ostatnie posiedzenie": "Latest sitting",
    "głosowań nad poprawkami i wnioskami": "votes on amendments and motions",
    "rozstrzygnięć wbrew rekomendacji komisji": "decisions against the committee's recommendation",
    "Wbrew rekomendacji komisji": "Against the committee's recommendation",
    "Najczęściej wyłamujący się z linii klubu": "Most frequent line-breakers",
    "Pełne zestawienia": "Full tables",
    "Jak liczymy": "How we count",
    # search
    "Wyszukiwarka wymaga JavaScriptu.": "Search requires JavaScript.",
    "Szukaj ustaw, poprawek, posłów…": "Search bills, amendments, MPs…",
    "Indeks wyszukiwania nie jest jeszcze zbudowany.": "The search index has not been built yet.",
}


# Keys that are identifiers rather than Polish display text.
PL = {
    "Podsumowania dni — opis": "Najważniejsze liczby z każdego dnia głosowań w Sejmie: uchwalone ustawy, przyjęte poprawki "
                               "i głosy klubów w najbardziej spornym głosowaniu, wprost z danych.",
    "Domyślny opis": "Każde głosowanie w Sejmie powiązane z poprawką, której dotyczy: pełna treść, "
                     "zgłaszający, rekomendacja komisji i wynik w podziale na kluby.",
    "Prywatność — opis": "Sejmomat nie używa cookies, śledzenia ani reklam. Co zapisuje dostawca hostingu, "
                         "co trafia do pamięci przeglądarki i skąd pochodzą dane o posłach.",
    "Poprawki — opis": "Wszystkie poprawki, wnioski mniejszości i poprawki Senatu, nad którymi Sejm głosował w tej "
                       "kadencji — przyjęte i odrzucone, ze zgłaszającym i rekomendacją komisji.",
    "Skuteczne poprawki — opis": "Wszystkie poprawki, wnioski mniejszości i poprawki Senatu, które Sejm "
                                 "przyjął w tej kadencji — i kto je zgłosił.",
}


def translator(lang):
    if lang == "pl":
        return lambda s: PL.get(s, s)
    missing = set()

    def t(s):
        if s not in EN:
            missing.add(s)
        return EN.get(s, s)

    t.missing = missing
    return t


def date_fmt(lang):
    def fmt(value, with_time=False):
        d = datetime.fromisoformat(value) if isinstance(value, str) else value
        month = MONTHS[lang][d.month - 1]
        out = f"{d.day} {month} {d.year}" if lang == "pl" else f"{month} {d.day}, {d.year}"
        return f"{out}, {d:%H:%M}" if with_time else out
    return fmt


def pct_fmt(lang):
    def fmt(x):
        s = f"{x * 100:.1f}"
        return (s.replace(".", ",") if lang == "pl" else s) + "%"
    return fmt
