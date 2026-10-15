---
version: 1
slug: "web-src-widget-widgetapp-tsx"
primary_target: "web/src/widget/WidgetApp.tsx"
related_targets: ["web/widget.js","web/widget-demo.html","web/src/components/WebsitePanel.tsx","web/src/pages/Publish.tsx","web/src/pages/Assistant.tsx"]
---

# Website widget surface brief

- **Scope:** the embeddable Website widget (`web/src/widget/`, loader `web/widget.js`) and where the owner sets it up: Publish panel 2 and the Assistant page's Channels tab (`web/src/components/WebsitePanel.tsx`). Spec: `docs/api-design.md` §7.
- **Visitor mode:** Operate. The customer asks one question and checks the source; the owner adds a domain and copies one line.
- **Audience:** customers of a small shop (no account) on the shop's own site; the shop owner (non-technical) in the app.
- **Task and states:** single-turn questions. Widget states: closed, empty, reading, streaming answer with [n], answer with sources, no answer (fallback contact), rate limited (countdown), error (retry), unavailable (not published, widget off, quota). Owner states: before publish (locked), no domains (off), domains listed (on), invalid domain, copied.
- **Constraints:** inherits DESIGN.md unchanged; bilingual keys; product vocabulary; hidden in production until the §7 backend exists (dev-only prototype with a demo host page and scripted answers); WCAG 2.2 AA; works inside any host page without host CSS leaking in.
- **Memorable moment:** hovering a [1] marker sweeps the citation highlight across its source line, the same motion as the landing.

## Direction contract

THESIS: The widget is RAGcat's Test pane handed to the customer: ink question bubble, white answer card, Brand Yellow [1] markers, and sources named by Document and page in mono. It refuses the generic support launcher: blue circle, chat-bubble icon, gradient header.

OWN-WORLD: DESIGN.md as built. White panel on the #F7F7F5 canvas, ink actions and selected states, Brand Yellow only for [1] and the mark's ears, Citation Yellow for the source sweep, Figtree with Geist Mono for files and pages, 14px panel radius with the Overlay shadow, 10px controls, no pills.

STORY: A customer opens the widget, asks a complete question, reads an answer that names returns-policy.pdf and its page, and trusts it. The owner adds their domain and copies one line of code.

FIRST VIEWPORT: Desktop, widget open: a 380×640 panel at bottom right, 12px above a 56px ink rounded-square launcher holding the mark. A 64px header holds the mark avatar, the Assistant name, "Every answer shows its source" and close. The canvas body shows the reading cat at 88px with the empty-state title and hint. The composer (16px input with ink Ask) sits at the bottom with a quiet "Powered by RAGcat" line.

FORM: An extension of the established RAGcat world; no direction round and no roll. Signature interaction: hovering or focusing [n] sweeps Citation Yellow across that source line over 420ms; static under reduced motion.
seed: none (unavailable)

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
