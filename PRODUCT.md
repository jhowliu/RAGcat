# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary: small-business owners who run customer support in a Discord community.** The reference case is a pet-supply shop (the fictional "Mochi Pet Co."). They are not technical. They already have return policies, shipping rules, care guides and product manuals as PDFs. They want a support Assistant that answers customers from those documents, without configuring models, prompts or settings. Their job is to:

1. Upload a PDF.
2. Check what the Assistant will read, and fix anything the PDF reading got wrong.
3. Test a few questions.
4. Publish.

**Customers (no account):** they ask questions through Discord or an API key. They never see the web app. They only see answers and their citations.

**Setting:** RAGcat is built as a CAB432 (QUT) cloud computing assessment and is evaluated through a report and a demo video. Design decisions still target the real owner, and the product is presented as if it were real.

## Product Purpose

RAGcat turns PDFs into a customer-support Assistant. Every answer cites the Document and page it relied on.

Success means two things. The owner trusts what the Assistant says because they have seen what it reads. Customers and the owner's team can check any answer against its source.

## Positioning

The owner reviews Passages one by one, beside the original PDF page. The Assistant answers only from published content, and every answer names the Document and page.

The product's two core capabilities are:

- human-reviewed Passages;
- answers that point back to their exact source location.

A generic chat-over-documents product cannot truthfully claim the review-against-source step.

## Operating Context

- **Creation flow:** Upload a PDF → Processing → Review & test → Publish changes → Connect Discord (later).
  - Processing runs in the background, and the owner may leave the page.
  - In Review & test, the Source pane sits beside the Passages, and test questions open the cited Passage.
- **Hub and management:** the Assistants list is the hub, and the Assistant overview handles day-to-day management. Creation is a one-time 3-step flow. After it, review is a repair tool, not a mandatory gate.
- **Typical documents:** the samples cover an English returns policy with tables, and a Traditional Chinese care guide with two columns and tables.
- **Languages:** English is the default, and Traditional Chinese is fully supported.

## Capabilities and Constraints

**Built:**

- Create an Assistant, with a name and a contact for unanswered questions.
- Upload a PDF (up to 50 MB and 300 pages). The backend renders its pages and extracts Passages: tables stay whole, and two-column pages are read one column at a time.
- Work on Passages: edit, merge, split, add, remove and restore, with quality warnings.
- **Publish changes:** this embeds changed Documents, and the first publish also makes the Assistant live. There is no separate draft index. Customers never see unpublished edits.
- **Test:** the owner asks questions and gets answers that cite their sources. When the Documents don't cover a question, the Assistant declines and refers the customer to the owner's contact. Tests always use the latest edits. Before the Assistant goes live, Test publishes changed Documents first. Once it is live, Test previews unpublished edits for the owner only, and Publish then reuses the vectors the preview prepared.
- Turn a Document off (Paused) without deleting it.
- See usage (pages read, answers) in the account menu.
- Sign in or create an account on RAGcat's own page, switch EN/中文 in the header (saved per browser), and sign out from the account menu.

**Not built, hidden in the app UI:** Discord Channels, Questions, Billing, Version history, notifications, Undo, and duplicate-file detection.

**Planned:**

- Live verification of sign-in on AWS. RAGcat has its own sign-in page: email and password through the API to Cognito. Sign-up creates a confirmed account at once and sends no email. Token refresh and sign-out are implemented. There is no password reset yet, because it depends on email delivery.
- P1: API keys and rate limits.
- P2: the Discord bot.

**When a design element needs a backend that doesn't exist:** hide or adapt it in the UI. Don't add backend scope unless the owner of this project asks for it.

**UI vocabulary:** Assistant, Document, Passage, Publish changes, Live version, Source, Paused, Not published, Needs review.

- Never show chunk, embedding, vector, top-k, indexing or temperature.
- Don't explain how the system works internally unless it affects a decision.

**Technical:** a React + Vite + TypeScript SPA, served from the same origin as the API. Every string is a translation key, and `web/src/locales/en.ts` and `zh.ts` must stay in sync.

## Brand Commitments

- **Name:** RAGcat. **Line:** "Every answer, with its source."
- **Mark:** the mascot's head, a cat wearing reading glasses (the cat that reads your documents), redrawn as a vector for small sizes. Files: `web/public/mark.svg`, `designs/icons/mark-ink.svg` and `designs/icons/mark-reverse.svg`; all three hold the same drawing, because its white face reads on light and dark grounds.
- **Cat elements are part of the identity** (user decision, 2026-10-14). The cat in glasses is a brand mascot, in the way Octocat is GitHub's. It appears at key moments:
  - the landing hero;
  - empty states;
  - reading or processing;
  - publish success.

  Working surfaces such as the Review workspace stay clean. The one exception is the Assistant's avatar beside Test answers, which uses the mark (user decision, 2026-10-14).
- **Visual direction** (user decision, 2026-10-14, after two re-rolls): the category standard for AI customer-support SaaS, executed straight at full craft. The craft bar is Notion, Mailchimp and Intercom (Fin): warm and approachable, professional and trustworthy. No irony and no smuggled quirk; the mascot is the one brand device.
- **What `designs/` (H3) still governs:** flow, copy, product vocabulary, states and accessibility.
- **What it no longer governs:** the visual world (colour, type, components). Since the 2026-10-14 redesign, that is replaced by the root `DESIGN.md` written at the end of the redesign.
- **Voice:**
  - Be direct and concrete, with one point per sentence.
  - Buttons start with a verb.
  - Errors give the reason and the next step.
  - Never use a casual tone around payment, deletion or privacy.

## Evidence on Hand

- **Sample PDFs:** `samples/mochi-returns-policy.pdf` and `samples/mochi-care-guide-zh.pdf`, generated by `samples/make_samples.py`. Mochi Pet Co. is a fictional demo business.
- **Illustrative content:**
  - The landing hero scene (returns policy, p. 3).
  - The landing pricing (Free / Starter / Growth).
  - The landing's Discord description.

  Keep these as designed and don't extend them.
- **Concept and design references:** `RAGcat.pdf`, `RAGcat.html`, `designs/RAGcat-Pages.pdf` and `designs/Design-Guideline.pdf`.
- **Absent, do not fabricate:** testimonials, customer logos, press, benchmarks, real usage data, and new prices, plan limits or performance claims.

## Product Principles

1. **Verifiability first.** Every answer traces to a Document and page, and the citation is the most important thing on screen.
2. **The owner sees exactly what the Assistant reads.** Passages always sit beside their source page.
3. **Customers get only published content.** Publish changes is the single action that makes edits visible.
4. **No configuration burden.** There are no models, prompts or settings to tune. Expose only what affects a decision.
5. **Hide what isn't real.** Features without a backend are hidden, never faked.

## Accessibility & Inclusion

- Target WCAG 2.2 AA (see `designs/DESIGN.md` §12).
- Every surface is bilingual: EN by default, plus zh-Hant.
- Everything works by keyboard.
- State is never shown by colour alone.
- Drag-and-drop always has a button alternative.
- `prefers-reduced-motion` is respected.
