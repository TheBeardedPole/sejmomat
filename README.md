# Sejmomat

Statyczna strona z głosowaniami Sejmu RP, w której każde głosowanie nad poprawką
jest powiązane z jej treścią, autorem i rekomendacją komisji, a wynik pokazany
jest w podziale na kluby — wraz z posłami wyłamującymi się z linii klubu.

## How it works

```
api.sejm.gov.pl ──fetch──> data/ (committed) ──build──> site/ (static HTML + JSON API) ──rsync──> web host
```

- `python -m sejmomat fetch` downloads votings (with individual ballots) and the
  prints they cite into `data/`. Old sittings are fetched once; the newest
  `REFRESH_LAST_SITTINGS` are re-fetched every run to pick up corrections.
  Print PDFs are converted to text (`pdftotext`; for scans the .docx
  attachment or OCR) and only the text is kept.
  When a run brings new votes or prints, the consolidated texts of newly
  amended acts are fetched from the ELI API into `data/acts` as well.
- `python -m sejmomat build` parses amendments out of the print texts, links
  them to votings, computes club lines / rebellions and renders
  `site/`.
- `.github/workflows/update.yml` runs both twice a day on Sejm sitting days and
  the two days after (checked against the Sejm's calendar; manual runs always
  go ahead), commits `data/` changes, builds a Pagefind search index and
  uploads the site.

### Modules

| module | role |
| --- | --- |
| `api.py` | HTTP client for api.sejm.gov.pl |
| `fetch.py` | download votings, MPs, clubs, prints |
| `textract.py` | PDF → text, DOCX → numbered paragraphs |
| `refs.py` | parse print numbers from titles, amendment numbers from topics |
| `amendments.py` | split reports / Senate resolutions into numbered amendments |
| `changes.py` | word-level diffs for "wyrazy „X” zastąpić wyrazami „Y”" instructions |
| `analysis.py` | club lines, rebellions |
| `model.py` | load data, pick the right print for each voting, link amendments |
| `build.py` | render Jinja templates into `site/` |

## Running locally

Requires Python 3.10+, `pdftotext` (poppler-utils) and, for scanned prints,
Tesseract with Polish data (`dnf install tesseract tesseract-langpack-pol` /
`apt install tesseract-ocr tesseract-ocr-pol`). Without Tesseract, scanned
prints that have no .docx attachment stay unparsed until OCR is available.

```sh
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m sejmomat fetch    # first run downloads the whole term (~1 h)
.venv/bin/python -m sejmomat build
npx pagefind --site site                 # optional: search index
python -m http.server -d site 8000
```

## Deploying

The workflow builds the site and copies it to the web host (Hostinger
shared hosting here) with rsync over SSH. Only files whose content changed
are sent, and files no longer in the build are removed from the server.

Repository settings → Secrets and variables → Actions:

| name | kind | value |
| --- | --- | --- |
| `SSH_PRIVATE_KEY` | secret | private half of a deploy key; add the public half in hPanel → Advanced → SSH Access |
| `SSH_USERNAME` | secret | SSH user, e.g. `u123456789` |
| `SSH_HOST` | secret | server IP (falls back to `FTP_SERVER` if unset) |
| `SITE_URL` | variable | `https://example.pl/` |
| `SSH_PORT` | variable (optional) | `65002` (default, Hostinger) |
| `SSH_DIR` | variable (optional) | default `domains/<domain from SITE_URL>/public_html/` |
| `SSH_KNOWN_HOSTS` | variable (optional) | the server's host key line, to pin it |

"Test połączenia SSH" (Actions tab) checks the login and the target folder
in a few seconds. Everything in the target folder that is not part of the
build is deleted on deploy, except `.well-known/`.

After changing templates or page text, run the main workflow with "fetch"
switched off (`gh workflow run update.yml -f fetch=false`): it skips the
Sejm download, rebuilds, and uploads only the pages that changed.

Changes to `static/` (styles, scripts) or `games/` do not need the full
run: pushing them to `main` starts "Szybka publikacja (style, skrypty, gry)",
which copies just those folders to the host in well under a minute.

Caching: HTML is sent with `Cache-Control: no-cache` (always revalidated),
while scripts and styles are cached for 10 minutes by browsers and the
host's CDN. Pages name them by content version (`app.js?v=<hash>`), so
after a full build the new files load at once. After the fast path alone,
the main site's pages still carry the previous version and pick up the new
script within about 10-20 minutes; the games page is re-stamped by the fast
path and updates immediately.

