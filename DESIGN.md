---
name: Sejmomat
description: Parliamentary reading surfaces with GOV.UK-inspired colours and open licensed type.
colors:
  bg: "#ffffff"
  surface: "#ffffff"
  text: "#0b0c0c"
  muted: "#484949"
  line: "#cecece"
  accent: "#1a65a6"
  accent-bg: "#e8f1f8"
  section: "#f3f3f3"
  section-strong: "#e6e9eb"
  accent-hover: "#0f385c"
  button-bg: "#0f7a52"
  button-hover: "#0b5c3e"
  button-text: "#ffffff"
  dark-bg: "#141b22"
  dark-surface: "#1b2732"
  dark-text: "#f3f3f3"
  dark-muted: "#b5c1cb"
  dark-line: "#43515d"
  dark-accent: "#8bb8e8"
  dark-accent-bg: "#21364a"
  dark-section: "#1b2732"
  dark-section-strong: "#263747"
  dark-accent-hover: "#c2dcf7"
  dark-button-bg: "#87bca8"
  dark-button-hover: "#b3d7c8"
  dark-button-text: "#0b0c0c"
  focus: "#ffdd00"
  focus-ink: "#0b0c0c"
  header-background: "#0b0c0c"
  header-text: "#ffffff"
  brand: "#1d70b8"
  on-accent: "#ffffff"
  dark-on-accent: "#0d1b2e"
typography:
  display:
    fontFamily: "\"Source Serif 4\", Georgia, serif"
    fontSize: "clamp(2.5rem, 4.8vw, 3.5rem)"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-.02em"
  headline:
    fontFamily: "\"Source Serif 4\", Georgia, serif"
    fontSize: "clamp(1.9rem, 3.5vw, 2.75rem)"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-.02em"
  title:
    fontFamily: "\"Source Serif 4\", Georgia, serif"
    fontSize: "1.65rem"
    fontWeight: 700
    letterSpacing: "-.015em"
  sitting-title:
    fontFamily: "\"Source Serif 4\", Georgia, serif"
    fontSize: "1.7rem"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-.015em"
  interest-title:
    fontFamily: "\"Source Serif 4\", Georgia, serif"
    fontSize: "2rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-.015em"
  body:
    fontFamily: "\"Source Sans 3\", system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.55
  intro:
    fontFamily: "\"Source Sans 3\", system-ui, sans-serif"
    fontSize: "1.2rem"
    fontWeight: 400
    lineHeight: 1.55
  index:
    fontFamily: "\"Source Sans 3\", system-ui, sans-serif"
    fontSize: "1.15rem"
    fontWeight: 500
  label:
    fontFamily: "\"Source Sans 3\", system-ui, sans-serif"
    fontSize: ".9rem"
    fontWeight: 600
  observed-size-1:
    fontSize: ".82rem"
  observed-size-2:
    fontSize: ".88rem"
  observed-size-3:
    fontSize: ".8rem"
  observed-size-4:
    fontSize: ".92rem"
  observed-size-6:
    fontSize: "1.05rem"
  observed-size-9:
    fontSize: "1.1rem"
  observed-size-11:
    fontSize: "1.5rem"
  observed-size-14:
    fontSize: "1rem"
  observed-size-15:
    fontSize: "2.4rem"
rounded:
  square: "0"
  marker: "3px"
spacing:
  step-8: "8px"
  step-12: "12px"
  step-16: "16px"
  step-20: "20px"
  step-24: "24px"
  step-28: "28px"
  step-32: "32px"
  step-40: "40px"
  step-64: "64px"
components:
  button-primary:
    backgroundColor: "{colors.button-bg}"
    textColor: "{colors.button-text}"
    rounded: "{rounded.square}"
    padding: "12px 20px"
  button-primary-hover:
    backgroundColor: "{colors.button-hover}"
  button-secondary:
    backgroundColor: "{colors.section}"
    textColor: "{colors.text}"
    rounded: "{rounded.square}"
    padding: "12px 20px"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.square}"
    padding: "24px"
  search:
    backgroundColor: "{colors.section}"
    textColor: "{colors.text}"
    rounded: "{rounded.square}"
    height: "44px"
