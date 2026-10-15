// How backend states read in the UI (designs/DESIGN.md §9 chips, §11 vocabulary).
//
// RAGcat publishes by Document: "Publish changes" embeds a Document's edited Passages, and only
// embedded Passages answer. So a Document is "Not published" until its first publish, and has
// "Unpublished changes" while Passages differ from what answers.
import type { Doc, Progress } from './api'
import type { ChipKind } from './components/ui'
import type { I18n } from './i18n'

export const pct = (p: Pick<Progress, 'done' | 'total'> | null | undefined) => (p && p.total ? Math.round((100 * p.done) / p.total) : 0)

/** Mirrors identity/domain.py PLANS; /v1/me doesn't expose the Assistant limit yet. */
export const ASSISTANT_LIMIT = 10
export const planName = (plan: string) => plan.charAt(0).toUpperCase() + plan.slice(1)

export const REVIEWABLE: Doc['status'][] = ['review', 'embedding', 'ready']

/** Model changes can leave a ready Document pending without a text edit. Mirrors the embed endpoint. */
export const needsPublish = (d: Doc) =>
  d.enabled && (d.status === 'review' || d.status === 'ready') && d.pending_changes > 0

export const isPublished = (d: Doc) => d.last_embedded_at !== null

export function docChip(d: Doc, { t }: I18n): { kind: ChipKind; text: string } | null {
  switch (d.status) {
    case 'awaiting_upload':
      return { kind: 'neutral', text: t('doc.uploading') }
    case 'parsing':
      return { kind: 'neutral', text: d.progress?.stage === 'reading_pages' ? t('doc.readingPct', { pct: pct(d.progress) }) : t('doc.reading') }
    case 'embedding':
      return { kind: 'neutral', text: t('doc.publishingPct', { pct: pct(d.progress) }) }
    case 'deleting':
      return { kind: 'neutral', text: t('doc.deleting') }
    case 'failed':
      return { kind: 'warn', text: t('doc.failed') }
    case 'cancelled':
      return { kind: 'neutral', text: t('doc.cancelled') }
  }
  if (!d.enabled) return { kind: 'neutral', text: t('doc.paused') }
  if (!isPublished(d)) return { kind: 'attn', text: t('doc.notPublished') }
  if (d.pending_changes > 0) return { kind: 'attn', text: t('doc.unpublished') }
  return { kind: 'done', text: t('doc.published') }
}

/** "Reading pages · 48 of 120" for the task rail and processing page. */
export function stageText(progress: Progress | null, { t }: I18n): string {
  if (!progress) return t('stage.waiting')
  const counts = { done: progress.done, total: progress.total }
  switch (progress.stage) {
    case 'checking_file':
      return t('stage.checking')
    case 'reading_pages':
      return progress.total ? t('stage.readingOf', counts) : t('stage.reading')
    case 'describing_figures':
      return progress.total ? t('stage.figuresOf', counts) : t('stage.figures')
    case 'organizing_passages':
      return t('stage.organizing')
    case 'embedding':
      return progress.total ? t('stage.publishingOf', counts) : t('stage.publishing')
  }
}

export function fileSize(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** "returns-policy.pdf" → "Returns policy": the starting name until the owner renames it. */
export function nameFromFile(filename: string): string {
  const base = filename.replace(/\.pdf$/i, '').replace(/[-_]+/g, ' ').replace(/\s+/g, ' ').trim()
  return (base.charAt(0).toUpperCase() + base.slice(1)).slice(0, 80) || filename
}

/** "p. 3 ¶2", "pp. 3–4 ¶2–1" */
export function passageLocation(source: { page_start: number; page_end: number; para_start: number | null; para_end: number | null }, { t }: I18n): string {
  const pages = source.page_start === source.page_end ? t('loc.page', { n: source.page_start }) : t('loc.pages', { a: source.page_start, b: source.page_end })
  if (!source.para_start) return pages
  const para = source.para_end && source.para_end !== source.para_start ? `${source.para_start}–${source.para_end}` : `${source.para_start}`
  return `${pages} ¶${para}`
}

/** Lint codes from the backend (curation/domain.py) → callout copy. */
export const WARNING_KEYS = {
  HEADING_ONLY: 'warn.headingOnly',
  TOO_SHORT: 'warn.tooShort',
  TOO_LONG: 'warn.tooLong',
  TABLE_FRAGMENT: 'warn.tableFragment',
} as const

/** Ingestion failure codes (ingestion/service.py) → title and fix. */
export const FAILURE_KEYS = {
  ENCRYPTED_PDF: ['fail.encrypted.title', 'fail.encrypted.body'],
  NOT_A_PDF: ['fail.notPdf.title', 'fail.notPdf.body'],
  PARSE_ERROR: ['fail.parse.title', 'fail.parse.body'],
  TOO_MANY_PAGES: ['fail.tooMany.title', 'fail.tooMany.body'],
  QUOTA_EXCEEDED: ['fail.quota.title', 'fail.quota.body'],
  NO_TEXT: ['fail.noText.title', 'fail.noText.body'],
} as const
