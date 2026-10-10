# Sejmomat

Statyczna strona z głosowaniami Sejmu RP, w której każde głosowanie nad poprawką
jest powiązane z jej treścią, autorem i rekomendacją komisji, a wynik pokazany
jest w podziale na kluby — wraz z posłami wyłamującymi się z linii klubu.

## How it works

```
api.sejm.gov.pl ──fetch──> data/ (committed) ──build──> site/ (static HTML) ──> GitHub Pages
```

- `python -m sejmomat fetch` downloads votings (with individual ballots) and the
  prints they cite into `data/`. Old sittings are fetched once; the newest
  `REFRESH_LAST_SITTINGS` are re-fetched every run to pick up corrections.
  Print PDFs are converted to text (`pdftotext`; for scans the .docx
  attachment or OCR) and only the text is kept.
- `python -m sejmomat build` parses amendments out of the print texts, links
  them to votings, computes club lines / rebellions and renders
  `site/`.
- `.github/workflows/update.yml` runs both daily, commits `data/` changes, builds
  a Pagefind search index and deploys to GitHub Pages.

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

The workflow builds the site and uploads it over FTPS to any static host
(Hostinger shared hosting here). Only changed files are uploaded: the
deploy action keeps a hash file (`.ftp-deploy-sync-state.json`) on the
server.

Repository settings → Secrets and variables → Actions:

| name | kind | example |
| --- | --- | --- |
| `FTP_SERVER` | secret | `ftp.example.pl` (hPanel → Files → FTP Accounts) |
| `FTP_USERNAME` | secret | `u123456789.example.pl` |
| `FTP_PASSWORD` | secret | |
| `SITE_URL` | variable | `https://example.pl/` |
| `FTP_DIR` | variable (optional) | `public_html/` (default) |
| `FTP_PROTOCOL` | variable (optional) | `ftps` (default) or `ftp` |

Then run the workflow once by hand (Actions → "Aktualizacja danych i
publikacja" → Run workflow). The first upload sends the whole site
(~400 MB) and takes a while; later runs send only what changed.

The build also writes `.htaccess` files for Apache/LiteSpeed hosts: CORS
for `/api/` (so other sites can use the JSON API) and compression.

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
