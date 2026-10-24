# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

All four of these audiences are primary, and the same pages serve all of them:

- **Curious citizens** who want to check how their MP or a club voted. They often arrive on a phone from a search or a shared post.
- **Journalists and researchers** who need exact figures, amendment texts and the JSON API (`/api/v1/`) for stories and analysis.
- **Activists and party staff** who track club-line rebellions and opponents' votes and make shareable graphics.
- **Social media followers** reached by the daily summary cards and #SejmOdADoZ posts. For them the site is where they land.

## Product Purpose

Sejmomat makes the Polish Sejm's voting record readable and checkable. It shows every vote, split by club, with the MPs who broke their club's line. Each amendment vote is tied to the amendment's text, its author and the committee's recommendation. Success means anyone can go from "how did they vote?" to the evidence in a few clicks, and can trust and cite what they find.

## Positioning

- Each amendment vote is linked to the amendment's text, its author and the committee's recommendation.
- Word-level diffs show what an amendment actually changes in the bill or act (`sejmomat/changes.py`).
- Results are split by club, with MPs who break the club line flagged.
- Shareable summaries and images are computed straight from the data, with no language model.
- Breadth in one cross-linked place: votes, bills, speeches (with word clouds), committees, interpellations, the agenda, the live stream and the Sejmdle games.

## Operating Context

- The site is static, rebuilt from data in `api.sejm.gov.pl` (and ELI for act texts) by GitHub Actions on sitting days. It is hosted on Hostinger shared hosting and has about 18,000 HTML pages.
- Polish is the primary language. There is an English version under `/en/`.
- Readers often come from social posts, so a lot of traffic lands on a phone deep inside the site (an MP, club or vote page) rather than on the home page.
- Content is shared outward as images, captions, text posts and the open JSON API (CORS enabled).

## Capabilities and Constraints

- A template change re-uploads every page. Site-wide extras (consent bar, support links, footer privacy links) are therefore injected by `static/app.js`, not by templates.
- The site has no accounts, forms or newsletter. Search (Pagefind) runs in the browser. The only server-side piece is `server/speedrun.php` for the "Twarze w minutę" leaderboard.
- Analytics load only after consent. MP photos and recordings come from the Sejm.
- Data limits: the API has no live "point under discussion", transcripts come out hours later, past terms reach back only to 1997, and committee transcripts are linked, not read.
- Light and dark themes are switched by the reader (`data-theme`, saved in localStorage).

## Brand Commitments

- Name: Sejmomat (sejmomat.pl). The wordmark is drawn in Monoton by `brand/make.py`, which also makes the favicon and social images.
- **Strictly nonpartisan.** Every club is treated the same, and the site shows data without judging it. No design, copy, colour or ordering choice may favour or disfavour a party.
- Figures are never invented or estimated by a model. Everything shown traces back to Sejm data.
- Post captions carry no links; the images name sejmomat.pl in their footer.
- It is a non-commercial project run by a private individual, supported by voluntary donations (buycoffee).

## Evidence on Hand

- The full term's data from 13 November 2023, committed in `data/`: votes with individual ballots, prints, speeches, committee meetings and interpellations.
- Generated share cards and day summaries (`dane/karty/`, `api/v1/summaries.json`) and brand assets (`brand/out/`).
- There are no testimonials, usage figures or press mentions on record. Don't invent any.

## Product Principles

1. **Evidence over assertion:** every number links back to the vote, text or source it came from.
2. **Even-handed by construction:** the same treatment, order and visual weight for every club.
3. **Readable by anyone, citable by experts:** plain answers first, with full detail one step away.
4. **Shareable from the data:** anything worth sharing should export cleanly and without manual editing.
5. **Lean and static:** fast pages on modest hosting, and no tracking without consent.
