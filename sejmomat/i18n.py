"""Interface strings for the English edition.

Templates and Python labels are written in Polish; `translator("en")` maps
them to English. Legal text and data from the API (topics, titles, amendment
text) are never translated.
"""
from datetime import datetime

LANGS = ("pl", "en")

# a term's place in an MP's career, as a word ("szósta kadencja"): reads more easily than "6."
ORDINALS = ["pierwsza", "druga", "trzecia", "czwarta", "piąta", "szósta", "siódma", "ósma", "dziewiąta", "dziesiąta"]

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
    "Kadencja": "Term",
    "Przygotowywanie…": "Preparing…", "Nie udało się przygotować grafiki.": "The image could not be made.",
    "Grafiki do udostępnienia": "Images to share",
    "Podsumowanie kadencji albo ostatniego posiedzenia — gotowe do wrzucenia w media społecznościowe. Grafiki są po polsku.":
        "A summary of the term or of the latest sitting, ready to post on social media. The images are in Polish.",
    "Podsumowanie kadencji albo ostatniego posiedzenia tego posła — gotowe do wrzucenia w media społecznościowe. Grafika powstaje w Twojej przeglądarce. Grafiki są po polsku.":
        "A summary of this MP's term or of the latest sitting, ready to post on social media. The image is made in your browser. The images are in Polish.",
    "Podsumowanie każdego dnia głosowań, a dla każdego klubu i posła — kadencji albo ostatniego posiedzenia. Gotowe do wrzucenia w media społecznościowe.":
        "A summary of every voting day, and for every club and MP, of the term or the latest sitting. Ready to post on social media.",
    "Dni głosowań": "Voting days", "Okręg": "Constituency", "niezrzeszeni": "non-attached",
    "Na stronie każdego klubu: grafiki do udostępnienia z podsumowaniem kadencji i ostatniego posiedzenia.":
        "On every club's page: images to share, summing up the term and the latest sitting.",
    "Na stronie każdego posła: grafiki do udostępnienia z podsumowaniem kadencji i ostatniego posiedzenia.":
        "On every MP's page: images to share, summing up the term and the latest sitting.",
    "Szukaj posła, okręgu, klubu…": "Search for an MP, constituency, club…", "Wszystkie kluby": "All clubs",
    "Wszystkie okręgi": "All constituencies", "Mandat": "Mandate", "Obecni i byli posłowie": "Current and former MPs",
    "Obecni posłowie": "Current MPs", "Wygasłe mandaty": "Former MPs", "Tylko ci, którzy zmienili klub": "Only those who switched clubs",
    "Nadchodzące posiedzenie": "Upcoming sitting", "Trwające posiedzenie": "Sitting under way", "porządek obrad": "agenda",
    "punktów": "items", "Porządek obrad następnego posiedzenia Sejmu.": "The agenda of the Sejm's next sitting.",
    "dni obrad": "days of proceedings", "punktów w porządku obrad": "items on the agenda",
    "punktów, które mogą zostać dodane": "items that may be added", "pierwszych czytań projektów": "first readings of bills",
    "projektów wykonujących prawo UE": "bills implementing EU law",
    "Porządek obrad opublikowany przez Sejm. Może się jeszcze zmienić, a kolejność punktów ustala Marszałek Sejmu bezpośrednio przed posiedzeniem. Po posiedzeniu znajdziesz tu wyniki głosowań.":
        "The agenda as published by the Sejm, in Polish. It may still change, and the Speaker sets the order of the items just before the sitting. After the sitting, the results of the votes appear on this site.",
    "Porządek obrad": "Agenda", "Projekt mający na celu wykonanie prawa Unii Europejskiej": "Bill implementing European Union law",
    "Przebieg prac nad projektem": "How the bill has progressed",
    "Porządek obrad opublikowany przez Sejm, z debatą i głosowaniami nad każdym punktem. „Nagranie” odtwarza debatę nad punktem z transmisji Sejmu; wystąpienia prowadzą do stenogramu na stronie Sejmu.":
        "The agenda as published by the Sejm, with the debate and votes on each item. “Recording” plays the debate on the item from the Sejm's stream; speeches link to the transcript on the Sejm's website.",
    "Sejm opublikował dotąd porządek planowany; punkty są tu ponumerowane i ułożone tak, jak na posiedzeniu (według głosowań i stenogramów), a punkty dodane w trakcie opisane tak, jak w głosowaniach.":
        "So far the Sejm has published the planned agenda; here the items are numbered and ordered as at the sitting (from the votes and transcripts), and items added during it are described as in the votes.",
    "Debata z nagraniami": "Debate with video", "bez debaty i głosowań na tym posiedzeniu": "no debate or votes at this sitting",
    "na piśmie": "in writing",
    "Wszystkie głosowania na tym posiedzeniu": "All votes at this sitting",
    "Najnowsze głosowania wczytują się na bieżąco z API Sejmu; kluby, posłowie i poprawki są na ich stronach od razu, a w pozostałych zestawieniach serwisu — od następnej aktualizacji.":
        "The latest votes load as they come from the Sejm's API; clubs and MPs are on their pages straight away, in the site's other summaries from the next update.",
    "Głosowanie wczytane z API Sejmu; pełna strona (z poprawkami i drukami) pojawi się przy następnej aktualizacji serwisu.":
        "Vote loaded from the Sejm's API; the full page (with amendments and prints) comes with the site's next update.",
    # the stats page
    "Statystyki głosowań": "Voting statistics", "Cała kadencja": "The whole term", "Pół roku po pół roku": "Half-year by half-year",
    "Spójność klubów": "Club cohesion", "Jak często kluby głosują tak samo": "How often clubs vote alike", "Na włosku": "By a hair",
    "Najbliższe rozstrzygnięcia": "The closest votes", "Wyróżnij klub": "Highlight a club", "Mapa posłów": "Map of MPs",
    "Mapa posłów według podobieństwa głosowań w całej kadencji": "Map of MPs by how alike they voted over the whole term",
    "inne / niezrzeszeni": "other / independent", "koalicja i opozycja głosowały tak samo": "coalition and opposition voted alike",
    "koalicja z opozycją": "coalition with opposition", "przewaga": "margin",
    "Mapa Sejmu według tego, jak głosują posłowie: kto z kim głosuje, jak spójne są kluby i które głosowania rozstrzygnęło kilka głosów.":
        "The Sejm mapped by how MPs vote: who votes with whom, how united the clubs are, and which votes came down to a few votes.",
    "Każda kropka to poseł, kolor to jego klub. Linie łączą każdego posła z pięcioma, z którymi najczęściej głosuje tak samo, i przyciągają ich do siebie, więc grupy, które głosują podobnie, zbijają się w skupiska. Najedź na kropkę, by zobaczyć posła, kliknij, by przejść do jego strony; kliknij klub w legendzie, by go wyróżnić na wszystkich mapach.":
        "Each dot is an MP, coloured by club. Lines join every MP to the five they most often vote alike with and pull them together, so groups that vote alike gather into clusters. Hover over a dot to see the MP, click to open their page; click a club in the legend to highlight it on every map.",
    "Te same mapy dla kolejnych półroczy, obrócone tak, by bloki zostawały na swoich miejscach. Na mapie są posłowie, którzy oddali głos w co najmniej czwartej części głosowań danego półrocza; liczba przy każdej mapie mówi, jak często poseł koalicji i poseł opozycji głosowali wtedy tak samo.":
        "The same maps for each half-year, turned so that the blocs keep their places. A map shows the MPs who voted in at least a quarter of that half-year's votes; the figure by each map says how often a coalition MP and an opposition MP voted alike then.",
    "tak często poseł koalicji i poseł opozycji głosowali tak samo (średnio, w głosowaniach, w których obaj oddali głos)":
        "how often a coalition MP and an opposition MP voted alike (on average, in the votes both took part in)",
    "Średni odsetek posłów klubu, którzy głosowali tak jak większość ich klubu (wśród głosujących). Im ciemniej, tym spójniej.":
        "The average share of a club's MPs who voted as most of their club did (among those voting). The darker, the more united.",
    "Odsetek głosowań w tej kadencji, w których linie dwóch klubów (to, jak głosowała większość ich posłów) były takie same. Obecne kluby i koła.":
        "The share of this term's votes in which two clubs' lines (how most of their MPs voted) were the same. Current clubs and groups.",
    "Ile głosów zabrakło albo zostało ponad to, co było potrzebne do przyjęcia, w głosowaniach kadencji (z udziałem większości Sejmu), od −40 do +40. Na prawo od przerywanej linii wniosek przeszedł, na lewo upadł.":
        "How many votes short of, or beyond, what passing needed, in this term's votes (with most of the Sejm taking part), from −40 to +40. Right of the dashed line the motion passed, left of it it failed.",
    "Poza wykresem: {a} głosowań przyjętych z zapasem ponad 40 głosów i {b} upadłych, którym zabrakło ponad 40.":
        "Off the chart: {a} votes passed with more than 40 to spare and {b} failed by more than 40.",
    "Tematy": "Topics", "temat": "topic", "Projekty i głosowania na temat": "Bills and votes on", "Nie ma jeszcze tematów.": "No topics yet.",
    "Projekty i głosowania według tematów: o czym naprawdę są, w kilku słowach.": "Bills and votes by topic: what they are really about, in a few words.",
    "Tytuły projektów rzadko mówią, o co w nich chodzi („o zmianie ustawy – Kodeks karny”). Tematy opisują to w kilku słowach. Nadaje je redakcja serwisu na podstawie tytułów i opisów projektów z API Sejmu.":
        "Bill titles rarely say what a bill is about (“amending the Penal Code”). Topics say it in a few words. They are given by the site's editors, from the bills' titles and their descriptions in the Sejm's API.",
    "Głosowanie nad całością": "Vote on the whole bill",
    "Porównaj głosowania": "Compare votes", "Porównaj z innym głosowaniem": "Compare with another vote",
    "Porównaj: wniosek o odrzucenie a głosowanie nad całością": "Compare: the motion to reject and the vote on the whole bill",
    "Jak posłowie i kluby głosowali w dwóch głosowaniach: kto zagłosował tak samo, a kto inaczej, np. przy wniosku o odrzucenie projektu i głosowaniu nad całością.":
        "How MPs and clubs voted in two votes: who voted the same way and who did not, e.g. on a motion to reject a bill and on the whole bill.",
    "Wybierz dwa głosowania, aby zobaczyć, kto zagłosował w nich tak samo, a kto inaczej. Przy wniosku o odrzucenie projektu „za” oznacza głos przeciw projektowi — takie głosowanie można odwrócić, by porównać je np. z głosowaniem nad całością.":
        "Pick two votes to see who voted the same way in both and who did not. In a motion to reject a bill, “for” is a vote against the bill: such a vote can be flipped to compare it with, e.g., the vote on the whole bill.",
    "Głosowanie A": "Vote A", "Głosowanie B": "Vote B",
    "Odwróć znaczenie: „za” to głos przeciw projektowi (np. wniosek o odrzucenie)": "Flip the meaning: “for” is a vote against the bill (e.g. a motion to reject)",
    "za projektem": "for the bill", "przeciw projektowi": "against the bill",
    "głosowali tak samo": "voted the same way", "głosowali inaczej": "voted differently", "nie głosowali w jednym z nich": "did not vote in one of them",
    "Posłowie, którzy zagłosowali inaczej": "MPs who voted differently",
    "Wszyscy, którzy oddali głos w obu głosowaniach, zagłosowali tak samo.": "Everyone who voted in both votes voted the same way.",
    "Wybierz głosowanie": "Pick a vote", "Wczytywanie z API Sejmu…": "Loading from the Sejm's API…", "Nie udało się wczytać głosowania.": "The vote could not be loaded.",
    "strona głosowania": "voting page", "zgodnie": "the same",
    "Porównywani są posłowie, którzy głosowali (za, przeciw lub wstrzymali się) w obu głosowaniach; wstrzymanie się to osobny wybór. Klub według drugiego głosowania.":
        "Compared are the MPs who voted (for, against or abstaining) in both votes; abstaining is a choice of its own. Clubs as in the second vote.",
    "Nie znaleziono takiego głosowania.": "No such vote.", "Wczytywanie głosowania z API Sejmu…": "Loading the vote from the Sejm's API…", "Pełna strona głosowania": "Full voting page",
    "Głosowania na żywo": "Votes as they happen", "Ostatnie głosowania": "Latest votes", "Głosowanie nr": "Vote no.", "Punkt": "Item", "Wcześniej": "Earlier",
    "Na tym posiedzeniu jeszcze nie głosowano.": "No votes at this sitting yet.",
    "Wyniki z API Sejmu, z około minutowym opóźnieniem.": "Results from the Sejm's API, about a minute behind.",
    "Transmisja idzie z opóźnieniem, a wyniki pojawiają się wtedy, gdy na nagraniu kończy się głosowanie.":
        "The stream runs with a delay, and each result appears when the vote ends in the video.",
    # amendments waiting for a vote, frozen bills
    "Czeka na głosowanie": "Waiting for a vote", "Czekające na głosowanie": "Waiting for a vote",
    "Poprawki czekające na głosowanie": "Amendments waiting for a vote", "Poprawki z drugiego czytania": "Amendments from the second reading",
    "Poprawki zgłoszone w drugim czytaniu, wnioski mniejszości z komisji i poprawki Senatu, nad którymi Sejm jeszcze nie głosował. Wnioski mniejszości i poprawki z drugiego czytania Sejm rozstrzyga w trzecim czytaniu; poprawki Senatu — głosując nad stanowiskiem Senatu.":
        "Amendments tabled in the second reading, minority motions from committees and Senate amendments the Sejm has not yet voted on. Minority motions and second-reading amendments are decided in the third reading; Senate amendments in the vote on the Senate's position.",
    "Z druków Sejmu, których nie przywołało jeszcze żadne głosowanie, o ile przebieg prac nad projektem nie pokazuje, że sprawa jest już zamknięta (trzecie czytanie, głosowanie nad stanowiskiem Senatu, odrzucenie, wycofanie).":
        "From Sejm prints no vote has cited yet, unless the bill's progress shows the matter is closed (third reading, vote on the Senate's position, rejection, withdrawal).",
    "poprawek i wniosków czeka": "amendments and motions waiting", "projektów": "bills",
    "w porządku obrad najbliższego posiedzenia": "on the agenda of the next sitting", "czeka ponad pół roku": "waiting over six months",
    "ponad pół roku": "over six months", "czeka": "waiting", "Pokaż": "Show",
    "poprawek, wniosków mniejszości i poprawek Senatu, nad którymi Sejm jeszcze nie głosował.": "amendments, minority motions and Senate amendments the Sejm has not yet voted on.",
    "Zamrażarka": "The freezer", "Zamrażarka: projekty, które utknęły": "The freezer: bills that got stuck",
    "Zamrażarka: projekty, które utknęły u Marszałka lub w komisjach": "The freezer: bills stuck with the Marshal or in committee",
    "projektów ustaw i uchwał czeka u Marszałka Sejmu albo w komisjach; ile dni i na co.": "bills and draft resolutions waiting with the Marshal of the Sejm or in committee; for how long and for what.",
    "Projekty ustaw i uchwał, które utknęły przed drugim czytaniem: czekają, aż Marszałek Sejmu skieruje je do pierwszego czytania albo wpisze pierwsze lub drugie czytanie do porządku obrad, albo aż komisja się nimi zajmie lub przygotuje sprawozdanie. Liczy się czas od ostatniego kroku w przebiegu prac.":
        "Bills and draft resolutions stuck before the second reading: waiting for the Marshal of the Sejm to send them to a first reading or put the first or second reading on the agenda, or for a committee to take them up or report on them. Counted from the last step in their progress.",
    "czeka u Marszałka Sejmu": "waiting with the Marshal", "czeka w komisjach": "waiting in committee", "bez ruchu ponad pół roku": "no progress for over six months",
    "Gdzie czekają": "Where they wait", "Etap": "Stage", "Razem": "Total", "Marszałek": "Marshal", "komisje": "committees",
    "Nieskierowane do pierwszego czytania": "Not sent to a first reading", "Czekają na pierwsze czytanie na sali": "Waiting for a first reading in the chamber",
    "Sprawozdanie gotowe, czekają na drugie czytanie": "Report ready, waiting for the second reading",
    "Czekają na pierwsze czytanie w komisji": "Waiting for a first reading in committee",
    "Po pierwszym czytaniu, bez sprawozdania komisji": "After the first reading, no committee report",
    "rządowy": "government", "poselski": "MPs'", "obywatelski": "citizens'", "senacki": "Senate", "prezydencki": "President's", "komisyjny": "committee", "inny": "other",
    "Szukaj w tytułach i opisach…": "Search the titles and descriptions…", "Nie ma poprawek czekających na głosowanie.": "No amendments are waiting for a vote.",
    "Projekty poselskie według klubu": "MPs' bills by club",
    "Klub posła, który podpisał projekt jako pierwszy, w dniu złożenia projektu (z podpisów w druku).": "The club of the MP who signed the bill first, on the day it was submitted (from the signatures in the print).",
    "projektów poselskich bez odczytanych podpisów.": "MPs' bills whose signatures could not be read.",
    "u Marszałka": "with the Marshal", "w komisjach": "in committee", "Wszystkie kluby": "All clubs",
    "Projekty czekające w komisji (na pierwsze czytanie albo sprawozdanie) i przerwy między posiedzeniami komisji w tej kadencji; dni od ostatniego posiedzenia pogrubione, gdy to ponad dwa miesiące.":
        "Bills waiting in a committee (for a first reading or a report) and the breaks between the committee's meetings this term; days since the last meeting in bold when over two months.",
    "Czeka": "Waiting", "Najdłużej (dni)": "Longest (days)",
    "Posiedzenia": "Meetings", "Od ostatniego (dni)": "Since the last (days)", "Najdłuższa przerwa (dni)": "Longest break (days)", "Wszystkie etapy": "All stages", "Wnioskodawca": "Sponsor", "Wszyscy wnioskodawcy": "All sponsors",
    "Projekty uchwał": "Draft resolutions", "Dni": "Days", "Wpłynął": "Submitted", "ostatni krok": "last step",
    "Z przebiegu prac nad projektami w API Sejmu. Projekty odrzucone, wycofane lub zamknięte z innego powodu nie są liczone. Linki prowadzą do przebiegu prac na stronie Sejmu albo, jeśli Sejm już nad projektem głosował, do jego strony tutaj.":
        "From the bills' progress in the Sejm's API. Bills rejected, withdrawn or closed for another reason are not counted. Links lead to the bill's progress on the Sejm's website or, if the Sejm has voted on it, to its page here.",
    "Obrady Sejmu na żywo": "The Sejm live", "Transmisja obrad dziś od": "Live stream today from",
    "Transmisja na stronie Sejmu": "Stream on the Sejm's website",
    "Nie udało się odtworzyć transmisji. Spróbuj na stronie Sejmu.": "The stream could not be played. Try the Sejm's website.",
    "Porządek obrad następnego posiedzenia nie został jeszcze opublikowany. Sejm ogłasza go zwykle około tygodnia przed posiedzeniem.":
        "The agenda of the next sitting has not been published yet. The Sejm usually announces it about a week before the sitting.",
    "Porządek obrad następnego posiedzenia nie został jeszcze opublikowany.": "The agenda of the next sitting has not been published yet.",
    "Kolejne planowane posiedzenia": "Planned sittings after that", "kolejne mogą zostać dodane": "more may be added",
    "Cały porządek obrad": "The whole agenda", "Najbliższe planowane posiedzenie": "Next planned sitting",
    "Komisje": "Committees", "Komisje sejmowe": "Sejm committees", "Komisja": "Committee", "Rodzaj": "Type",
    "stała": "standing", "nadzwyczajna": "extraordinary", "śledcza": "investigative",
    "Komisja stała": "Standing committee", "Komisja nadzwyczajna": "Extraordinary committee", "Komisja śledcza": "Investigative committee",
    "Komisje Sejmu: członkowie, posiedzenia z porządkiem obrad, nagraniami i stenogramami oraz projekty ustaw, którymi się zajmowały.":
        "Sejm committees: members, meetings with their agendas, recordings and transcripts, and the bills they worked on.",
    "Członkowie, posiedzenia z porządkiem obrad, nagraniami i stenogramami oraz projekty ustaw, którymi zajmowała się każda komisja.":
        "Members, meetings with their agendas, recordings and transcripts, and the bills each committee worked on.",
    "Projekty ustaw": "Bills", "Projekty": "Bills", "Funkcja": "Role", "członków": "members",
    "posiedzeń w tej kadencji": "meetings this term", "zaplanowanych posiedzeń": "planned meetings",
    "projektów ustaw i uchwał, nad którymi głosował Sejm": "bills and resolutions voted on by the Sejm",
    "Zaplanowane": "Planned", "Odbyte": "Held", "zaplanowane": "planned", "zamknięte": "closed", "zdalne": "remote",
    "posiedzenie nr": "meeting no.", "wspólnie z": "jointly with", "Cały porządek": "Whole agenda", "pozycji": "lines",
    "Nagranie": "Recording", "w serwisie Sejmu": "on the Sejm's site",
    "Nie udało się odtworzyć nagrania. Otwórz je w serwisie Sejmu.": "The recording could not be played. Open it on the Sejm's site.", "Stenogram (PDF)": "Transcript (PDF)", "W komisjach": "In committee",
    "Szukaj w porządku obrad…": "Search the agendas…", "Szukaj w porządku obrad": "Search the agendas",
    "Nagrania i stenogramy pochodzą z serwisu Sejmu. Stenogram pojawia się zwykle kilka dni lub tygodni po posiedzeniu; posiedzenia zamknięte często go nie mają.":
        "Recordings and transcripts are the Sejm's, in Polish. A transcript usually appears a few days or weeks after the meeting; closed meetings often have none.",
    "Projekty ustaw i uchwał, nad którymi głosował Sejm, omawiane na posiedzeniach komisji (według numerów druków w porządku obrad).":
        "Bills and resolutions voted on by the Sejm that were discussed at the committee's meetings (going by the print numbers on the agenda).",
    "Posiedzenia komisji, na których omawiano projekt (według numerów druków w porządku obrad), od najnowszych.":
        "Committee meetings where the bill was discussed (going by the print numbers on the agenda), newest first.",
    "Obecny skład komisji według Sejmu.": "Current committee membership, as listed by the Sejm.",
    "Prace w rządzie, przed skierowaniem do Sejmu": "Work in the government, before the bill went to the Sejm",
    "Rządowe Centrum Legislacji": "Government Legislation Centre",
    "pierwsze wersje projektu, uzgodnienia i konsultacje; RCL nie pozwala na automatyczne pobieranie danych, dlatego pokazujemy tylko odnośnik":
        "first drafts, inter-ministerial agreement and consultations; RCL does not allow automated downloads, so we only link to it",
    "Interpelacje i zapytania": "Interpellations and written questions",
    "Interpelacje i zapytania poselskie": "MPs' interpellations and written questions",
    "Interpelacje i zapytania poselskie w tej kadencji: kto pyta najczęściej i jak szybko odpowiadają ministrowie.":
        "MPs' interpellations and written questions this term: who asks most, and how quickly ministers answer.",
    "Pytania posłów do rządu i to, jak szybko ministrowie na nie odpowiadają. Na odpowiedź mają": "MPs' questions to the government and how quickly ministers answer them. They have",
    "dni.": "days to answer.", "dni": "days", "dn.": "d",
    "interpelacji": "interpellations", "zapytań poselskich": "written questions", "z odpowiedzią": "answered",
    "Z odpowiedzią": "Answered", "typowy czas odpowiedzi (mediana)": "typical time to answer (median)",
    "typowy czas odpowiedzi": "typical time to answer", "odpowiedzi po terminie": "answers after the deadline",
    "bez odpowiedzi po terminie": "unanswered past the deadline", "Jak odpowiadają ministrowie": "How ministers answer",
    "Kliknij nagłówek kolumny, aby posortować. „Po terminie” to odpowiedzi, które przyszły później niż przewiduje regulamin; „bez odpowiedzi” — pytania, na które termin minął, a odpowiedzi nie ma.":
        "Click a column heading to sort. \"After the deadline\" means answers that came later than the rules allow; \"unanswered\" means questions whose deadline has passed with no answer.",
    "Adresat": "Addressed to", "Pytania": "Questions", "Mediana dni": "Median days", "Po terminie": "After the deadline",
    "Przedłużenia": "Extensions", "Bez odpowiedzi": "Unanswered", "Interpelacje": "Interpellations", "Zapytania": "Written questions",
    "Pytania liczone według klubu posła w dniu ich złożenia; pytanie podpisane przez posłów kilku klubów liczy się dla każdego z nich.":
        "Questions are counted by the MP's club on the day they were filed; a question signed by MPs of several clubs counts for each.",
    "Najczęściej pytający posłowie": "MPs who ask most",
    "Pytanie podpisane przez kilku posłów liczy się dla każdego z nich.": "A question signed by several MPs counts for each of them.",
    "Wszyscy posłowie": "All MPs", "Treść pytań i odpowiedzi jest w serwisie Sejmu; tytuły prowadzą do niej.":
        "The questions and answers themselves are on the Sejm's site, in Polish; the titles link to them.",
    "Pytanie": "Question", "Odpowiedź": "Answer", "odpowiedź po": "answered after", "po terminie": "late",
    "brak odpowiedzi po terminie": "no answer, deadline passed", "termin przedłużony": "deadline extended",
    "czeka na odpowiedź": "awaiting an answer", "interpelacja": "interpellation", "zapytanie": "written question",
    "Szukaj w tytułach i adresatach…": "Search titles and recipients…", "Pokaż wszystkie": "Show all",
    "Nie udało się wczytać listy.": "The list could not be loaded.",
    "Łącznie z pytaniami podpisanymi wspólnie z innymi posłami. Tytuł prowadzi do treści pytania i odpowiedzi w serwisie Sejmu.":
        "Including questions co-signed with other MPs. The title links to the question and answer on the Sejm's site.",
    "posłów klubu, w czasie gdy do niego należeli": "by the club's MPs while they belonged to it",
    "Wszystkie kluby i ministrowie": "All clubs and ministers", "Najczęściej pytają": "Ask most often",
    "Do kogo najczęściej": "Asked most often",
    "Kadencje": "Terms", "Pierwsza kadencja w Sejmie": "First term in the Sejm", "kadencja w Sejmie": "term in the Sejm",
    "liczone od III kadencji (1997); API Sejmu nie ma danych o wcześniejszych":
        "counted from the III term (1997); the Sejm API has no data on earlier ones",
    "złożonych samodzielnie / podpisanych z innymi posłami": "filed alone / co-signed with other MPs",
    "miejsce w Sejmie pod względem liczby pytań (mediana posła": "place in the Sejm by number of questions (median MP",
    "Brak interpelacji i zapytań poselskich w tej kadencji.": "No interpellations or written questions this term.",
    "Mediana posła to": "The median MP has", "bez żadnego pytania jest": "MPs without a single question:",
    "posłów.": "MPs.", "Interpelacje i zapytania wszystkich posłów": "Interpellations and written questions of all MPs",
    "Mandat wygasł przed końcem kadencji, więc porównanie z innymi posłami jest przybliżone.":
        "The mandate ended before the end of the term, so the comparison with other MPs is only approximate.",
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
    "podpisanych poprawek i wniosków przeszło w głosowaniu": "of the signed amendments and motions passed",
    "przeszło": "passed", "Podpisane poprawki: przeszło": "Signed amendments: passed",
    "ile podpisanych poprawek i wniosków przeszło w głosowaniu, z ilu": "how many of the signed amendments and motions passed, out of how many",
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
    # home page: broadcasts, interests, events in the reader's topics, suggested MPs (static/home.js)
    "Transmisje Sejmu": "Sejm broadcasts", "Na żywo — trwa transmisja z Sejmu": "Live — the Sejm is on air now",
    "Oglądaj transmisję": "Watch the broadcast", "Inne trwające transmisje": "Other broadcasts under way",
    "Transmisja zaplanowana na teraz": "Broadcast scheduled for now", "od": "from",
    "Nie potwierdziliśmy jeszcze, że transmisja się rozpoczęła.": "We have not yet confirmed that the broadcast has started.",
    "Następna transmisja z Sejmu": "Next broadcast from the Sejm", "Najbliższe posiedzenie Sejmu": "Next sitting of the Sejm",
    "Zobacz szczegóły": "See the details", "Sprawdź transmisje Sejmu": "See the Sejm's broadcasts",
    "Nie mamy obecnie potwierdzonego terminu następnej transmisji.": "There is no confirmed date for the next broadcast at the moment.",
    "Nie udało się pobrać danych o transmisjach z API Sejmu.": "Could not get broadcast information from the Sejm's API.",
    "Co Cię interesuje?": "What are you interested in?",
    "Wybierz tematy, które chcesz śledzić. Pokażemy Ci najważniejsze wydarzenia i głosowania z tych obszarów.":
        "Pick the topics you want to follow. We will show you the main events and votes in them.",
    "Zapisz moje zainteresowania": "Save my interests", "Pomiń": "Skip", "Anuluj": "Cancel",
    "Wybierz co najmniej jeden temat albo pomiń ten krok.": "Pick at least one topic, or skip this step.",
    "Wybór zostaje w tej przeglądarce. Nie wysyłamy go nigdzie.": "Your choice stays in this browser. We do not send it anywhere.",
    "Wybierz zainteresowania": "Pick your interests",
    "Możesz wybrać tematy, które Cię interesują — pokażemy wtedy, co się w nich wydarzyło.":
        "You can pick the topics you are interested in, and we will show what happened in them.",
    "Zmień zainteresowania": "Change interests",
    "Czy Twoje zainteresowania się zmieniły?": "Have your interests changed?", "Ostatnio interesowały Cię": "Lately you followed",
    "Tak, chcę je zmienić": "Yes, change them", "Nie, bez zmian": "No, keep them",
    "Ważne dla Ciebie": "For you", "Zobacz, co wydarzyło się w Sejmie w sprawach, które obserwujesz.":
        "What happened in the Sejm in the matters you follow.", "Obserwujesz": "You follow",
    "Ostatnie wydarzenia w Twoich tematach": "Latest in your topics",
    "Głosowania, etapy prac nad projektami i punkty porządku obrad z ostatnich {n} dni, od najnowszych.":
        "Votes, stages of bills and agenda items from the last {n} days, newest first.",
    "Widzisz to, bo obserwujesz": "You see this because you follow", "komisja:": "committee:",
    "Nie znaleźliśmy nowych wydarzeń w wybranych przez Ciebie tematach.": "We found no new events in the topics you picked.",
    "Co dzieje się w Sejmie": "What is happening in the Sejm", "Nie udało się wczytać wydarzeń.": "Could not load the events.",
    "Etap prac": "Stage", "W porządku obrad": "On the agenda",
    "Posłowie, którzy mogą Cię zainteresować": "MPs you may want to follow",
    "Dobór według udokumentowanej pracy w wybranych tematach: funkcji w komisjach, interpelacji i zapytań oraz podpisanych projektów — nie według poglądów ani klubu.":
        "Picked by documented work in your topics: committee roles, interpellations and questions, and bills signed — not by views or club.",
    "Za mało danych o pracy posłów w tych tematach, by kogoś zaproponować.": "Too little data on MPs' work in these topics to suggest anyone.",
    "Wybierz zainteresowania, a zaproponujemy posłów, którzy zajmują się tymi tematami.":
        "Pick your interests and we will suggest MPs who work on those topics.",
    "Powiązane tematy": "Related topics", "Dlaczego może Cię zainteresować:": "Why you may want to follow them:", "członek": "member",
    "{n} interpelacji i zapytań, w tym {recent} w ostatnich 90 dniach": "{n} interpellations and questions, {recent} of them in the last 90 days",
    "Wśród autorów projektów w temacie {topic} ({n}), ostatnio": "Among the authors of bills on {topic} ({n}), most recently",
    "Zobacz profil posła": "See the MP's profile", "i {n} więcej na profilu posła": "and {n} more on the MP's profile",
    # home page, was / now / next and the interests flow (design of October 2026)
    "Transmisja": "Broadcast", "Na żywo": "Live", "Trwa transmisja z Sejmu": "The Sejm is on air",
    "{n}. dzień obrad": "day {n}", "otwiera się w nowej karcie": "opens in a new tab",
    "+1 inna transmisja": "+1 other broadcast", "+{n} inne transmisje": "+{n} other broadcasts", "+{n} innych transmisji": "+{n} other broadcasts",
    "Teraz nie ma transmisji": "Nothing on air now", "Następna": "Next",
    "Posiedzenie Sejmu": "Sejm sitting", "Godzinę pokażemy, gdy pojawi się w harmonogramie.": "We will show the time once it is in the schedule.",
    "Harmonogram transmisji": "Broadcast schedule",
    "Nie udało się sprawdzić statusu transmisji.": "Could not check whether anything is on air.",
    "Nie pokazujemy statusu, którego nie możemy potwierdzić.": "We do not show a status we cannot confirm.",
    "Transmisja: iTV Sejm, status potwierdzony przed chwilą · posiedzenia: API Sejmu RP · czas polski":
        "Broadcast: iTV Sejm, confirmed a moment ago · sittings: the Sejm's API · Polish time",
    "Transmisje: iTV Sejm, sprawdzono {when} · posiedzenia: API Sejmu RP · czas polski":
        "Broadcasts: iTV Sejm, checked {when} · sittings: the Sejm's API · Polish time",
    "Transmisje: brak odpowiedzi iTV Sejm · posiedzenia: API Sejmu RP, stan z {when}":
        "Broadcasts: no answer from iTV Sejm · sittings: the Sejm's API, as of {when}",
    "Posiedzenia: API Sejmu RP, stan z": "Sittings: the Sejm's API, as of", "czas polski": "Polish time",
    "Sprawdzamy, czy trwa transmisja…": "Checking whether the Sejm is on air…",
    "Wyniki posiedzenia": "Results of the sitting", "głosowanie": "vote", "głosowania": "votes",
    "punkt w porządku obrad": "item on the agenda", "punkty w porządku obrad": "items on the agenda",
    "Wybierz tematy, które chcesz śledzić. Pokażemy Ci wydarzenia i głosowania z tych obszarów.":
        "Pick the topics you want to follow. We will show you the events and votes in them.",
    "Możesz wybrać kilka tematów": "You can pick several topics", "Pomiń na razie": "Skip for now",
    "Nie wybrano jeszcze tematów": "No topics picked yet", "Wybrano 1 temat": "1 topic picked",
    "Wybrano {n} tematy": "{n} topics picked", "Wybrano {n} tematów": "{n} topics picked",
    "Zapisano Twoje zainteresowania": "Your interests are saved", "Tematy możesz wybrać w każdej chwili.": "You can pick topics at any time.",
    "Wybierz tematy": "Pick topics", "Zmień tematy": "Change topics", "Zamknij przypomnienie": "Close the reminder",
    "Wszystkie wydarzenia w Twoich tematach z ostatnich {n} dni": "Everything in your topics from the last {n} days",
    "Pojawią się tu, gdy wybierzesz tematy.": "They will appear here once you pick topics.",
    "Widzisz to, ponieważ obserwujesz": "You see this because you follow",
    "Wniosek o odrzucenie projektu": "Motion to reject the bill", "Wniosek Senatu o odrzucenie ustawy": "Senate's motion to reject the act",
    "Głos. nr {n}": "Vote {n}", "całość": "as a whole", "Punkt {n}": "Item {n}",
    "Zdarzenie": "Event", "Sprawa": "Matter", "Temat": "Topic",
    "Nie było głosowań nad poprawkami.": "There were no votes on amendments.",
    "Wcześniej: {n} nad poprawkami i wnioskami, przyjęto {k}.": "Before it: {n} on amendments and motions, {k} adopted.",
    "1 głosowanie": "1 vote", "{n} głosowania": "{n} votes", "{n} głosowań": "{n} votes",
    "Poprawki i wnioski do projektu": "Amendments and motions to the bill",
    "Temat przypisany na podstawie projektu, którego dotyczą poprawki": "Topic taken from the bill the amendments are to",
    "Szczegóły głosowania": "Vote details", "Przebieg prac": "Progress of the bill", "Zobacz poprawki": "See the amendments",
    "nadchodzące": "upcoming", "Między posiedzeniami": "Between sittings",
    "Gdy wybierzesz tematy, zaproponujemy posłów aktywnych w tych obszarach.": "Once you pick topics, we will suggest MPs active in them.",
    "Dlaczego może Cię zainteresować?": "Why you may want to follow them", "Pokaż kolejnych: {n}": "Show {n} more",
    "Po jednym z każdego klubu i koła: kto najwięcej pracuje nad Twoimi tematami — w komisjach, interpelacjach i projektach ustaw.":
        "One from each club and group: whoever works most on your topics — in committees, interpellations and bills.",
    # broadcast schedule (transmisje.html, static/schedule.js)
    "Transmisje z Sejmu: obrady, komisje, podkomisje, zespoły parlamentarne i konferencje — dziś i w najbliższych dniach, z porządkiem i salą.":
        "Broadcasts from the Sejm: sittings, committees, subcommittees, parliamentary groups and conferences — today and in the coming days, with the agenda and room.",
    "Obrady Sejmu, komisje, podkomisje, zespoły parlamentarne i konferencje — dziś i w najbliższych dniach.":
        "Sittings of the Sejm, committees, subcommittees, parliamentary groups and conferences — today and in the coming days.",
    "Obrady Sejmu": "Sejm sittings", "Podkomisja": "Subcommittee", "Konferencja": "Conference", "Zespół i inne": "Group and other",
    "Komisje i podkomisje": "Committees and subcommittees", "Zespoły, konferencje i inne": "Groups, conferences and other",
    "Komisje z moich tematów": "Committees in my topics", "dziś": "today", "jutro": "tomorrow", "Teraz": "Now",
    "Teraz nic nie jest transmitowane.": "Nothing is on air now.",
    "w planie na teraz, bez potwierdzonego obrazu": "scheduled for now, no picture confirmed",
    "Oglądaj tutaj": "Watch here", "Odtwórz nagranie": "Play the recording", "Zamknij odtwarzacz": "Close the player",
    "Nie udało się odtworzyć tutaj.": "Could not play it here.", "Odtwarzacz Sejmu": "Sejm's player", "Porządek": "Agenda", "Sala": "Room",
    "W harmonogramie nie ma transmisji w najbliższych dniach.": "No broadcasts are scheduled for the coming days.",
    "Nic w wybranym rodzaju transmisji. Zmień filtr powyżej.": "Nothing of that kind. Change the filter above.",
    "Nie udało się pobrać harmonogramu z API Sejmu.": "Could not get the schedule from the Sejm's API.",
    "Źródło: API Sejmu RP (transmisje), sprawdzono {when} · czas polski. Harmonogram może się zmieniać.":
        "Source: the Sejm's API (broadcasts), checked {when} · Polish time. The schedule may change.",
    "1 transmisja": "1 broadcast", "{n} transmisje": "{n} broadcasts", "{n} transmisji": "{n} broadcasts",
    "Wczytujemy harmonogram…": "Loading the schedule…",
    "Harmonogram wczytuje się z API Sejmu i wymaga JavaScriptu.": "The schedule loads from the Sejm's API and needs JavaScript.",
    "Transmisje na stronie Sejmu": "Broadcasts on the Sejm's website",
    "więcej": "more",
    "Sejmomat na żywo": "Sejmomat live", "Relacja na żywo z komentarzem i wynikami głosowań": "Live coverage with commentary and vote results",
    "Sejmomat": "Sejmomat",
    "Wszyscy posłowie": "All MPs", "W tej sekcji": "In this section",
    "Następne posiedzenie": "Next sitting",
    "Kalendarz posiedzeń": "Calendar of sittings",
    "Porządek obrad nie został jeszcze opublikowany.": "The agenda has not been published yet.",
    "Nie znamy jeszcze terminu następnego posiedzenia.": "The date of the next sitting is not known yet.",
    # stages of a bill (the Sejm's names), shown on the home page
    "Projekt wpłynął do Sejmu": "Bill submitted to the Sejm", "I czytanie na posiedzeniu Sejmu": "First reading in the chamber",
    "I czytanie w komisjach": "First reading in committee", "II czytanie na posiedzeniu Sejmu": "Second reading",
    "III czytanie na posiedzeniu Sejmu": "Third reading", "Uchwalono": "Passed", "Stanowisko Senatu": "Senate's position",
    "Prezydent podpisał ustawę": "Signed by the President", "Wniosek Prezydenta (weto)": "President's veto",
    "Wycofano": "Withdrawn", "Prezydent skierował ustawę do Trybunału Konstytucyjnego": "Referred by the President to the Constitutional Tribunal",
    "nie uchwalona ponownie po wecie Prezydenta": "Not passed again after the President's veto",
    # header, breadcrumbs, home page links
    "Główna nawigacja": "Main navigation", "Ścieżka nawigacji": "Breadcrumb", "Menu": "Menu", "Szukaj…": "Search…",
    "Głosowanie na żywo": "Live vote", "Przyjęte poprawki": "Adopted amendments", "Zgłoszone poprawki": "Amendments proposed",
    "Statystyki": "Statistics", "Wszystkie głosowania tego posiedzenia": "All votes of this sitting",
    "Wszystkie posiedzenia": "All sittings", "Wszystkie ustawy": "All bills",
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


def date_range_fmt(lang):
    """"20–22 października 2026" / "October 20–22, 2026"; a day alone as date_fmt has it."""
    one = date_fmt(lang)

    def fmt(first, last):
        a = datetime.fromisoformat(first) if isinstance(first, str) else first
        b = datetime.fromisoformat(last) if isinstance(last, str) else last
        if a.date() == b.date():
            return one(a)
        if (a.year, a.month) != (b.year, b.month):
            return f"{one(a)} – {one(b)}"
        return f"{a.day}–{one(b)}" if lang == "pl" else f"{MONTHS[lang][a.month - 1]} {a.day}–{b.day}, {a.year}"
    return fmt


def plural_fmt(lang):
    """n | plural("punkt", "punkty", "punktów"): the Polish form for n; in
    English the first form for 1, else the second (each passed through _())."""
    def fmt(n, one, few, many):
        if lang != "pl":
            return one if n == 1 else few
        if n == 1:
            return one
        return few if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else many
    return fmt


def pct_fmt(lang):
    def fmt(x):
        s = f"{x * 100:.1f}"
        return (s.replace(".", ",") if lang == "pl" else s) + "%"
    return fmt
