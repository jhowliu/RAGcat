---
version: 1
slug: "web-src-pages-landing-tsx"
primary_target: "web/src/pages/Landing.tsx"
related_targets: ["web/src/components/AppShell.tsx","web/src/pages/Assistants.tsx","web/src/pages/Setup.tsx","web/src/pages/Review.tsx","web/src/pages/Publish.tsx","web/src/pages/Assistant.tsx","web/src/pages/Usage.tsx"]
---

# Landing surface brief

- **Scope:** the landing page `/` (`web/src/pages/Landing.tsx`). It is the first surface of the 2026-10-14 redesign. The app pages inherit the same world afterwards.
- **Visitor mode:** Persuade.
- **Audience:** small-shop owners who run support in Discord (see PRODUCT.md). They need to understand within seconds that every answer cites its document and page, and then act.
- **Action:** Upload a PDF (primary). Secondary: See the product, Start free.
- **Proof and content:**
  - Use the real product mechanism, shown as working UI. The mock data is Mochi Pet Co.'s returns-policy p. 3.
  - Pricing is illustrative and is kept exactly as written; nothing is added to it.
  - No logos, testimonials or metrics.
- **Constraints:**
  - Keep the bilingual keys.
  - Keep the product vocabulary.
  - Hidden features stay hidden.
  - Meet WCAG 2.2 AA.
- **Memorable moment:** the cat in glasses leans in from the chat side of the product frame and points back at the highlighted source sentence.

## Direction contract

THESIS:
- The category standard for AI customer-support SaaS, executed straight at Notion, Mailchimp and Intercom craft.
- The working product UI is the proof: a real Discord answer next to its source page, with the cited sentence highlighted.
- A cat in reading glasses is the single brand device.
- It refuses the cream-paper, editorial-serif look, and the dark AI-gradient look.

OWN-WORLD:
- **Ground and neutrals:** white ground, warm near-black ink, warm-grey neutrals.
- **Brand yellow:** the one brand yellow does two jobs. It is the citation highlight behind cited text, and it fills whole sections: the closing band and the hero frame's backdrop.
- **Type:** Figtree 800 headings, Figtree UI, Geist Mono for data. Noto Sans TC for Chinese.
- **Components:**
  - 12px-radius cards with soft, layered neutral shadows.
  - Ink primary buttons with a 10px radius; never pills, never coloured.
- **Mascot:** a line-drawn cat with an ink outline, white fill, and the mark's glasses (raster art in web/public/cat/).

STORY: The visitor understands that RAGcat turns their PDFs into a Discord assistant that cites the document and page. They believe it because they can see the exact sentence highlighted on the page. They act by uploading a PDF.

FIRST VIEWPORT (1440×900):
- **Header:** a sticky white header with the mark and RAGcat on the left; How it works, Trust and Pricing; then EN/中文, Sign in, and an ink Start free button.
- **Centred column:**
  - No label above the H1; kicker labels are banned by the craft floor.
  - The H1 "Every answer, with its source." at 72px, Figtree 800, tight tracking, on two lines.
  - A 20px lead, at most 640px wide.
  - Upload a PDF (ink, 52px) and See the product (outline).
  - The fine-print line.
- **Product frame:** from about y=600, the top of a 1120px product frame sits on a yellow backdrop. It is a window with three dots, with the Source page on the left (sentence highlighted) and the #help-desk answer with its [1] marker on the right.
- **Mascot:** the cat leans in from the source column's right edge, with its paw tip at the end of the cited line.

FORM: The category standard, played straight as the standing exit chosen by the user after two re-rolls. Benchmarks: Notion, Mailchimp, Intercom Fin.

Signature interaction: hovering or focusing a [1] marker sweeps the yellow highlight across the cited sentence (a 400ms wipe from left to right). The same citation motion is used everywhere in the product. With reduced motion, the highlight is static.

seed: none (unavailable)

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