---
# Design System: Sejmomat

## Overview

**Creative North Star: "Katalog obywatelski"**

A parliamentary reading service with a GOV.UK-inspired functional palette: near-black masthead and white logo, blue links, green primary actions, neutral reading surfaces and yellow keyboard focus. Source Serif 4 and Source Sans 3 retain the earlier approved Stortinget-inspired typography; neither is Berlingske. Palette reference: https://design-system.service.gov.uk/styles/colour/.

The existing Monoton wordmark remains the identity asset. Results and club colours retain their data meaning; interface accents do not express political affiliation.

**Key Characteristics:**

- Serif headings paired with clear sans-serif evidence and controls.
- Ruled indexes, square controls and neutral grey sections.
- Equal visual treatment for every parliamentary club.

## Colors

### Primary

Blue identifies links and topic selection; hover deepens it and strengthens the underline. Pale blue marks interactive context. Green identifies primary actions; yellow is reserved for keyboard focus. The near-black masthead scopes white text and logo with a blue bottom rule.

### Neutral

White reading surfaces alternate with neutral grey sections. Near-black text carries records and darker grey carries metadata. Dark mode uses blue-charcoal surfaces, pale blue links and pale green actions. The masthead remains near-black with white controls in both themes. System preference applies until the reader selects a theme.

**The Evidence Colour Rule.** Keep result and club colours semantic; use blue for links, green for primary actions and yellow only for keyboard focus.

The inherited result palette in `static/style.css` remains green for yes/adopted, red for no/rejected, amber for abstention/warnings and grey for absence. Preserve its paired light/dark values.

## Typography

**Display Font:** Source Serif 4, Georgia, serif; bold headings (700).
**Body Font:** Source Sans 3, system-ui, sans-serif. Both variable fonts are hosted in `static/fonts/` with OFL licenses. The logo is existing Monoton artwork.

### Hierarchy

The frontmatter records actual catalogue sizes, including compact and responsive exceptions; it is not a geometric scale. The home display becomes (2.4rem) at (640px); section headings use the title role, sitting titles become (1.5rem), and interest headings become (1.7rem). Home introduction prose becomes (1rem) and index rows (1.05rem). Reading text uses the body role, introduction prose is limited to (65ch), and the home heading to (25ch), then (20ch) on phones. Statistics use bold serif numerals (1.65rem/1.2); metadata and utility text use the observed compact sizes. Inherited evidence-specific sizes remain in `static/style.css` rather than being forced onto this catalogue scale.

## Layout

Content and masthead share a centred (1200px) maximum measure with (32px) horizontal padding, reduced to (20px) at (640px). Main content starts (40px) below the masthead, or (28px) on phones. Common section intervals are (40px), panel padding (24px), and neutral section padding (28px–32px).

At (900px), search/utilities and navigation form separate masthead rows. Below this, Menu reveals navigation; without JavaScript links remain available. Search takes a full row at (640px). The inherited sticky masthead begins at (1060px). Desktop scroll padding and contents positioning use the exact catalogue sticky offset (152px): the contents toggle sits there from (1060px), its open panel starts (44px) lower; at (1540px) the permanently visible contents starts at (152px).

The home index has three columns, then two at (640px). Sitting summaries use two columns, then one at (640px), followed by a full-width broadcast row. Topic entries use three columns, two below (900px), and one at (640px). Preserve source order when stacking. Tables scroll horizontally when necessary.

## Elevation & Depth

Reading surfaces are flat, separated by tone and thin rules. Floating menus retain the inherited diffuse shadow (0 6px 24px rgb(0 0 0 / .18)), with opacity (.55) in dark mode. Current navigation uses an inset underline; selected topics use an inset square marker.

**The Flat Reading Rule.** Reading panels use borders and tonal separation; floating menus may use the existing diffuse shadow.

## Shapes

