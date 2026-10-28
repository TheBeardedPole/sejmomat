---
version: 1
slug: "templates-index-html"
primary_target: "templates/index.html"
related_targets: ["templates/base.html","static/catalog.css","static/header.css"]
---

# Home and shared shell
Mode: Read. Citizens find and check parliamentary records on phones and desktops.
Scope: site typography, colours, links, buttons, fields and shared reading surfaces. Preserve content, existing functions, logo, party/result semantics, dark and English support, and the corrected sticky contents position.

## Direction contract
THESIS: A parliamentary reading service with a clear typographic identity, retaining Stortinget-inspired typography with the user-pinned GOV.UK colour palette. Replace the generic cool-grey UI treatment while keeping the useful catalogue structure.
OWN-WORLD: White reading ground, neutral grey section backgrounds, near-black text, blue links, crisp rectangular controls and sturdy serif headings. Source Serif 4 Bold and Source Sans 3 are locally hosted OFL substitutes for the reference's licensed Berlingske families. Daylight reading and night-time research retain the user's theme choice.
STORY: Identify the section, follow a recognisable blue link, inspect records in a calm column, optionally follow topics.
FIRST VIEWPORT: Near-black masthead, white existing logo and navigation, blue bottom rule; large serif home heading; six ruled text links, latest and upcoming records paired against a neutral grey field, a separate broadcast strip. Buttons are rectangular, primary green, secondary neutral with a thin border. Mobile follows the same DOM order with a compact menu. Signature interaction: blue underline on links deepens on hover; selected topics carry a visible square mark.
FORM: User-pinned Stortinget reference overrides seed 68cefd26's assignment. Code-led adaptation of the existing surface; no raster comps or imitation official insignia. Colour reference: https://design-system.service.gov.uk/styles/colour/. Typography source evidence: https://www.stortinget.no/no/ and its typography/design handbook plus app.min.css. User explicitly chose open substitutes over Berlingske licensing.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

Unresolved: author acceptance of a future PR. No fork or push in this stage.
