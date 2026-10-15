---
name: RAGcat
description: PDFs become a support Assistant, on a website or in Discord, whose every answer cites its Document and page.
colors:
  ink: "#1B1A19"
  ink-hover: "#34322F"
  on-ink: "#FFFFFF"
  canvas: "#F7F7F5"
  surface: "#FFFFFF"
  surface-subtle: "#F2F2EF"
  surface-sunken: "#ECEBE7"
  text-secondary: "#45423F"
  text-control: "#3A3835"
  text-muted: "#5C5955"
  text-subtle: "#6C6863"
  text-disabled: "#9A958E"
  border: "#E7E5E1"
  border-subtle: "#EFEDEA"
  border-strong: "#D8D5CF"
  border-input: "#CDC9C2"
  brand-yellow: "#FFD43B"
  brand-soft: "#FFF3C2"
  brand-deep: "#8A6400"
  citation-yellow: "#FFE066"
  selection-blue: "#2F6FEB"
  success: "#1F9254"
  success-bg: "#E3F4E9"
  success-text: "#146C3C"
  warning: "#D98E04"
  warning-bg: "#FFF2D2"
  warning-text: "#774B00"
  callout-bg: "#FFF8E5"
  callout-border: "#F2DCA0"
  info-bg: "#E8F0FE"
  info-text: "#1D4FB8"
  neutral-bg: "#EFEEEB"
  dot-idle: "#BAB5AE"
  danger: "#C62828"
typography:
  display:
    fontFamily: "Figtree, Noto Sans TC, system-ui, sans-serif"
    fontSize: "72px"
    fontWeight: 800
    lineHeight: 1.02
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "Figtree, Noto Sans TC, system-ui, sans-serif"
    fontSize: "44px"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "-0.035em"
  page-title:
    fontFamily: "Figtree, Noto Sans TC, system-ui, sans-serif"
    fontSize: "32px"
    fontWeight: 800
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Figtree, Noto Sans TC, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 800
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  lead:
    fontFamily: "Figtree, Noto Sans TC, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.6
  body:
    fontFamily: "Figtree, Noto Sans TC, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
  ui:
    fontFamily: "Figtree, Noto Sans TC, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.2
  label:
    fontFamily: "Figtree, Noto Sans TC, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 500
  hint:
    fontFamily: "Figtree, Noto Sans TC, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
  chip:
    fontFamily: "Figtree, Noto Sans TC, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.6
  data:
    fontFamily: "Geist Mono, ui-monospace, SFMono-Regular, monospace"
    fontSize: "14px"
    fontWeight: 400
    letterSpacing: "-0.01em"
    fontFeature: "tnum"
  data-micro:
    fontFamily: "Geist Mono, ui-monospace, SFMono-Regular, monospace"
    fontSize: "11px"
    fontWeight: 500
    fontFeature: "tnum"
