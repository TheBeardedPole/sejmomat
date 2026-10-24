# Working notes for Claude Code

Project notes for an AI assistant (or anyone) picking up work on Sejmomat.
README.md describes how the site works; this file is about how to work on
it and where things stand. Keep it free of personal data.

## How to work here

- **`main` is production.** A push to `main` touching `static/**` or
  `games/**` goes live within a minute ("Szybka publikacja"). Templates,
  Python and data go live only after a rebuild:
  `gh workflow run update.yml -f fetch=false` (about 10 minutes; a change
  to every MP or club page means a larger upload). Work on a branch and
  ask the owner before pushing to `main` or starting a rebuild.
- **Workflow files need a special login.** GitHub refuses pushes that
  change `.github/workflows/` unless the `gh` login has the `workflow`
  scope (`gh auth refresh -h github.com -s workflow`). Keep workflow edits
  in their own commit so the rest can be pushed regardless.
- **Local build:** a virtualenv with `requirements.txt`, then
  `python -m sejmomat build` (about a minute; writes `site/`). Serve
  `site/` with `python -m http.server` to look at it. CI runs Python 3.12.
- **Checking changes:** there are no committed tests. What worked: Node
  scripts that `require()` `games/sejmdle/sejmdle.js` (its logic is
  exported for Node) to check puzzles against `api/v1/games.json`, and
  headless Chromium (puppeteer-core) against the local `site/` for pages,
  comparing what a page shows with figures computed from the build.
- **Data fetches:** `python -m sejmomat fetch` (CI does it on sitting
  days). Large one-off downloads are run locally, not in CI, and the
  resulting `data/` is committed.

## State (14 October 2026)

Live on sejmomat.pl:

- **Day summaries** (`sejmomat/social.py`, `sejmomat/card.py`,
  `podsumowania.html`, `api/v1/summaries.json`): per voting day a
  summary image with a "Zobacz więcej na sejmomat.pl" footer, a caption,
  and text posts; copy, download and share buttons. Figures come straight
  from the data, no language model. Images use Noto Sans (installed in
  `update.yml`).
- **Votes by sitting** on MP and club pages (`templates/_breakdown.html`,
  `static/breakdown.js`): per-sitting rows, each opening every vote, with
  missed votes and breaks of the club line flagged; sitting pages link to
  each club's breakdown (`klub/X.html#posiedzenie-N`).
- **Speeches in the chamber** (see README, "Speeches in the chamber").
  `sejmomat/speeches.py` fetches transcripts into
  `data/speeches/<date>.json` (the whole term from 13 November 2023 is
  committed; `fetch` adds new days, a few hundred requests per sitting
  day). MP, club and bill pages have a "Wystąpienia" section: word clouds
  on MP and club pages (Morfeusz 2 / SGJP dictionary forms, dependency
  `morfeusz2`; a click on a word in an MP's cloud searches their speeches
  in all its forms); MP and bill pages list speeches with text, video,
  transcript link and the bill's vote; voting pages link to the bill's
  debate. Full build: about 80–150 s and 2.2 GB of memory; speech files
  `dane/wystapienia/` 130 MB and `dane/debaty/` 94 MB.
- **Sejmdle independents:** the coalition/opposition conditions
  (Prezydium, Siatka) count each independent MP with the side they vote
  with: coalition if at least 60% of their ballots in the contested final
  votes matched the coalition majority's choice, opposition at 40% or
  less, otherwise neither.

- **Look:** the header logo is `static/logo.svg` (Monoton, drawn by
  `brand/make.py`, which also makes the social media images in
  `brand/out/`), shown as a CSS mask in the accent colour. Light/dark
  switch in the header (`data-theme` on `<html>`, localStorage
  `sejmomat-theme`, also read by Sejmdle). MP and club pages show their
  sections as tabs (`templates/_tabs.html`, script in `static/app.js`);
  ids inside a section still work as links. Club pages tag former members.
  Word clouds leave out the words of a club's name.
