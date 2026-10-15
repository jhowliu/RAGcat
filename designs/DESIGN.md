# RAGcat Design Specification — H3 formal · v1.0 (2026-10)

RAGcat turns PDFs into a Discord customer-support Assistant. Every answer cites the Document and page it relied on.
This file is the written spec. Exact values live in `tokens/tokens.css`. Layout and behaviour references live in `prototypes/*.html`, and pictures of them are in `screens/`.

Token names below drop the `--rc-` prefix. For example, `ink` means `var(--rc-ink)`.

---

## 1. Principles

1. **Verifiability first.** Every answer can be traced to its source. The footnote marker `[1]` and the highlighted source sentence are the most important visual elements, and everything else gives way to them.
2. **Quiet and precise.** Use hairlines, few colours and generous whitespace. Colour expresses status and citation only, never decoration. Use no illustrations, mascots, gradients or coloured shadows.
3. **Progressive disclosure.** By default, show the current state, the next step and one primary action. Secondary actions appear after selection or expansion.
4. **Bilingual and accessible.** English is the default and Traditional Chinese is fully supported. Every page targets WCAG 2.2 AA.

---

## 2. Colour

Neutrals make up 90%+ of the interface. Contrast ratios are measured against `bg` (#FAF8F4).

### Neutrals

| Token | Hex | Use | Contrast |
|---|---|---|---|
| `bg` | #FAF8F4 | Page canvas | |
| `surface` | #FFFFFF | Panels, cards, inputs | |
| `surface-subtle` | #F4F0E9 | Source pane, secondary blocks, dropzone while dragging | |
| `surface-sunken` | #F1ECE4 | Landing product-scene background | |
| `surface-hover` | #F2EEE7 | Secondary button hover | |
| `ink` | #1F1D1C | Primary text, primary button, selected state, footnote marker | 15.8:1 |
| `ink-hover` | #3A3634 | Primary button hover | |
| `on-ink` | #FAF8F4 | Text and icons on ink | |
| `text-secondary` | #4B4643 | Secondary body text, landing lead | 8.8:1 |
| `text-muted` | #5C5754 | Inactive tabs and nav, app page leads | 6.7:1 |
| `text-control` | #3F3B39 | Segmented options, landing nav | 10.4:1 |
| `text-subtle` | #6B6561 | Hints, metadata, times | 5.4:1 |
| `text-disabled` | #8A837E | Disabled items, upcoming steps. Never use it for essential information. | 3.5:1 |
| `border` | #E4DED5 | Panel borders, section dividers | |
| `border-subtle` | #EDE8E0 | Row dividers inside panels, progress track | |
| `border-strong` | #D9D2C7 | Segmented and icon-button borders, stepper connectors, seams | |
| `border-input` | #CFC6BA | Input borders, dropzone dashed border | |

### Accents and status

Accents have exactly three jobs: citation, selection and status. Primary buttons are always `ink` and are never coloured.

| Token | Hex | Use |
|---|---|---|
| `accent-eyebrow` | #A4544A | Landing section eyebrow only (5.0:1) |
| `citation` | #F6D27A | Background behind the cited sentence. The text stays `ink`. |
| `selection` / `selection-fill` | #D98A7E / 12% | Outline and fill of the selected Passage's range on the PDF |
| `success` | #5E9A55 | Live, saved and connected dot |
| `success-bg` / `success-text` | #E6F0E3 / #2F5E2A | Completed stage circle and label |
| `warning` | #C9962E | Usage ≥ 80% bar, background-task dot |
| `warning-bg` / `warning-text` | #FBF0D2 / #6B4A12 | Warning chip |
| `callout-bg` / `callout-border` / `callout-icon` | #FBF7EC / #EADBB4 / #8A6216 | Passage quality callout |
| `info-bg` / `info-text` | #E7F1F6 / #2C556A | "Edited" chip |
| `neutral-bg` / `neutral-text` | #EFEAE2 / #4B4643 | Neutral chip, counts |
| `dot-idle` | #BDB5AA | "Not published" dot |
| `danger` | #B3261E | Errors and destructive actions only (6.2:1) |

Narrow-use tokens:

- `header-bg`: 96% `bg` with backdrop blur, for the sticky header.
- `bg-hover`: landing nav hover.
- `on-ink-muted` and `on-ink-hover`: text and button hover on ink blocks.
- `avatar-bg`: customer avatar.
- Illustration only: `pdf-line`, `pdf-rule`, `selection-tint` and `selection-card`. These are for mock PDF pages and landing scenes, never for real UI.

**Rules**

- ✓ Use yellow only for "the sentence that was cited".
- ✓ Express every state with text or an icon as well, never colour alone.
- ✓ Use at most one solid `ink` primary button per screen.
- ✕ Do not use accents for large backgrounds or decoration.
- ✕ Do not use gradients or coloured shadows.
- ✕ Use `danger` only for errors and deletion, never for emphasis.

---

## 3. Typography

| Family | Token | Weights | Use |
|---|---|---|---|
| Source Serif 4 (zh: Noto Serif TC) | `font-serif` | 600, tracking −0.015em | Headings, prices |
| IBM Plex Sans (zh: Noto Sans TC) | `font-sans` | 400 / 500 / 600 | UI and body |
| IBM Plex Mono | `font-mono` | 400 / 500 | Data such as file names, page numbers, times, counts and IDs |

Google Fonts URL used by the prototypes:
`https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=Noto+Serif+TC:wght@500;600&family=Noto+Sans+TC:wght@400;500;700&display=swap`

| Style | Spec | Use |
|---|---|---|
| Display | serif 600 · 64/1.05 (phone 42) | Landing H1 |
| Heading 2 | serif 600 · 42/1.15 (phone 32) | Landing section title |
| Page title | serif 600 · 30–36/1.1–1.15 | App page title (Assistants 36, Processing 30, others 34) |
| Title | serif 600 · 21–24 | Card, block and component titles |
| Lead | sans 400 · 18/1.7 · `text-secondary` | Landing paragraph under a title. App pages use 16/1.6 `text-muted` under the page title. |
| Body | sans 400 · 16/1.6 | Body text and input text. Inputs are always 16px so phones don't zoom. |
| UI | sans 500 · 15 | Buttons, nav, tabs. Panel headings use 600. |
| Label | sans 500 · 14 | Form labels, list primary text |
| Hint | sans 400 · 13 · `text-subtle` | Descriptions, metadata |
| Data | mono 400/500 · 12–14 | File names, `p. 3`, times, counts, Passage IDs |
| Eyebrow | sans 600 · 13 · uppercase · 0.06em · `accent-eyebrow` | Landing section labels only |

**Rules**

- ✓ English headings and buttons use sentence case.
- ✓ Mono is only for data-like content.
- ✓ Do not tighten Chinese tracking.

---

## 4. Spacing, layout, breakpoints

The base unit is 4px. The scale is `space-1…20`: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80.

| Value | Typical use |
|---|---|
| 4 | Icon–text gap |
| 8 | Inside controls, between chips |
| 12 | Elements within a row |
| 16 | Panel padding on phones, phone gutter |
| 20 | Panel padding, block gaps |
| 24 | Card grid gap, page section gap |
| 32 | Tablet gutter |
| 40 | Landing desktop gutter |
| 48 | Large block gap |
| 64–80 | Landing section padding |

Containers:

| Container | Max width |
|---|---|
| Landing | 1160px |
| App | 1200px |
| Review workspace | 1320px |

Gutters:

| Breakpoint | App | Landing |
|---|---|---|
| Phone | 16px | 20px |
| ≥ 768px | 32px | 40px |

The app header is 60px and sticky; the landing header is 64px. The minimum touch target is 44px.

| Breakpoint | Width | What changes |
|---|---|---|
| phone | < 640 | Single column everywhere. |
| below md | < 768 | App nav wraps to a second scrollable row. The stepper shows only the current step's label plus "Step n of 3". The document table becomes a two-line list. The header task pill is hidden. |
| sm | ≥ 640 | Landing steps and plans become 2 columns. |
| md | ≥ 768 | Nav returns to one row. Stepper shows all labels. The document table shows all columns (Name · Pages · Published · Status · On). |
| lg | ≥ 960 | Landing hero becomes 2 columns, steps 4 and plans 3. |
| xl | ≥ 1024 | App main content plus sidebar (1.6fr / 1fr). The review workspace shows Source and Passages side by side (0.95fr / 1.05fr, panes 700px tall, scrolling inside). |

---

## 5. Radius, borders, elevation

**Radius**

| Radius | Use |
|---|---|
| 3–4px (`radius-xs`, `radius-sm`) | Footnote marker, chips, counts |
| 5 / 7px | Segmented option and container |
| 6px | Callouts, toolbar buttons |
| 8px (`radius-md`) | Buttons, inputs, Passage cards, status bar |
| 12px (`radius-lg`) | Panels, cards, task rail, dropzone |
| 16px (`radius-xl`) | Landing scene |
| 50% | Avatars, dots, step circles |
| 2px (`radius-bar`) | Progress bar track and fill |
| 10px (`radius-bubble`) | Customer message in chat previews |
| 11px (`radius-switch`) | Switch track |

**Borders**

Layers are separated with 1px hairlines, not shadows.

| Name | Value | Use |
|---|---|---|
| Hairline | 1px solid `border` | Panels, cards |
| Divider | 1px solid `border-subtle` | Rows inside panels |
| Selected | 1.5px solid `ink` | Selected Passage card, dropzone while dragging |
| PDF selection | 1.5px solid `selection` + `selection-fill` | Passage range on the source page |
| Dashed | 1.5px dashed `border-input` | Dropzone (the "New Assistant" card uses 1px) |
| Seam | 1px dashed `border-strong` | Gap between Passages (citation dividers use 1px dashed `border`) |

**Elevation**

| Level | Value | Use |
|---|---|---|
| Flat | none | Default for every app panel and card |
| Raised | `shadow-raised`, `shadow-raised-lg` | Floating cards in the landing scene and the PDF page mock only. The landing review preview uses a softer variant (0 18px 40px at 7%). |
| Overlay | `shadow-overlay` | Task rail, popovers, menus |

---

## 6. Icons and brand

Icons are in `icons/*.svg`: doc, up, check, lock, link, clock, trash, book, quote, person, layers, bell, undo, plus, chev, left, alert, lens.

- Grid is 24px. Stroke is 1.75; icons at 18px or smaller use 1.9–2 (the stepper check uses 2.2). Round caps and joins. Outline only, using `stroke="currentColor"`.
- Sizes range from 14 to 24.
- Every icon-only button needs an `aria-label`. A tooltip is recommended.

The brand mark is a cat-ear head with round glasses. Files are `icons/mark-ink.svg` and `icons/mark-reverse.svg`.

- The minimum size is 18px.
- Only two colourways are allowed: ink on `bg`, or `on-ink` on ink (bot avatar, 6px radius tile).
- Never outline, recolour or pair it with illustrations.
- The wordmark "RAGcat" is IBM Plex Sans 600 next to the mark.

---

## 7. Motion

| Item | Value | Note |
|---|---|---|
| Hover / press | 140ms ease-out (`duration`, `ease`) | Background and border colour only |
| Switch | 140ms ease-out | Knob slide |
| Looping or decorative animation | none | No floating or bouncing |
| Reduced motion | `prefers-reduced-motion` | Remove all transitions (`duration` → 0), including the switch knob. The prototypes only cover `.btn` and `.acard`, so close that gap when building. |
| Progress | text + bar | Every loading state has words |

---

## 8. Components — actions and input

Reference CSS is in `styles/app.css` (class names in brackets).

### Button `.btn .btn-dark | .btn-line | .btn-text`

- **Primary** `[.btn-dark]`: `ink` fill, `on-ink` text, hover `ink-hover`. Use at most one per block or view. The landing page has three (header Start free, hero, Free plan), which is the accepted exception.
- **Secondary** `[.btn-line]`: `surface` fill, `ink` text, hover `surface-hover`. Both Primary and Secondary have a 1px `ink` border.
- **Text** `[.btn-text]`: underlined (offset 4px), no border, 44px tall.
- **Size:**
  - Height 44px; compact 38px, used inside panels such as "Add Document".
  - Landing buttons are 46px tall with 20px padding. The landing header "Start free" is 42px with 16px padding and 14px text.
  - Otherwise padding is 0 18px, radius 8px, Plex Sans 500 15px, icon gap 8px.
- **Disabled:** 40% opacity and `not-allowed`. If the reason isn't obvious, show it next to the button, e.g. "Pages already read are still counted."
- **Copy:** use a verb in sentence case, e.g. "Publish changes", "Upload a PDF", "Next: Review & test".
- ✕ No coloured buttons, no pill buttons, no two primaries competing in one block.

### Icon button `.ibtn`

40×40, or compact 34×34 in toolbars such as the Source pane page navigation (also shown on phones). 1px `border-strong` border, 8px radius, `surface` fill. Icon 16–18px with stroke 1.75. It requires an `aria-label`. A tooltip is recommended. Disabled uses 40% opacity.

### Text field & Select `.field .lbl .hint`

Each field has a label above (14/500), the input, and a hint below (13 `text-subtle`).

- **Input:** 44px tall, 12px horizontal padding, 1px `border-input` border, 8px radius, `surface` fill, 16px text.
- **Mono variant:** emails, file names and other data fields use `font-mono`.
- **Focus:** 2px `ink` outline, offset 2px.
- **Error (pattern, not yet in the prototypes):** `danger` border plus a specific message in `danger` 13px saying how to fix it, e.g. "Enter a full email address, like name@brand.com."
- **Compact select:** the review toolbar's Document select is 40px tall with mono 14px text.
- A placeholder never replaces the label.

### Segmented control `.seg`

The container is `surface` with a 1px `border-strong` border, 7px radius and 2px padding, with a 2px gap between options.

- **Options:** 34px tall, 12px padding, 5px radius, 13px/500, `text-control`.
- **Selected:** `ink` fill and `on-ink` text.
- **Semantics:** filters and toggles use `role="group"` with `aria-pressed`. A segmented control that switches views (the phone Source / Passages / Test switcher) uses `role="tablist"` with `role="tab"` and `aria-selected`.
- **Uses:** language (EN/中文), billing (Monthly/Annual), Passage filter (All / Warnings 2 / Edited 1), and the phone review view (Source / Passages / Test).
- Use 2–4 options. Never use it for main navigation.

### Tabs `.tabbtn .cnt .cnt-attn`

Use tabs for parallel views of one object, e.g. Assistant overview: Documents / Channels / Questions / Settings.

- **Size:** 46px tall, 22px gap, on a 1px `border` baseline.
- **Selected:** 2px `ink` underline, weight 600, `ink` text. Unselected uses `text-muted`.
- **Count:** mono 11/500 on `neutral-bg`. When action is needed it uses attention style (white with an inset 1px `ink` ring), e.g. "2 unanswered".
- Use 2–5 tabs. They scroll horizontally on phones. Use `role="tablist"`, `role="tab"` and `aria-selected`.

### Checkbox list

The container has a 1px `border` and 8px radius. Rows are 48px tall with 14px padding, separated by `border-subtle`.

- **Checkbox:** native, 18px, `accent-color: ink`.
- **Text:** primary text is mono 14 (`#help-desk`). A right-side hint says, e.g., "Will answer here".
- **Disabled:** row text uses `text-disabled` and the reason is shown, e.g. "Used by Wholesale help".

### Switch

Use a switch only for instant binary settings, e.g. whether a Document is used for answers.

- **Size:** track 38×22, radius 11. Knob 16px white, inset 3px.
- **Colour:** on uses an `ink` track, off uses `border-strong`. Disabled is 40% opacity.
- **Behaviour:** `role="switch"` with `aria-checked` and an `aria-label` naming the Document. The state is also written as text, e.g. a "Paused" chip.
- **Motion:** 140ms.

### Header & navigation `.app-nav .navlink`

- **Header:** sticky, 60px, `header-bg` with backdrop blur, 1px `border` bottom.
- **Left:** mark plus the wordmark.
- **Centre nav:** Assistants · Usage · Billing, 15px `text-muted`. The current page uses `ink` 600 with a 2px underline and `aria-current="page"`.
- **Right:**
  - Optional task pill: 1px `border-strong`, warning dot and "1 task running". Hidden below 768px.
  - Notifications `.ibtn`.
  - Avatar: 36px ink circle with the initial.
- **Phone:** nav moves to a second row that scrolls horizontally. Account and notifications stay visible.
- **Back link:** chevron plus the parent's name, e.g. "‹ Assistants", 14px `text-muted`. Never "Back".
- **Landing header:** nav links have a 12px padding and a `bg-hover` pill on hover, an EN/中文 segmented control, Sign in and "Start free". Sign in is hidden below 768px.

### Stepper (create flow)

The steps are Setup → Review & test → Publish & connect. Recommended: let the URL decide the step so a reload keeps it (the prototypes are static files).

| State | Circle (26px) | Label | Interaction |
|---|---|---|---|
| Done | `surface` fill, 1px `ink` border, check icon | `ink` (inherited) | Links back to that step |
| Current | `ink` fill, `on-ink` number | `ink` 600 plus a "· Step n of 3" hint | `aria-current="step"` |
| Upcoming | 1px `border-input` border, `text-disabled` number | `text-disabled` | Not clickable |

Connectors are 1px `border-strong`. On phones, only the current step shows its label, and the other circles remain.

---

## 9. Components — content and feedback

### Panel `.panel .phead`

- **Panel:** `surface` fill, 1px `border`, 12px radius, no shadow.
- **Heading row:** padding 14×18 with a 1px `border` bottom. The title is 15–16/600 (Connect's numbered panels use 16) and a right-side status is optional, e.g. a `success` dot with "Saved".
- **Body padding:** 16–24px; 32px for centred empty and error states.

### Assistant card `.acard`

The whole card is one link with a single click target. It is a panel with 20px padding, a minimum height of 210px, and contents spaced apart.

- **Top:**
  - Name: serif 21.
  - Optional chip, only when action is needed, e.g. "Needs review" or "Reading".
  - Hint line, e.g. "5 Documents · updated today, 11:04".
- **Bottom:** a `border-subtle` divider, then:
  - "Answers in" in 12px `text-disabled`.
  - "Discord · #help-desk, #returns".
  - A status dot plus text, e.g. "Live since Sep 28" or "Not published".
- **Hover:** the border turns `ink`. Keyboard focus shows the global 2px `ink` outline.
- **Grid:** `repeat(auto-fill, minmax(min(100%, 300px), 1fr))` with a 16px gap.
- **New Assistant card:** dashed border, plus icon, and "Start from a PDF".
- A healthy card has no chip.

### Chip & status dot `.chip-* .dot`

Chips are 12/500 with 1×8 padding and a 4px radius.

| Variant | Style | Examples |
|---|---|---|
| attention `.chip-attn` | `surface` fill, inset 1px `ink` ring, `ink` text | Needs review, Unpublished changes, Not published |
| neutral `.chip-neutral` | `neutral-bg` / `neutral-text` | Paused, Reading · 40%, Done, Table |
| warning `.chip-warn` | `warning-bg` / `warning-text` | Compact quality warnings, e.g. Heading only, Multiple topics (landing preview). Full Passage cards use the callout instead. |
| info `.chip-info` | `info-bg` / `info-text` | Edited |

The status dot is 7px:

- `success`: Live, Saved.
- `warning`: task running.
- `dot-idle`: Not published.

A dot always has text next to it. A live, healthy Document gets no chip. "Edited" is a state, not an achievement, so it uses no accent.

### Citation (most important component)

- **Footnote marker `.fn`:**
  - Size: 16px tall, minimum 16px wide, 0 3px padding, 3px radius.
  - Style: `ink` fill, `on-ink` text, mono 10/500, raised 2px.
- **Source highlight:** `<mark>` with a `citation` background, `ink` text, 1×3 padding and a 3px radius. Only the sentence actually used is highlighted.
- **Citation line:** under the answer, after a 1px dashed `border` divider. It shows the marker plus mono 12 "returns-policy.pdf, p. 3" on the left and "● Grounded in 1 source" on the right.
- **In Discord:** "Source: returns-policy.pdf, p. 3" in mono on a `surface-subtle` chip.
- Use at most 3 sources per answer. Never show PDF URLs in Discord.
- Clicking a citation in the app opens the cited Passage.

### Progress & stage list

- **Progress bar:** 4px tall, 2px radius, `border-subtle` track, `ink` fill. It uses `warning` when usage is ≥ 80%.
  - Always add numbers in mono, e.g. "48 / 120 · 40%" or "1,640 / 2,000".
  - A warning bar also gets a `warning-text` message, e.g. "82% used. Add answers".
- **Stage list:** rows with a 24px circle, label and status. Rows have 12px vertical padding and are separated by `border-subtle`.

  | State | Circle | Label | Status |
  |---|---|---|---|
  | Done | `success-bg` fill, `success-text` check | | "Done" in `success-text` |
  | Current | `ink` fill with number | 600 | "In progress" |
  | Waiting | 1px `border-input` border | `text-disabled` | "Waiting" |

### Callout & status bar

- **Quality callout:**
  - Style: `callout-bg`, 1px `callout-border`, 6px radius, padding 8×10.
  - Content: alert icon 15px in `callout-icon`, then 13px `warning-text`.
  - It never blocks publishing.
- **Status bar:** sits under the page title, `surface` fill, 1px `border`, 8px radius, padding 10×14. Items are on one wrapping row:
  - A `success` dot with "Live since Sep 28, 14:02".
  - "1 Document has unpublished changes".
  - An alert icon with "Answers at 82% of the monthly limit".
  - A "Version history" text link on the right.
- **Error:**
  - Style: a panel with a `danger` border.
  - Title: lock or alert icon plus a `danger` 500 title, e.g. "This PDF is password-protected".
  - Body: the fix, e.g. "Remove the password from price-list.pdf, then upload it again."

### Passage card (review workspace)

- **Card:** `surface` fill, 1px `border`, 8px radius, padding 12×14, 10px gap.
- **ID line:** mono 12 `text-muted`, e.g. "**P-14** · p. 3 ¶2", with chips on the right (Edited, Table).
- **Quality warning:** shown as a callout under the text, not as a chip, e.g. "Heading only. Merge it with the next Passage so the heading stays with its content." or "Covers several topics: requests, labels and refunds. Split where the topic changes." (The landing preview mock shortens these to small warning chips.)
- **Text:** 14/1.7 with `white-space: pre-line`. Tables render as a real `<table>`: 13px, 1px `border` cells, and a header row on `surface-subtle` at 600.
- **Selected:** 1.5px `ink` border.
- **Toolbar:** appears only when the card is selected. It has a `border-subtle` top divider and `.tool` buttons: 32px tall, 1px `border-input` border, 6px radius, 13px. The buttons are Edit text · Split at cursor · Merge with next · Restore original, plus "Show on page" on phones.
- **Split marker:** inline when selected and a split point exists. "Split here" is a button with a 1px dashed `ink` border, 4px radius and 11/500 text.
- **Seam between cards:**
  - Look: a 1px dashed `border-strong` line with a centred "Merge" button (24px tall, 1px `border-input` border, 4px radius, 11px).
  - Tables: there is no merge across a table; show "Tables stay separate" instead.
  - Filters: when a filter is on, show a plain gap instead of seams.
- **Source pane:** the PDF page sits on `surface-subtle`. The selected Passage range has a 1.5px `selection` outline with `selection-fill`, and an ink mono 10px ID tag at its top-left.
- **Actions:** merge and split record history, and Undo (the `.ibtn` in the toolbar) steps back. "Saved hh:mm" shows a `success` dot.

### Upload dropzone

The same component covers five states.

| State | Look |
|---|---|
| idle | 1.5px dashed `border-input`, `surface`, minimum 360px tall. Doc icon tile, then "Drag a PDF here" (serif), "or choose a file from your computer", a **Choose file** secondary button, and mono limits "PDF · max 50 MB · max 300 pages". |
| drag | 1.5px solid `ink` on `surface-subtle`, "Release to upload" plus the file name |
| uploading | File row with name, size, progress bar and Cancel |
| duplicate | Info chip "Already in this Assistant", then "returns-policy.pdf is identical to a Document you uploaded on Sep 28." with **Open existing Document** / **Process another copy** and the hint "Processing another copy uses 24 pages from your plan." |
| error (encrypted) | `danger` panel: "This PDF is password-protected", the fix, and **Choose another file** |

The limits line is shown in the idle state. Drag-and-drop always has a keyboard alternative (Choose file).

### Task rail (background work)

- **Position:** fixed bottom-right with a 16px inset, 320px wide with `max-width: calc(100vw - 32px)`. It uses `role="status"`.
- **Style:** `surface` fill, 1px `border`, 12px radius, `shadow-overlay`.
- **Head:** "Tasks · 1" in 13/600 with an elapsed mono time on the right.
- **Body:** mono file name, a progress bar, "Reading pages · 48 of 120", and a Cancel text link.
- It never covers the main navigation. Recommended: move finished tasks to notifications (not built in the prototypes).

### Chat preview (test panel and Discord preview)

- **Customer message:** right-aligned, max ~82% wide, `ink` fill, `on-ink` text, 10px radius, padding 10×14, 14px.
  - In the Discord preview, customer messages sit left with a 30px `avatar-bg` person avatar.
- **Bot reply in the Discord preview (P06):**
  - Avatar: a 30px `ink` tile with 6px radius and the reverse mark.
  - Name line: "RAGcat · bot" in 12px `text-subtle`.
  - Body: answer text 14px, then a mono "Source: returns-policy.pdf, p. 3" chip. No footnote markers in Discord.
- **Reply in the Test panel (P05):** a white panel (max ~94% wide) with no avatar, the answer with inline footnote markers (mono, 0 4px padding), and citation lines that open the cited Passage.
- **Test panel input:** a field with an **Ask** primary button. Recommended: unanswerable questions say so and point to the contact email (the prototypes show only an answered question).

### Data rows (document list) `.drow`

- **Desktop (≥ 768):** a grid with columns Name `1fr` · Pages 70 · Published 110 · Status 200 · On 56.
  - Header row: 11–12px `text-disabled`.
  - Rows: padding 12×18 with `border-subtle` dividers.
  - Name: mono 14, which turns `text-disabled` when the Document is paused.
- **Phone:** two lines.
  - First line: mono name plus a switch.
  - Second line: a hint with "12 pages · published Sep 28 · Unpublished changes".

---

## 10. Pages

Prototypes are in `prototypes/NN-*.html` and open directly in a browser. Routes below are proposed; the prototypes are static files. Pictures are in `screens/desktop` (1440) and `screens/mobile` (390).

### P01 Landing `/` · `01-landing.html`

**Purpose:** explain the product and lead to uploading the first PDF. The hero shows a real answer with its source to prove that every answer cites.

**Sections:**

1. Header with an EN/中文 toggle.
2. Hero. The left side has an eyebrow, the H1 "Every answer, with its source.", a lead, **Upload a PDF** and **See the product** buttons, and a fine-print line. The right side has a scene card on `surface-sunken`: a source page card with a highlighted sentence, overlapped by a Discord chat card with a cited answer.
3. How it works: 4 steps, each with a top border and a mono number.
4. Review workspace preview, with a checklist.
5. Trust: 2 columns.
6. Pricing: Monthly/Annual segmented control and 3 plan cards.
7. Closing CTA on ink, then the footer.

**Responsive:**

| Breakpoint | Change |
|---|---|
| ≥ 960 | Hero has 2 columns |
| ≥ 640 | Steps and plans have 2 columns |
| ≥ 960 | Steps have 4 columns and plans 3 |

**State:** `lang` (en|zh) and `billing` (monthly|annual).

### P02 Assistants `/assistants` · `02-assistants.html`

**Purpose:** the entry point to every Assistant.

**Layout:**

- Page title "Assistants" with "3 of 10 on the Growth plan" underneath.
- **+ New Assistant** primary button on the right.
- A card grid with the New Assistant dashed card last.
- A hint: "Tip: drop a PDF anywhere on this page…".
- A task pill appears in the header while work runs.

**Responsive:** cards auto-fill at a minimum of 300px.

### P03 Upload · Step 1 `/assistants/new` · `03-upload.html`

**Purpose:** step one of creation. Ask for the Document first and the name later.

**Layout:**

- Back link and stepper.
- Title "Upload a PDF" with the lead "Your Assistant will answer only from the Documents you add and publish."
- "Pages remaining · Free 50 / 50" on the right.
- Then the dropzone.

**Responsive:** a single column with a maximum width of 960px.

**Prop:** `dropState` = idle | drag | uploading | duplicate | encrypted, e.g. `?dropState=drag`.

### P04 Processing · Step 1 `/assistants/new/processing` · `04-processing.html`

**Purpose:** reading is in progress, and the user may leave. They can fill in details while waiting.

**Main panel:**

- File header: mono name, page count, size and elapsed time.
- "Reading your PDF" with the lead "You can leave this page. Processing continues, and you'll be notified when it's ready."
- Stage list: Checking the file → Reading pages → Organizing into Passages → Ready to review.
- Progress bar "Pages read 48 / 120 · 40%".
- **Next: Review & test** is disabled until ready. **Back to Assistants** and Cancel are also shown.

**Sidebar (≥ 1024):** an "Assistant details" panel with Name and Contact-for-unanswered-questions fields that autosave.

**Phone:** the sidebar stacks below.

### P05 Review & test · Step 2 `/assistants/:id/review` · `05-review.html`

**Purpose:** fix Passages against the source and test by asking questions. Clicking a citation jumps to its Passage.

**Toolbar:** a Document select (mono), "● Saved hh:mm", Undo, and **Next: Publish & connect**.

**Workspace (≥ 1024):**

- Left: the Source pane, with page navigation `‹ p. 3 / 24 ›` and the selected Passage highlighted.
- Right: Passages | Test tabs. The Passages tab has a filter segmented control (All / Warnings n / Edited n) with "One topic per Passage improves answers.", then the list of Passage cards.

**Phone:** a Source / Passages / Test segmented control shows one pane at a time.

**Behaviour:**

- Select a card.
- Merge it with the next card (not across tables).
- Split at the marked point.
- Undo, from the history stack.
- Filter.
- "Show on page" switches to Source on phones.

**State:** `passages`, `sel`, `view` (src|psg|test), `filter` (all|warn|edit), `history` and `savedAt`.

### P06 Publish & connect · Step 3 `/assistants/:id/publish` · `06-connect.html`

**Purpose:** one action publishes. Channel selection unlocks after publishing.

**Panel "1. Publish changes":**

- Before publishing: a primary **Publish changes** button.
- After: "Done" chip and "● Live · published today at 11:20 · 47 Passages" with a Version history link.

**Panel "2. Connect Discord":**

- Bot and server row with "Change server".
- A channel checkbox list. A channel can belong to only one Assistant, so a channel used elsewhere is disabled with its reason.
- A behaviour list.
- Footer: Skip for now and **Finish**.

**Sidebar (≥ 1024):** a Preview panel with the Discord chat preview for `# help-desk`.

**Prop:** `startPublished` (true|false).

### P07 Assistant overview `/assistants/:id` · `07-assistant.html`

**Purpose:** day-to-day management.

**Layout:**

- Back link.
- The name as page title, with **Test** (secondary) and **Publish changes `1`** (primary, with a count) on the right.
- Status bar.
- Tabs: Documents n / Channels n / Questions "n unanswered" / Settings.

**Documents tab:**

- "Turn a Document off to stop using it without deleting it." with **+ Add Document** (compact).
- Data rows with switches and the statuses Unpublished changes, Reading · 40%, Paused and Not published.

**Task rail:** shown while a Document is being read.

**State:** `tab`, `filter`, and `off` (switch map).

### Journey

P01 → P03 Upload → P04 Processing → P05 Review & test → P06 Publish & connect → P07 Assistant overview.

P02 is the hub. Creation is a one-time 3-step flow, and review is a repair tool, not a mandatory gate.

---

## 11. Content and vocabulary

English is the default, and every string is a translation key.

| English | 繁體中文 | Meaning |
|---|---|---|
| Assistant | 助理 | A support assistant the user creates |
| Document | 文件 | An uploaded PDF |
| Passage | 段落 | The unit of content the Assistant reads |
| Publish changes | 發布變更 | The only action that makes edits visible to customers |
| Live version | 上線版本 | The version currently answering |
| Source | 出處 / 原文 | The cited Document and page |
| Paused | 已暫停 | Was live and can be resumed |
| Not published | 尚未發布 | Never live |
| Needs review | 需要檢查 | Has warnings to handle |

**Voice:**

- Be direct and concrete, with one point per sentence.
- Buttons start with a verb.
- Errors give the reason and the next step.
- Back links name the parent.
- Numbers, file names, page numbers and times are mono.

**Never in the UI:**

- chunk, embedding, vector, top-k, indexing, temperature.
- Explanations of how the system works internally. Explain only what affects a decision.
- A casual tone around payment, deletion or privacy.
- Numbers the user can't act on, such as Passage counts or version IDs on overview pages.

---

## 12. Accessibility (WCAG 2.2 AA)

- [ ] Text contrast ≥ 4.5:1. `text-disabled` (3.5:1) is only for non-essential info.
- [ ] Every action works by keyboard. Focus is a 2px `ink` outline with an offset.
- [ ] Touch targets ≥ 44px for primary controls. Compact controls are the exceptions: icon button 40, avatar 36, compact button 38, segmented 34, toolbar 32.
- [ ] State is never shown by colour alone, so there is always text or an icon.
- [ ] Drag-and-drop always has a button alternative.
- [ ] Progress bars use `role="progressbar"`. "Saved hh:mm" and the processing lead use `aria-live="polite"`, and the task rail uses `role="status"`.
- [ ] Icon-only buttons have an `aria-label` (tooltip recommended).
- [ ] `prefers-reduced-motion` is respected.
- [ ] Semantics:
  - Tabs use `role="tab"` with `aria-selected`.
  - Segmented filters use `aria-pressed`; segmented view switchers use `role="tab"`.
  - Switches use `role="switch"` with `aria-checked`.
  - The stepper uses `aria-current="step"` and the nav uses `aria-current="page"`.

## 13. Review checklist — reject a UI change if…

- It introduces a new button, input, chip or card style instead of an existing component.
- It uses a colour, radius, shadow or spacing value that is not a token.
- It shows illustrations where people read, compare, pay or delete.
- It exposes engineering terms (chunk, embedding…) in the main interface.
- It relies on colour alone for state.
- It only works in one language or at one screen size.
- It only works on hover, with no keyboard or touch alternative.