rounded:
  xs: "4px"
  sm: "6px"
  seg-option: "8px"
  md: "10px"
  seg: "11px"
  lg: "14px"
  bubble: "16px"
  xl: "20px"
  bar: "999px"
  full: "50%"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "8": "32px"
  "10": "40px"
  "12": "48px"
  "16": "64px"
  "20": "80px"
  "28": "112px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    typography: "{typography.ui}"
    rounded: "{rounded.md}"
    padding: "0 18px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.ink-hover}"
    textColor: "{colors.on-ink}"
  button-primary-large:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0 24px"
    height: "52px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.ui}"
    rounded: "{rounded.md}"
    padding: "0 18px"
    height: "44px"
  button-secondary-hover:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.ink}"
  icon-button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    size: "40px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "44px"
  chip-attention:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.chip}"
    rounded: "{rounded.sm}"
    padding: "1px 8px"
  chip-neutral:
    backgroundColor: "{colors.neutral-bg}"
    textColor: "{colors.text-secondary}"
    typography: "{typography.chip}"
    rounded: "{rounded.sm}"
    padding: "1px 8px"
  chip-done:
    backgroundColor: "{colors.success-bg}"
    textColor: "{colors.success-text}"
    typography: "{typography.chip}"
    rounded: "{rounded.sm}"
    padding: "1px 8px"
  chip-warning:
    backgroundColor: "{colors.warning-bg}"
    textColor: "{colors.warning-text}"
    typography: "{typography.chip}"
    rounded: "{rounded.sm}"
    padding: "1px 8px"
  chip-info:
    backgroundColor: "{colors.info-bg}"
    textColor: "{colors.info-text}"
    typography: "{typography.chip}"
    rounded: "{rounded.sm}"
    padding: "1px 8px"
  footnote-marker:
    backgroundColor: "{colors.brand-yellow}"
    textColor: "{colors.ink}"
    typography: "{typography.data-micro}"
    rounded: "{rounded.xs}"
    padding: "0 4px"
    height: "18px"
  citation-mark:
    backgroundColor: "{colors.citation-yellow}"
    textColor: "{colors.ink}"
    rounded: "{rounded.xs}"
    padding: "1px 3px"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "24px"
  callout:
    backgroundColor: "{colors.callout-bg}"
    textColor: "{colors.warning-text}"
    typography: "{typography.hint}"
    rounded: "{rounded.md}"
    padding: "9px 12px"
  avatar:
    backgroundColor: "{colors.brand-yellow}"
    textColor: "{colors.ink}"
    rounded: "{rounded.full}"
    size: "36px"
  assistant-avatar:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.full}"
    size: "32px"
  step-number:
    backgroundColor: "{colors.brand-yellow}"
    textColor: "{colors.ink}"
    typography: "{typography.ui}"
    rounded: "{rounded.full}"
    size: "40px"
  launcher:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    rounded: "{rounded.bubble}"
    size: "56px"
  launcher-hover:
    backgroundColor: "{colors.ink-hover}"
    textColor: "{colors.on-ink}"
  widget-panel:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    width: "380px"
    height: "640px"
  embed-snippet:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.ink}"
    typography: "{typography.data}"
    rounded: "{rounded.md}"
    padding: "10px 10px 10px 14px"
---

# Design System: RAGcat

## Overview

**Creative North Star: "The Cited Answer"**

RAGcat looks like the category standard for AI customer-support SaaS, played straight at Notion, Mailchimp and Intercom craft: a white ground, warm near-black ink, warm-grey neutrals, and Figtree set heavy for headings. The world earns its own identity through two things only. The first is one brand yellow, which fills whole brand fields and marks citations. The second is a line-drawn cat in reading glasses, which appears at a few key moments. Everything else stays quiet so that the product itself is the proof. A Discord answer sits beside its source page, and the cited sentence is highlighted on that page.

There are two densities. The landing is spacious and persuasive. It uses a white ground with alternating #F7F7F5 bands, 80px section rhythm, and a product frame on a yellow stage. The app is an Operate surface: a #F7F7F5 canvas carrying white panels and cards with soft, layered lift, data set in Geist Mono, and dense rows. The Review workspace is the working core and carries no decoration; the cat appears there only as the mark in the Assistant's avatar.

This world replaces the visual rules of the H3 spec in `designs/` (cream paper, editorial serif, flat with no shadows). Those visual rules are retired. `designs/` still governs product flow, copy, vocabulary (Assistant, Document, Passage, Publish changes), states and accessibility (WCAG 2.2 AA). The world refuses both the cream-paper editorial look and the dark AI-gradient look.

**Key Characteristics:**
- White ground and warm near-black ink; one brand yellow that does two jobs, as brand field and as citation.
- Figtree 800 headings with tight tracking; Figtree UI; Geist Mono for every piece of data.
- 14px-radius white panels with soft, layered, neutral shadows on a #F7F7F5 app canvas.
- Ink primary buttons with a 10px radius, never pill-shaped and never coloured.
- The cat in reading glasses as the single brand device, used decoratively at key moments only.
- The citation sweep as the signature motion.

## Colors

A warm-neutral system with one loud brand yellow, a paler citation yellow, and conventional semantic status colours kept strictly apart from both yellows.

