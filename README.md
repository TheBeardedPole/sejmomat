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

`games/sejmdle/` holds three daily games (guess the MP, "Czy przeszło?",
"Kim jestem?") as plain HTML/CSS/JS. They read `api/v1/games.json` and are
copied to `/sejmdle/` as a test bench. To host them elsewhere, copy the
folder and point the two `<meta name="sejmomat-…">` tags in `index.html`
at this site. The left-to-right order of clubs used by the first game is
`CLUB_AXIS` in `sejmomat/api_out.py`.

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