- **Images to share** on club and MP pages ("Grafika do udostępnienia"):
  a term overview and the latest sitting, in Polish. Club images are made
  with the site (`sejmomat/card.py`, `dane/karty/klub/`); an MP's is drawn
  in the reader's browser on a click (`static/card.js`, same layout as
  `card.py`; the photo comes from the Sejm's API, which allows it) and
  handed over as a download, with nothing kept. MP term images carry "TOP N%"
  badges (1, 5, 10 or 20) on turnout, speeches and questions, against the
  sitting MPs, ties counted against the MP (`build.mp_standing`); captions
  of the A-to-Z posts repeat them. The day summaries page
  (`podsumowania.html`) is for readers; the ready-made posts are only in
  `api/v1/summaries.json`.

- **Upcoming sitting** (`nadchodzace-posiedzenie.html`, also a card on the
  home page and the sittings list): the agenda of the next sitting or the
  one under way, from the Sejm's calendar (`sejmomat/agenda.py`,
  `data/proceedings.json`, refreshed by `fetch`), with items linked to
  prints, bills and the MPs who present them. Scheduled updates now also
  run in the 7 days before a sitting, when the agenda comes out and changes
  (`sejmomat/sitting_days.py`, LEAD_DAYS). On sitting days updates also run
  hourly, 8:00–1:59 Warsaw time (cron "17 * * * *", `sitting_days hourly`).
- **Live stream** (`static/live.js`, `_cards.live_box`, on the home page and
  the upcoming sitting page): on the sitting's days the browser asks
  `videos/today` for the plenary stream ("posiedzenie") and plays it muted
  with hls.js (lowest quality first, capped to the player's size). The
  Sejm's own player (`playerLinkIFrame`) cannot be framed: its bot
  protection loops. The API has no live "point under discussion";
  transcripts come out hours later.
- **Agenda on sitting pages** ("Porządek obrad" tab): `data/proceedings.json`
  keeps every sitting's agenda (`agenda.by_sitting()`; later lists continue
  from `<ol start>`). Item numbers are the speeches' "point" and the votes'
  "Pkt. N", which link each item to its speakers (transcript links), votes,
  and a recording per day (`speeches.item_clips`, played by `static/clips.js`).
  Right after a sitting the API's agenda is still the planned one (several lists,
  each numbered from 1; items renumbered and added at the sitting); then
  `agenda.renumber` numbers the items from the votes' "Pkt. N" and the speeches'
  points (by prints, else wording), adds items named only in votes, and lists the
  planned items never taken up last. Once the Sejm publishes the final agenda it
  fits and nothing changes.

- **Committees** (`komisje.html`, `komisja/<code>.html`, "Komisje" in the
  nav): members, meetings with agenda, joint committees, recording and
  transcript links; bills discussed (from print numbers on the agenda) also
  on bill pages ("W komisjach"); MP pages have a "Komisje" tab.
  `sejmomat/committees.py` keeps `data/committee_sittings.json`: one request
  per committee for the meetings, plus a HEAD request per meeting to see
  whether its transcript PDF is out. The API answers those slowly (the
  first full check took 5.5 hours, run locally); afterwards only meetings
  of the last 60 days still without a transcript are checked again.
  Transcripts are linked, not read: they have no times per speaker.

- **First-day club ids merged:** on 13 November 2023 three clubs voted
  under provisional ids (PSL, Nowa_Lewica, Polska2050) and switched the next
  day; `model.merge_opening_ids()` counts those votes under the lasting id
  (PSL-TD, Lewica, Polska2050-TD) when the data is loaded. The later, real
  Polska2050 club is unaffected.