### Primary
- **Ink** (#1B1A19): primary text, primary buttons, the selected state (tab underline, selected segment, current step circle, checked switch, the "Needs action" chip outline) and the focus ring. Ink is the action colour; there is no blue or brand-coloured CTA.
- **Ink Hover** (#34322F): primary button hover only.

### Secondary
- **Brand Yellow** (#FFD43B): brand fields only. These are the landing hero stage behind the product frame, the full-bleed closing band, the mascot's inner ears, the account avatar, the landing step numbers, and the footnote marker [1].
- **Citation Yellow** (#FFE066): the highlight behind a cited sentence. Text on it stays ink.
- **Brand Soft** (#FFF3C2): tinted brand wells and the 3px focus halo around a focused input and a hovered avatar.
- **Brand Deep** (#8A6400): text on Brand Soft when it must read as brand.

### Tertiary
- **Selection Blue** (#2F6FEB): the outline of the selected Passage on the PDF page, with a 10% fill. It never marks an action.
- **Status set**: Success (#1F9254) with its background (#E3F4E9) and text (#146C3C) for live, saved and connected. Warning (#D98E04) with its background (#FFF2D2) and text (#774B00) for usage over 80% and background tasks. Quality callouts use Callout Background (#FFF8E5) with Callout Border (#F2DCA0). Info Background (#E8F0FE) with Info Text (#1D4FB8) is used for the "Edited" chip. Danger (#C62828) is used for errors and destructive actions only.

### Neutral
- **Canvas** (#F7F7F5): the app canvas and the landing's alternating bands. Using this as the app canvas is a deliberate Operate-surface adaptation. White panels and cards need lift on it.
- **Surface** (#FFFFFF): panels, cards, inputs, the sticky header, and the landing ground.
- **Surface Subtle** (#F2F2EF): the source pane, the segmented track, and secondary-button and row hover.
- **Surface Sunken** (#ECEBE7): inset wells.
- **Text Secondary** (#45423F, 10.2:1): leads and secondary body text. **Text Control** (#3A3835): segmented options and landing nav. **Text Muted** (#5C5955, 7.0:1): inactive tabs, field descriptions. **Text Subtle** (#6C6863, 5.5:1): hints, metadata, timestamps. **Text Disabled** (#9A958E, 2.9:1): disabled and upcoming steps only, never essential information.
- **Border** (#E7E5E1): panel borders and section dividers. **Border Subtle** (#EFEDEA): row dividers inside panels and progress tracks. **Border Strong** (#D8D5CF): secondary and icon-button borders, connectors. **Border Input** (#CDC9C2): input borders and the dashed dropzone.
- **Neutral Background** (#EFEEEB): neutral chips and counts. **Dot Idle** (#BAB5AE): the "Not published" dot.

### Named Rules
**The Two Yellows Rule.** Brand Yellow fills brand fields and marks [1]; Citation Yellow sits behind cited text. Yellow means brand or "cited" and nothing else, so status chips never use yellow; "Needs action" is a white chip with a 1px ink outline.

**The Canvas Lift Rule.** The app canvas is #F7F7F5 by design (an Operate-surface adaptation), so every white panel and card on it carries a hairline border and the card shadow. The landing ground is white, with #F7F7F5 only as alternating section bands.

**The Ink Acts Rule.** Every primary action and every selected state is ink. No coloured buttons.

## Typography

**Display Font:** Figtree (with Noto Sans TC, system-ui)
**Body Font:** Figtree (with Noto Sans TC, system-ui)
**Label/Mono Font:** Geist Mono (with ui-monospace, SFMono-Regular)

**Character:** Figtree set at 800 with negative tracking gives friendly, confident SaaS headings. Geist Mono marks anything a machine produced or counts: file names, pages, paragraph references, times, counts and IDs. In Traditional Chinese, headings drop to 700 with zero tracking.

### Hierarchy
- **Display** (800, 72px, 1.02, -0.035em): the landing H1 only, from 960px up; 44px on phone.
- **Headline** (800, 44px, 1.1, -0.035em): landing section titles from 960px up; 32px below. Prices and the closing title share this tracking.
- **Page Title** (800, 32px, 1.15, -0.02em): app page titles.
- **Title** (800, 20px, 1.3): card and block titles, Assistant names, landing step titles.
- **Lead** (400, 18px, 1.6, Text Secondary): section leads. The landing hero lead is 20px at most 640px wide.
- **Body** (400, 16px, 1.6): running text. Inputs are always 16px.
- **UI** (600, 15px): buttons, nav, tabs and panel headings.
- **Label** (500, 14px): labels and list primary text. **Hint** (13px, Text Subtle): hints and metadata. **Chip** (600, 12px): chips.
- **Data** (Geist Mono 400, 14px, tabular figures, -0.01em): file names, page references, timestamps. **Data Micro** (Geist Mono 500, 11px): counts and the [1] marker.

### Named Rules
**The Mono Means Data Rule.** Anything the system measured, numbered or named from a file is set in Geist Mono with tabular figures. Prose and controls are never mono.

**The Bare Heading Rule.** Headings stand alone. No eyebrow, kicker or uppercase label sits above a heading.

## Layout

Content sits in centred containers: 1200px for the landing and the app, and 1320px for the Review workspace. Gutters are 16px on phone and 32px from tablet; the landing wraps at 20px side padding. The header is 64px tall and sticky. On the landing it is 90% white with a backdrop blur and a hairline bottom border. Every interactive target is at least 44px tall.

Spacing is on a 4px base (4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 112). Landing sections breathe at 80px vertical padding, with 48px between a section head and its content. App panels pad 20px on phone and 24px from 768px. Card grids auto-fill at a 300px minimum with 16px gaps.

Breakpoints, mobile-first:
- **sm (640px):** landing steps and plans go to two columns, and CTAs sit in a row.
- **md (768px):** the header shows the task count, stepper labels show in full, and the full document table appears.
- **lg (960px):** landing feature rows go to two columns, steps to four and plans to three; the Display and Headline sizes apply.
- **xl (1024px):** the app shows main content beside a sidebar, and the Review workspace shows source and Passages side by side.

## Elevation & Depth

The system is softly lifted, not flat. Shadows are neutral, tinted from the ink (rgba 27, 26, 25), and always layered as a tight contact shadow plus a wider ambient one. They separate white surfaces from the #F7F7F5 canvas, and they grow only with importance or interaction.

### Shadow Vocabulary
- **Card** (`box-shadow: 0 1px 2px rgba(27,26,25,0.05), 0 1px 3px rgba(27,26,25,0.04)`): panels, cards, status bar, secondary and icon buttons, the selected segment.
- **Hover** (`box-shadow: 0 2px 4px rgba(27,26,25,0.05), 0 10px 24px rgba(27,26,25,0.08)`): Assistant card hover, together with a 2px rise.
- **Raised** (`box-shadow: 0 1px 2px rgba(27,26,25,0.04), 0 8px 24px rgba(27,26,25,0.08)`): the PDF sheet, landing previews and the featured plan.
- **Raised Large** (`box-shadow: 0 2px 6px rgba(27,26,25,0.05), 0 28px 64px rgba(27,26,25,0.16)`): the landing product frame only.
- **Overlay** (`box-shadow: 0 4px 10px rgba(27,26,25,0.06), 0 18px 44px rgba(27,26,25,0.14)`): task rail, popover, menu, dialog, and the Website widget's launcher and panel (the panel with a 14px radius and a Border hairline). Anything RAGcat floats over a host page it doesn't control carries Overlay.

### Named Rules
**The Soft Lift Rule.** Depth comes from soft, layered, ink-tinted shadows. There is no glow, no coloured shadow and no hard offset shadow.

## Shapes

Corners are gently rounded and scale with the size of the object. Markers and the citation highlight use 4px. Chips and counts use 6px. Segmented options and nav links use 8px. Buttons, inputs, Passage cards, callouts and the status bar use 10px; the segmented track uses 11px. Panels, cards, menus, the dropzone and the Website widget panel use 14px. Chat bubbles use 16px, and so does the Website widget's launcher: a 56px ink rounded square, because a floating control at that size reads as a key, not a button. The launcher is never a circle and never a pill. The landing product frame and the closing stage use 20px. Fully round shapes are reserved for avatars, status dots, step circles, progress bars and the switch track. Borders are 1px hairlines; the selected state is 1.5px ink, and the "add" card and dropzone use a 1.5px dashed Border Input stroke. The empty site list in Channel setup is the one sanctioned use of that dashed stroke outside an add target.

**The No Pill Rule.** Buttons are never pill-shaped. A 999px radius belongs only to progress bars and switches.

## Components

### Buttons
Confident and plain: a solid ink block or a white outlined key.
- **Shape:** gently rounded (10px), at least 44px tall; the large landing CTA is 52px and the compact size is 38px.
- **Primary:** ink background with white 15px/600 text and 18px horizontal padding. This button is used for Upload a PDF, Publish changes and Start free.
- **Hover / Focus:** hover moves to Ink Hover; press nudges down 1px. Focus is a 2px ink outline at a 2px offset (3px on the landing). Transitions take 160ms on the expo-out curve.
- **Secondary:** white with a Border Strong hairline and the card shadow; hover fills with Surface Subtle. A **text button** is ink with a Border Input underline that turns ink on hover. **Icon buttons** are 40px white squares with a 10px radius.
- **Disabled:** 40% opacity.

### Chips
- **Style:** 12px/600 text, 6px radius, 1px by 8px padding, with a tinted background and no border.
- **State:** done is green, warning is amber, edited is blue (info) and neutral is grey. **Needs action** is a white chip with a 1px inset ink outline, never yellow. Counts are 11px Geist Mono on Neutral Background.

### Cards / Containers
- **Corner Style:** 14px.
- **Background:** white on the #F7F7F5 canvas.
- **Shadow Strategy:** Card at rest; Assistant cards lift to Hover with a 2px rise (see Elevation & Depth).
- **Border:** a 1px Border hairline; a panel header is divided by the same hairline. The "new Assistant" card is a transparent 1.5px dashed tile with no shadow.
- **Internal Padding:** 20px on phone and 24px from 768px; panel headers use 14px by 20px.
- **Callouts:** Passage-quality warnings use Callout Background with a Callout Border hairline, a 10px radius and 13px Warning Text.

### Inputs / Fields
- **Style:** white, a 1px Border Input stroke, a 10px radius, 44px tall, 16px text; placeholders are Text Subtle.
- **Focus:** the border turns ink and a 3px Brand Soft halo appears.
- **Error / Disabled:** the border turns Danger, with a 13px Danger message below.

### Navigation
- **App header:** one row at every width. The mark and wordmark lead back to the Assistants list; with a single hub there is no nav row. On the right, the EN/中文 segmented control (as on the landing) sits beside the account avatar, a 36px Brand Yellow circle with an ink initial. The account menu holds the owner's name and email, this month's usage meters and Sign out; there is no separate Usage or Account page.
- **Tabs:** 15px/500 Text Muted; the selected tab is ink at 600 with a 2px ink underline.
- **Segmented control:** a Surface Subtle track with an inset hairline; the chosen option is a raised white key with the card shadow.
- **Stepper:** 28px circles. The current step is ink, done steps are green, and upcoming steps use Text Disabled.

### Citation (Signature Component)
The footnote marker [1] is an 18px Brand Yellow block with a 4px radius and an 11px Geist Mono ink numeral. The cited sentence carries a Citation Yellow highlight that clones across line breaks.

**The Highlighter Rule.** The citation sweep is the signature motion. When a [1] marker is hovered or focused, the highlight wipes left to right across the cited sentence over 420ms on the expo-out curve (cubic-bezier(0.16, 1, 0.3, 1)), like a highlighter pen. With reduced motion the duration is 0 and the highlight is static. This is the only expressive motion; every other transition is a 160ms state change. Today the sweep is wired on the landing product frame; the Review workspace's markers are static.

### Mascot
The cat in reading glasses is drawn with ink outlines, a white fill and Brand Yellow inner ears. It ships as raster art in five poses (sit, point, read, cheer, sleep), each with a provenance sidecar.

The mark is the same cat's head, redrawn as a 32-unit vector for small sizes: a white face with a 1.8 ink outline, Brand Yellow inner ears, thin round glasses with dot eyes, whiskers, a nose and a smile. It stays legible down to the 16px favicon, and its white face reads on light and dark grounds, so it has no reversed version.

**The Key Moments Rule.** The cat illustrations appear only at key moments: the landing hero (point, leaning in from the source column so its paw points back at the cited sentence), the landing close (cheer), the empty Assistants state (sleep), the Setup reading panel (read while reading, cheer when ready) and Publish success (cheer). The Review workspace never shows an illustration. There the cat appears only as the mark in the Assistant's avatar beside each Test answer: a 32px white circle with a Border hairline holding the 22px mark (user decision, 2026-10-14). The landing's Discord preview uses the same white avatar at 36px. In the Website widget, the read cat (84px) greets an empty conversation and the sleep cat (132px) marks an Assistant that is unavailable; once a question is asked, the cat appears only as the mark in the answer avatar, as in the Review workspace. On the host page, the launcher holds the 32px mark on ink, the one place the mark sits on a dark ground, and while the frame loads the panel holds the same mark, static, centred in a 48px white circle with a Border hairline. The cat is always decorative, with an empty alt and aria-hidden.

### Website widget
The Test pane handed to the customer on the owner's own site (dev-only until the backend in `docs/api-design.md` §7 exists).
- **Loader:** one script line draws the launcher in a shadow root and, on first open, an iframe of RAGcat's frame page, so no host CSS leaks in. Any value the loader needs is copied from `tokens.css`, never invented. The frame fades in over 160ms, a state change.
- **Launcher and panel:** the 56px ink launcher sits 20px from the bottom-right corner and swaps the mark for a down chevron when open. The 380×640 panel sits 12px above it with a 14px radius, a Border hairline and the Overlay shadow. Under 480px wide the panel fills the screen with no radius or border, and the open launcher hides.
- **Header:** 64px, white, with a hairline below. It holds the 36px white mark avatar, the Assistant name at 15px, the Hint "Every answer shows its source", and a borderless, shadowless compact close.
- **Transcript:** on the #F7F7F5 canvas with 16px padding. The ink question bubble, white answer card, Brand Yellow [n] markers, mark avatar and streaming cursor are the Test pane's own. Reading is a Hint line; the rate limit is a Hint with a clock icon, and the Ask button shows the countdown in mono; a failure is the error panel shrunk to the answer card's 14×16 padding, with a text-button Retry; no answer shows the owner's fallback message and contact.
- **Empty and unavailable:** centred, at most 290px wide: the cat (see the Key Moments Rule), a Title (20px/800) heading, 14px Text Secondary body, and in the empty state a Hint. Unavailable shows the contact, if any, as a mail icon beside a mono address.
- **Sources:** below a dashed divider, each [n] names its Document, page and paragraph in 12px Geist Mono, Text Secondary, with tabular figures ("returns-policy.pdf · p. 1 ¶2"). Hovering or focusing [n] sweeps Citation Yellow across that source line (the Highlighter Rule).
- **Composer:** white, with a hairline above; the 16px input and ink Ask. Once a conversation has started, the single-turn Hint ("Ask each question in full") stays in view above the input.
- **Foot:** "Powered by RAGcat" as a 13px Hint in Text Subtle beside the 14px mark, turning ink on hover.

### Channel setup
The owner's side of the Website widget: Publish panel 2 and the Assistant's Channels tab (at most 760px wide), both dev-only until the backend exists.
- **Panel:** a standard panel. Its header carries an On (done) or Off (neutral) chip; the lead is 14px Text Secondary.
- **Before the first publish:** a lock icon with 14px Text Muted copy replaces the controls, and the chip is hidden.
- **Allowed sites:** a 10px hairline list of 44px rows with the site in Data mono, Border Subtle dividers and a small text-button Remove. An empty list is a 10px box with the 1.5px dashed Border Input stroke and 14px Text Muted copy. Below it, a mono input and a secondary Add website button with a plus icon; an invalid site turns the input Danger, with a 13px Danger message.
- **Embed code:** the one line sits in a Surface Subtle well with a 10px radius and a hairline, set as Data (14px Geist Mono), beside a compact secondary Copy code button that swaps to a check and "Copied" for 2s.

## Do's and Don'ts

### Do:
- **Do** set every primary action in ink (#1B1A19) with a 10px radius and white text.
- **Do** keep the app canvas #F7F7F5 and give every white panel or card on it a hairline border and the card shadow.
- **Do** keep the landing ground white and use #F7F7F5 only for alternating section bands.
- **Do** reserve Brand Yellow (#FFD43B) for brand fields (hero stage, closing band), the mascot's ears, the avatar, step numbers and the [1] marker; reserve Citation Yellow (#FFE066) for the highlight behind cited text.
- **Do** set file names, pages, counts, times and IDs in Geist Mono with tabular figures.
- **Do** use the 420ms left-to-right citation sweep for citation reveals and switch it off under reduced motion.
- **Do** keep the product vocabulary, flow, states and WCAG 2.2 AA requirements from the H3 spec in `designs/`.

### Don't:
- **Don't** put an eyebrow or kicker label above a heading.
- **Don't** make buttons pill-shaped or coloured; primary buttons are ink.
- **Don't** use gradients or glow; the only gradient in the build is the flat single-colour layer that drives the citation sweep.
- **Don't** use yellow for status chips; "Needs action" is an ink-outline chip.
- **Don't** show the mascot illustrations in the Review workspace or anywhere outside their key moments; in the Review workspace the cat is only the mark in the Assistant's avatar. Never give the cat meaning that assistive technology must announce.
- **Don't** bring back the H3 spec's retired visual rules: cream paper, editorial serif, or flat surfaces with no shadows.