Catalogue buttons, fields, cards, dropdowns and contents panels have square corners. Topic markers retain a small radius (3px). Inherited result badges, media and specialised utilities retain their own geometry; square controls are not a mandate to flatten semantic badges. Navigation arrows are inline SVG.

## Components

### Buttons

Primary actions have green fill and theme-aware button text; secondary actions have neutral fill, neutral borders and normal text. Both have (48px) minimum height, padding (12px 20px), weight (500) and line-height (1.25). Broadcast actions use a (44px) minimum. Hover deepens green or strengthens neutral fill and border; disabled opacity is (.65).

### Search

The always-visible field is (44px) high with neutral fill and a thin neutral border. Keyboard focus uses yellow fill, black text and a black (3px) outline. Placeholder text uses muted ink.

### Navigation and index rows

Desktop navigation uses a separate ruled row, normal text (1.05rem), and an accent inset underline (3px) for the current page. Home index rows have a (52px) minimum height. Hover deepens text and bottom border to accent-hover and underlines the link. The arrow moves (2px, -2px) over (.2s) only when reduced motion is not requested.

### Topic selection

Ruled topic rows have a (56px) minimum height and a square marker with a surface inset when `aria-pressed="true"`. Hover adds pale blue. Retain the programmatic state.

### Panels and tables

Cards have a surface fill, thin neutral border and (24px) padding, reduced to (20px) on phones. Nested cards remove the extra frame. Tables use ruled rows and cell padding (12px 10px); hover uses the accent tint. Numerical data retains tabular figures where defined.

### Sitting and broadcast summary

A stronger grey heading tops paired neutral grey summaries. The broadcast strip uses stronger grey, with the inherited warning surface for errors. Statistics use bold serif numerals. Status is sentence case, following the record title, and actions follow status.

Keyboard focus on links, buttons and fields uses yellow fill, black text and a black outline (3px), offset (2px). Preserve reduced-motion overrides.

## Do's and Don'ts

### Do:

- **Do** preserve the existing wordmark and party/result colour meanings.
- **Do** use serif headings, blue links and square controls.
- **Do** retain keyboard focus, explicit selected states and both reader themes.

### Don't:

- **Don't** describe the open font substitutes as Berlingske.
- **Don't** use party colours as general interface accents.
- **Don't** add decorative imagery to replace the catalogue’s information hierarchy.

Evidence: `static/catalog.css` overrides `static/style.css` and `static/header.css` in the order declared by `templates/base.html`; `templates/index.html` supplies the catalogue structure. Reference intent is recorded in `.impeccable/surfaces/templates-index-html.md`. No new raster assets or provenance claims are introduced by this system update.

### Grafiki do udostępnienia

Okno generatora korzysta z prostokątnych kontrolek, tekstowych zakładek i czarnego nagłówka z niebieską linią. Eksportowane PNG mają zawsze jasne tło, lokalne fonty Source Serif 4 / Source Sans 3, wiersze danych oddzielone liniami i niewielką stopkę ze źródłem. Porównania zachowują równe kolumny. Kolory wyników głosowań zachowują znaczenie semantyczne.

Tekst druków (`.print-text`): miara 72ch, Source Serif 4 19 px (18 px na telefonie), interlinia 1.75 i odstęp akapitu 1em. Szerokość ogranicza wyłącznie miara czytelnicza lub dostępne miejsce ekranu.

Informacje o projekcie na końcu strony głównej: szersza kolumna z celem projektu i autorem, węższa sekcja wsparcia na szarym tle. Na telefonie sekcje układają się kolejno. Szczegóły kosztów i planów pozostają na stronie zbiórki autora.

Sejmdle ładuje wspólny `catalog.css`: paletę, fonty, nagłówek i focus. Arkusz gry definiuje układ oraz semantyczne kolory podpowiedzi. Nazwa gry jest typograficzna, zakładki mają dolne podkreślenie, a kontrolki są prostokątne. Oba arkusze są wersjonowane podczas budowania strony.