- **RCL link** on government bill pages (`data/rcl.json`, from the Sejm
  API's process records; `fetch.fetch_rcl()`). RCL's own site disallows
  crawling (robots.txt `Disallow: /`), so we only link to it; a request to
  RCL for data is up to the owner. Favicon: `static/favicon.*`, made by
  `brand/make.py`.

- **Interpellations and written questions** (`interpelacje.html`, nav
  "Interpelacje"; "Interpelacje" tabs on MP and club pages; a column on the
  MP list): `sejmomat/questions.py` keeps `data/questions.json` (no texts;
  titles link to the Sejm), refreshed in full by `fetch` (about 50 requests,
  a minute). Figures: answered share, median days to the first real answer
  (deadline extensions do not count), answers after the deadline
  (answerDelayedDays), unanswered past the 21 days. MP pages show the
  latest 100; the rest load from `dane/pytania/<id>.json`
  (`static/questions.js`). "Metodologia" moved from the nav to the footer
  to keep the header on one line.

- **Posts to share by hand** (`python -m sejmomat.posts [date] [--days N]`,
  `sejmomat/posts.py`): writes `posts/<date>/` (not in git) with images
  and `posts.txt` (caption and alt text each). "MPs from A to Z": the MPs
  serving on 18 October 2026 by surname, fixed in `data/posts_order.json`,
  1 and 2 on alternate days, from 18 October 2026 (the last on 20 August 2027); a club and a
  minister once a week each; the voting-day summary the morning after.
  Cards: `card.mp_term` (the browser's `static/card.js` draws the same),
  `card.minister`, `card.club_term`. Needs a `git pull` first, about 2
  minutes (it loads the whole build context).

- **Terms served** on MP pages, the MP list ("Kadencje") and the MP cards:
  matched by name and birth date in `data/past_terms.json` (MP lists of the
  earlier terms, fetched once by `fetch.fetch_past_terms()`). The API has
  them only from the III term (1997), so counts are "od 1997" where the
  record reaches back that far. Social media images carry the white
  wordmark (`static/logo-white.png`, made by `brand/make.py`) in the footer;
  MP posts use #SejmOdADoZ (also on their images) and emoji bullets; terms
  are spelt out ("szósta kadencja"). Post captions carry no links, not even
  the bare domain (the owner's rule: links cut reach); the images name
  sejmomat.pl in their footer.

- **Sejmdle is daily:** the endless test mode is gone; one set of puzzles
  a day, numbered from 1 October 2026 (#1), and an archive picker
  (`?dzien=YYYY-MM-DD`) to play any earlier day; shared results link to
  their day. Past puzzles are drawn from today's data, so a day's puzzle
  can shift slightly as data grows.
- **"Uzupełnij słowo"** (Sejmdle tab, daily, in the archive): three passages
  of real speeches a day with 2, 3 and 4 blanks (`sejmomat/fillgaps.py`,
  `api/v1/slowa/<day>.json`, written 60 days ahead since the site is not
  rebuilt daily). Speakers' clubs in turn; passages naming parties, clubs
  or MPs are left out; blanks are frequent nouns/adjectives whose word does
  not come up again in the passage. Other forms of the word (Morfeusz
  generate) earn 2 points instead of 3. A day uses speeches from at least
  two days before it.
- **"Twarze w minutę"** (Sejmdle tab): as many MP photos named as possible
  in 60 seconds (+1 right, −1 wrong, skipping free), with daily and all-time
  leaderboards (nickname only). The one server-side piece:
  `server/speedrun.php`, copied by the build to `/srv/speedrun.php` (PHP on
  Hostinger). It deals the run inside an encrypted token, serves the photos
  (so their addresses do not give the answers away), checks and timestamps
  every answer (revealed only once given; none after the minute) and
  finishes each run once; nicknames are filtered. Data (JSON files with
  locking, secret key, cached photos) goes to `domains/sejmomat.pl/speedrun-data`
  outside the web folder, or `srv/data/` (closed to the web, excluded from
  the upload's delete) if the host does not allow that. Address hashes for
  rate limiting are deleted after three days. Test locally with
  `podman run -p 127.0.0.1:8800:8800 -v "$PWD/site":/app:Z -w /app php:8.3-cli php -S 0.0.0.0:8800`.
- **Upload retries:** the deploy step tries rsync three times, a minute
  apart (the host's SSH times out now and then).

- **Own stream with captions** (`tools/livestream.py`, run locally, not part of
  the site): the Sejm's plenary stream through ffmpeg, ~100 s behind live (or a
  replay from `--at "YYYY-MM-DD HH:MM"`), with a caption box in the bottom left (the cards' style) for the agenda item,
  its tags and the latest vote with its result, each shown when the picture
  reaches it (the clock is ffmpeg's position, not the wall clock). Out to a
  preview window, a file, or RTMP (`SEJMOMAT_RTMP`, `--out rtmp`). The live DVR
  playlists respect `start`; with `stop` the archive answers and ignores it.
  Between votes: the speaker read from the broadcast's caption (with a
  Koalicja/Opozycja tag) and fact cards from `api/v1/ciekawostki.json`
  (`sejmomat/facts.py`), one every 90 s, related cards kept apart; during a
  longer speech the speaker's club's Top 5s; one card in 8 points to Sejmdle
  or buycoffee (not with `--demo`).
  On a server: `tools/vps/setup.sh` (Debian/Ubuntu, clones to `/opt/sejmomat`)
  installs the `sejmomat-live` systemd service (`--wait`: waits for the day's
  sitting; key in `/etc/sejmomat-live.env`) and `sejmomat-pull.timer` (git pull
  every 10 min, for the amendment prints CI commits on sitting days);
  `tools/vps/test-stream.sh` sends a replay to the same address as a test.
  The video CDN (blueonline) answers only Polish addresses (its picker also hands
  out edges inside Vectra's network; `FALLBACK_EDGES` lists one that answers
  elsewhere in Poland): a server abroad fetches the video through a proxy in Poland,
  `SEJMOMAT_VIDEO_PROXY` (tinyproxy, `tools/vps/proxy-setup.sh`, limited to the
  stream server and *.blueonline.tv).
  Captions name the item from the vote's own title: the API's agenda is the planned
  one (several lists, each from 1) and items are renumbered at the sitting.
- **Clips of past sittings** (`tools/clips.py`, run on a Polish address, writes
  `clips/`, not in git): `list` (closest decisive votes, one per bill), `bill
  S:N` (the debate that led to the vote, the latest day up to it with 8+ speeches
  on the bill's prints, then its votes), `votes DAY`; a title and description
  per video. Uses `livestream.py --fast --transcript` (speakers from
  data/speeches, no OCR; file output at constant quality, finished properly).

Waiting on the owner:

- **Posting day summaries** (no social media accounts yet) (`.github/workflows/social.yml`): to X
  and/or Bluesky, off until the repository variable `SOCIAL_AUTOPOST` is
  `true`; needs secrets `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`,
  `X_ACCESS_TOKEN_SECRET` and/or `BLUESKY_HANDLE`,
  `BLUESKY_APP_PASSWORD` (the X API is paid per post). A manual run
  without "publish" only shows what would be posted.
- Scheduled data updates are paused until the date in the repository
  variable `PAUSE_SCHEDULED_UNTIL`.
- **Google Analytics:** ready but off. Setting the repository variable
  `GA_MEASUREMENT_ID` ("G-...") and rebuilding turns it on: the build adds
  `<meta name="sejmomat-ga">`, `static/app.js` loads gtag only after
  "Zgadzam się", the consent text and version change (everyone is asked
  again) and the privacy page gets its GA section. "Tylko niezbędne"
  removes the `_ga` cookies. Sejmdle has no analytics.

Known gaps in the speeches:

- 25 spoken speeches (mostly the first sitting, November 2023) get no
  video clip: their times fall outside the day's listed video.
- Words that change inside (rolnik, rolniczy, rolnictwo) stay separate
  words in the clouds; only "-owy" adjectives join their noun.
