# Symbol Set Specification

Canonical symbols used in both **Studio display** and **PDF output**.
Any variant is normalised to the canonical form at render time
(Studio JS `renderKanaHtml` / `normalizeKanaForPdf`) and at
PDF generation time (Python `_render_kana_html`).

## Canonical symbols

| Annotation | Canonical | Input variants | Notes |
|---|---|---|---|
| Breath | ・ | ˘ ｜ / | Inserted between phrases |
| Emphasis up | ↑ | ⬆ ⇧ ⤴ | Pitch/volume direction |
| Emphasis down | ↓ | ⬇ ⇩ ⤵ | Pitch/volume direction |
| Liaison | ～ (U+FF5E) | ~ (ASCII) 〜 (U+301C) | Connects syllables |
| Elision | ( ) | （ ） (fullwidth) | Wraps dropped sounds |

## Where the rules live

| Layer | File | Function |
|---|---|---|
| Studio display | index.html | renderKanaHtml() |
| Studio payload | index.html | normalizeKanaForPdf() in buildSheetPayloadFromCurrentResult() |
| PDF render | app_web.py | _render_kana_html() |
| PDF legend | singkana_sheet.html | Static text in .legend div |

## Rules for changes

1. Always update both JS and Python when adding or removing a variant.
2. Keep singkana_sheet.html legend in sync with the canonical column above.
3. Run `singkana-smoke-sheet` after deploy to verify normalisation and legend.