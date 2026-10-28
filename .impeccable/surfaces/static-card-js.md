---
version: 1
slug: "static-card-js"
primary_target: "static/card.js"
related_targets: ["static/share.js","sejmomat/card.py","templates/_cards.html","static/style.css"]
---

# Share graphics
Mode: Operate for the chooser; Read for exported images.
Scope: templates/_cards.html sharing dialog, static/share.js, static/card.js and sejmomat/card.py image generators. Inherit the approved site typography and GOV.UK palette. Preserve all factual data, image variants, sources, download/share behavior and nonpartisan treatment.

## Direction contract
THESIS: Parliamentary evidence in a readable publication, replacing the generator's rounded metric-card wall.
OWN-WORLD: Source Serif 4 Bold titles and numerals; Source Sans 3 labels. White image ground, near-black wordmark masthead, thin blue rule, grey row separators and neutral black values. Semantic voting colours remain data-specific. Exported PNGs always use the light reading palette, independent of the page theme.
STORY: Choose subject and scope, inspect the graphic, download or share it. The chooser uses existing site controls, clear fields and a large unframed preview.
FIRST VIEWPORT: Square dialog with a dark title band, blue selection rule, fields at left and preview at right. Mobile stacks fields, preview and actions. Each PNG begins with the existing wordmark masthead, then a serif subject title and factual metadata; summary figures form ruled rows, comparisons align two equal value columns; small source/footer credit closes it.
FORM: Explicit user-pinned existing GOV.UK-inspired visual system, code-led. No replacement world or generated illustration; real Sejm data and existing logo only.
FINISH: Verify representative desktop/mobile chooser states and actual exported PNGs, check long names, missing photos, font loading, download availability, both generator runtimes and existing tests. Update the existing design documentation only for this surface's approved changes.
