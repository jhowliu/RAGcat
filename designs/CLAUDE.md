# RAGcat UI: instructions for Claude Code

> **Superseded for visuals on 2026-10-14.**
> - The visual system now lives in the project root `DESIGN.md`, with values in `web/src/theme/tokens.css`. Those values replace `tokens/`, the colour, type and elevation rules below, and the screenshots.
> - This folder still governs product flow, page structure, copy, vocabulary, states and accessibility.

Read this before writing or changing any UI. This folder is the design source of truth for RAGcat (H3 formal style).

## Read in this order

1. `tokens/tokens.css`: every colour, font, size, radius, shadow and duration. Import it once globally.
   - Tailwind projects: also use `tokens/tailwind.preset.js`.
   - Other tooling: use `tokens/tokens.json`.
2. `DESIGN.md`: the rules and component specs (sections 8–9), plus page specs (section 10).
3. `prototypes/NN-*.html`: the built reference for layout, copy and behaviour. The markup is in `<template id="dc-template">`.
   - `{{name}}` is a value from `renderVals()` in the page script.
   - `<template data-if>` and `<template data-for>` are conditionals and loops.
   - `onclick="{{fn}}"` binds handlers.
   - Treat the `Component` class state as the page's view-model.
4. `styles/app.css` and `styles/landing.css`: the prototype CSS with tokens substituted. Port the rules; don't copy class names blindly.
5. `screens/desktop/*.png` (1440) and `screens/mobile/*.png` (390): what the result must look like.

## Hard rules

- Never hardcode a hex, px radius, shadow or font stack in a component. Use tokens. If a value is missing, add it to `tokens.css` (and `DESIGN.md`), then use it.
- Build each component once (`DESIGN.md` §8–9) and reuse it. Don't create one-off button, chip, card or input styles.
- Use at most one primary (`ink` filled) button per block or view. Never use coloured or pill buttons.
- Colour is only for citation (`citation` yellow), selection (`selection`) and status. Use no gradients, coloured shadows or decorative illustrations.
- App surfaces are flat: 1px `border`, no shadow. `shadow-overlay` is for the task rail, popovers and menus only.
- Every status has text or an icon, never colour alone.
- Typography:
  - Headings use `font-serif` 600.
  - UI uses `font-sans`.
  - Data uses `font-mono`: file names, `p. 3`, times, counts, Passage IDs.
  - English is sentence case.
- Use the product vocabulary exactly: Assistant, Document, Passage, Publish changes, Live version, Source, Paused, Not published, Needs review.
- Never show chunk, embedding, vector, top-k, indexing or temperature in the UI.
- Make everything bilingual (EN default, zh-Hant) with translation keys and no hardcoded strings. `DESIGN.md` §11 has the zh terms.
- Accessibility:
  - 44px touch targets for primary controls.
  - Visible focus: 2px `ink` outline with an offset.
  - `aria-label` on icon-only buttons.
  - `role="tab"` with `aria-selected` for tabs and view switchers.
  - `aria-pressed` for filter segments.
  - `role="switch"` with `aria-checked`.
  - `aria-current` for the nav and stepper.
  - Respect `prefers-reduced-motion`.
- Breakpoints: sm 640 · md 768 · lg 960 · xl 1024. These are RAGcat's, not Tailwind's defaults.

## Definition of done for a UI task

1. Matches the prototype's structure, copy and states for that page. Check `DESIGN.md` §10 for the state list.
2. No raw hex values in the changed files. Check with: `grep -nE "#[0-9a-fA-F]{6}" <changed files>`, which should only hit token definitions.
3. Screenshot the page at 1440×900 and 390×844 (Playwright). Compare with `screens/desktop/<page>.png` and `screens/mobile/<page>.png`, then fix differences in spacing, type and colour.
4. Keyboard pass: tab through every control. Focus is visible and the order is logical.

## Page map

| # | Page | Proposed route | Prototype |
|---|---|---|---|
| P01 | Landing | `/` | `prototypes/01-landing.html` |
| P02 | Assistants | `/assistants` | `prototypes/02-assistants.html` |
| P03 | Upload · Step 1 | `/assistants/new` | `prototypes/03-upload.html` (`?dropState=idle\|drag\|uploading\|duplicate\|encrypted`) |
| P04 | Processing · Step 1 | `/assistants/new/processing` | `prototypes/04-processing.html` |
| P05 | Review & test · Step 2 | `/assistants/:id/review` | `prototypes/05-review.html` |
| P06 | Publish & connect · Step 3 | `/assistants/:id/publish` | `prototypes/06-connect.html` (`?startPublished=false`) |
| P07 | Assistant overview | `/assistants/:id` | `prototypes/07-assistant.html` |

To open the prototypes, serve or open `prototypes/index.html` in a browser. No build step is needed; they load Google Fonts and `dc-runtime.js`.
