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

Waiting on the owner:

- **Posting day summaries** (`.github/workflows/social.yml`): to X
  and/or Bluesky, off until the repository variable `SOCIAL_AUTOPOST` is
  `true`; needs secrets `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`,
  `X_ACCESS_TOKEN_SECRET` and/or `BLUESKY_HANDLE`,
  `BLUESKY_APP_PASSWORD` (the X API is paid per post). A manual run
  without "publish" only shows what would be posted.
- Scheduled data updates are paused until the date in the repository
  variable `PAUSE_SCHEDULED_UNTIL`.

Known gaps in the speeches:

- 25 spoken speeches (mostly the first sitting, November 2023) get no
  video clip: their times fall outside the day's listed video.
- Words that change inside (rolnik, rolniczy, rolnictwo) stay separate
  words in the clouds; only "-owy" adjectives join their noun.