The build also writes `.htaccess` files for Apache/LiteSpeed hosts: CORS
for `/api/` (so other sites can use the JSON API) and compression.

Site-wide extras (consent bar, support links, footer privacy links) are
added by `static/app.js`, not the page template: the site is ~18,000 HTML
files, and a template change means sending every one of them again.

## Sejmdle (games)

`games/sejmdle/` holds five daily games (guess the MP, "Czy przeszło?",
"Kim jestem?", "Prezydium", "Siatka") as plain HTML/CSS/JS. They read `api/v1/games.json` and are
copied to `/sejmdle/` as a test bench. To host them elsewhere, copy the
folder and point the two `<meta name="sejmomat-…">` tags in `index.html`
at this site. The left-to-right order of clubs used by the first game is
`CLUB_AXIS` in `sejmomat/api_out.py`.

"Prezydium" (seven seats, each with one or two conditions) and "Siatka" (a
3×3 grid of row and column conditions) ask for MPs who fit, and the less
known the MP, the better. There are no statistics of players' answers: an
MP's popularity is their rank by election votes among the MPs fitting the
same slot. The conditions are built in `categories()` in `sejmdle.js`; the
clubs of the governing coalition are `COALITION` and the groups of
voivodeships are `MACRO_REGIONS` there — update `COALITION` when the
coalition changes.

## Votes by sitting (MPs and clubs)

Every MP page and club page has a table "Głosowania według posiedzeń": one
row of figures per sitting (for an MP: for / against / abstained / missed /
against the club line; for a club: its line, split votes, ballots not cast,
breaks). A click on a row loads that sitting's votes — an MP's ballot next
to the club line, with missed votes flagged; for a club, its MPs ranked by
votes missed and every vote with who did not vote or broke the line.

The rows are in the page; the votes come on demand from two files per
sitting shared by both languages, `dane/posiedzenia/N.json` (what was voted
on, outcome, every club's line) and `dane/glosy/N.json` (ballots). The
script is `static/breakdown.js`, loaded only by those pages and versioned
on its own, so changing it does not touch every page. `#posiedzenie-N` in
the address opens a sitting; sitting pages link to each club that way.

## Daily summaries for social media

`sejmomat/social.py` turns each voting day into a ready-made summary in
Polish: the day's figures (votes, laws and resolutions passed, amendment
votes), the most contested vote on a law with the clubs on each side, and
whose amendments passed. Everything is a filled-in template — every number
and name comes from the data, no language model is involved.

- `sejmomat/card.py` draws the summary as an image with the site's address
  in its footer (`dane/podsumowania/<day>.png`). It needs Pillow and Noto
  Sans or DejaVu Sans; without them the build goes on and the summaries
  are text only.
- The build lists the days in `api/v1/summaries.json` and on the page
  `podsumowania.html`: the image, a caption to post with it, and a text
  version (one post or a thread), with copy and download buttons and links
  that open X or Bluesky with the text filled in.
- `python -m sejmomat.social [YYYY-MM-DD]` prints a day's text posts locally.
- `python -m sejmomat.social post` publishes the newest summaries not yet
  posted — one post per day: the image, its description for screen readers,
  the caption and a link — on the services whose credentials are in the
  environment, and records them in `data/social.json`. `--dry-run` only
  shows them. A day goes out once it is over (or two hours after its last
  vote), and never if it is more than three days old.

Automatic posting is the workflow "Podsumowanie dnia w mediach
społecznościowych" (`.github/workflows/social.yml`). It is off until the
repository variable `SOCIAL_AUTOPOST` is `true`; run by hand, it shows what
would be posted unless "publish" is ticked. Secrets: `X_API_KEY`,
`X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET` (an X developer
app with write access; the X API is paid per post) and/or `BLUESKY_HANDLE`,
`BLUESKY_APP_PASSWORD` (free).

## Known limitations

- Amendment votes on items moved directly in the chamber (no printed report)
  cannot be linked; the page links to the official prints instead.
- PDF text extraction occasionally misreads characters (e.g. "lit. 1" for "lit. l").
- "Nadać brzmienie" amendments are shown in full but not yet diffed against the
  current bill/act text (planned: ELI API, `api.sejm.gov.pl/eli`).

## License

Code: [GNU General Public License v3.0](LICENSE) or later.
Data comes from the public [Sejm API](https://api.sejm.gov.pl) and
[ELI API](https://api.sejm.gov.pl/eli); parsed data is published as-is,
without warranty — the official prints are authoritative.

## Support

If you find this useful, you can support the project at
[buycoffee.to/adamkoscielak](https://buycoffee.to/adamkoscielak).
