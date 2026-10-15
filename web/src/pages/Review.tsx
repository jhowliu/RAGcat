// P05 Review & test: fix Passages against the source, and test by asking questions.
// Clicking a citation opens the Passage it came from.
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { api, ApiError, ask, type ChangeSet, type Citation, type Doc, type Passage, type PassageList } from '../api'
import { BackLink, Callout, Chip, ConfirmDialog, ErrorPanel, Icon, Mark, Saved, Segmented, Stepper, Tabs, errorText } from '../components/ui'
import { keys, useAssistant, useDocument, useDocumentTitle, useDocuments, usePage, usePassages } from '../hooks'
import { useI18n, type I18n } from '../i18n'
import { REVIEWABLE, WARNING_KEYS, needsPublish, passageLocation } from '../model'
import { usePublishChanges } from '../publish'

type View = 'src' | 'psg' | 'test'
type Filter = 'all' | 'warn' | 'edit'
type Run = (op: (version: number) => Promise<ChangeSet>) => Promise<boolean>

export function ReviewPage() {
  const { aid = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const i18n = useI18n()
  const { t } = i18n
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: assistant } = useAssistant(aid)
  const { data: docs = [] } = useDocuments(aid)
  const publish = usePublishChanges(aid)
  const reviewable = docs.filter((d) => REVIEWABLE.includes(d.status))
  const did = params.get('doc') ?? reviewable[0]?.id ?? null
  const view = (['src', 'psg', 'test'].includes(params.get('view') ?? '') ? params.get('view') : 'psg') as View
  const { data: doc } = useDocument(did)
  const { data: list } = usePassages(did)
  useDocumentTitle(t('review.title'))

  const [selected, setSelected] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [filter, setFilter] = useState<Filter>('all')
  const [savedAt, setSavedAt] = useState<Date | null>(null)
  const [opError, setOpError] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const setQuery = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    Object.entries(patch).forEach(([k, v]) => (v === null ? next.delete(k) : next.set(k, v)))
    setParams(next, { replace: true })
  }
  const setView = (v: View) => setQuery({ view: v === 'psg' ? null : v })

  // Publishing finished: refresh which Passages answer.
  const lastStatus = useRef(doc?.status)
  useEffect(() => {
    if (lastStatus.current === 'embedding' && doc?.status !== 'embedding' && did) queryClient.invalidateQueries({ queryKey: keys.passages(did) })
    lastStatus.current = doc?.status
  }, [doc?.status, did, queryClient])

  const select = (p: Passage | null) => {
    setSelected(p?.id ?? null)
    if (p) setPage(p.source.page_start)
  }

  const run: Run = async (op) => {
    if (!list || !did) return false
    setOpError(null)
    try {
      applyChangeSet(await op(list.edit_version))
      return true
    } catch (e) {
      if (e instanceof ApiError && e.status === 412) {
        setOpError(t('review.conflict'))
        queryClient.invalidateQueries({ queryKey: keys.passages(did) })
      } else {
        setOpError(errorText(e))
      }
      return false
    }
  }

  function applyChangeSet(cs: ChangeSet) {
    if (!did) return
    queryClient.setQueryData<PassageList>(keys.passages(did), (old) => {
      if (!old) return old
      const updates = new Map(cs.upserted.map((p) => [p.id, p]))
      return { ...old, items: old.items.filter((p) => !cs.deleted.includes(p.id)).map((p) => updates.get(p.id) ?? p), edit_version: cs.edit_version }
    })
    queryClient.setQueryData<Doc>(keys.document(did), (old) =>
      old && { ...old, edit_version: cs.edit_version, status: cs.document.status, pending_changes: cs.document.pending_changes, warning_count: cs.document.warning_count },
    )
    // Split creates Passages whose order and counts come from the server.
    queryClient.invalidateQueries({ queryKey: keys.passages(did) })
    queryClient.invalidateQueries({ queryKey: keys.documents(aid) })
    queryClient.invalidateQueries({ queryKey: keys.assistant(aid) })
    if (selected && cs.deleted.includes(selected)) setSelected(null)
    setSavedAt(new Date())
  }

  async function deleteDocument() {
    if (!did) return
    setConfirmDelete(false)
    try {
      await api.deleteDocument(did)
      queryClient.invalidateQueries({ queryKey: keys.documents(aid) })
      queryClient.invalidateQueries({ queryKey: keys.assistants })
      const next = reviewable.find((d) => d.id !== did)
      if (next) {
        setSelected(null)
        setQuery({ doc: next.id })
      } else navigate(`/assistants/${aid}`)
    } catch (e) {
      setOpError(errorText(e))
    }
  }

  const creating = assistant ? !assistant.published : true
  if (assistant && docs.length && !reviewable.length) {
    return (
      <div className="wrap review">
        <div className="page">
          <BackLink to={`/assistants/${aid}`}>{assistant.name}</BackLink>
          <p className="empty">{t('review.nothingYet')}</p>
        </div>
      </div>
    )
  }

  const count = list?.counts.all ?? 0
  return (
    <div className="wrap review">
      <div className="page tight">
        {creating ? (
          <>
            <BackLink to="/assistants">{t('nav.assistants')}</BackLink>
            <Stepper aid={aid} current={2} />
          </>
        ) : (
          <BackLink to={`/assistants/${aid}`}>{assistant?.name ?? ''}</BackLink>
        )}

        <div className="review-toolbar">
          <div className="row loose">
            <label htmlFor="doc-pick" className="sr-only">
              {t('review.document')}
            </label>
            <select
              id="doc-pick"
              className="input compact mono"
              value={did ?? ''}
              onChange={(e) => {
                setSelected(null)
                setPage(1)
                setSavedAt(null)
                setQuery({ doc: e.target.value })
              }}
            >
              {reviewable.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.filename}
                  {d.page_count ? ` · ${i18n.tn('review.pages', d.page_count)}` : ''}
                </option>
              ))}
            </select>
            <Saved at={savedAt ?? doc?.updated_at ?? null} />
          </div>
          <div className="row">
            <button type="button" className="ibtn" aria-label={t('review.deleteDoc')} title={t('review.deleteDoc')} onClick={() => setConfirmDelete(true)} disabled={!did}>
              <Icon name="trash" size={17} />
            </button>
            {creating ? (
              <Link className="btn btn-dark" to={`/assistants/${aid}/publish`}>
                {t('review.next')}
                <Icon name="chev" size={16} stroke={2} />
              </Link>
            ) : (
              <button type="button" className="btn btn-dark" disabled={!publish.canPublish} onClick={publish.publish}>
                {publish.publishing ? t('publish.publishing') : t('publish.button')}
                {!publish.publishing && publish.pendingCount > 0 && <span className="count">{publish.pendingCount}</span>}
              </button>
            )}
          </div>
        </div>

        {opError && <ErrorPanel title={t('review.opFailed')}>{opError}</ErrorPanel>}
        {publish.error != null && <ErrorPanel title={t('publish.failed')}>{errorText(publish.error)}</ErrorPanel>}
        {doc?.status === 'review' && doc.error?.code === 'EMBED_FAILED' && <ErrorPanel title={t('publish.stopped')}>{t('publish.stoppedBody')}</ErrorPanel>}

        <div className="view-switch">
          <Segmented
            tabs
            label={t('review.view')}
            value={view}
            onChange={setView}
            options={[
              { value: 'src', label: t('review.source') },
              { value: 'psg', label: `${t('review.passages')} ${count}` },
              { value: 'test', label: t('review.test') },
            ]}
          />
        </div>

        <div className="panel workspace">
          <SourcePane did={did} page={page} pageCount={doc?.page_count ?? 1} onPage={setPage} passage={list?.items.find((p) => p.id === selected) ?? null} on={view === 'src'} />
          <div className={`pane pane-right desk ${view !== 'src' ? 'on' : ''}`}>
            <Tabs
              label={t('review.panels')}
              value={view === 'test' ? 'test' : 'psg'}
              onChange={(v) => setView(v)}
              items={[
                { value: 'psg', label: t('review.passages'), count },
                { value: 'test', label: t('review.test') },
              ]}
            />
            {view === 'test' ? (
              <TestPane
                aid={aid}
                live={!creating}
                currentDoc={did}
                onCite={(c) => {
                  setQuery({ doc: c.document_id, view: null })
                  setFilter('all')
                  setSelected(c.chunk_id)
                  setPage(c.page)
                }}
              />
            ) : list && did ? (
              <PassagesPane did={did} list={list} filter={filter} setFilter={setFilter} selected={selected} onSelect={select} run={run} showOnPage={() => setView('src')} />
            ) : (
              <p className="empty">{t('common.loading')}</p>
            )}
          </div>
        </div>
      </div>
      {confirmDelete && doc && (
        <ConfirmDialog title={t('review.deleteTitle', { name: doc.filename })} confirmLabel={t('review.deleteDoc')} onConfirm={deleteDocument} onCancel={() => setConfirmDelete(false)}>
          <p>{t('review.deleteBody')}</p>
        </ConfirmDialog>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ Source

function SourcePane({ did, page, pageCount, onPage, passage, on }: { did: string | null; page: number; pageCount: number; onPage: (n: number) => void; passage: Passage | null; on: boolean }) {
  const i18n = useI18n()
  const { t } = i18n
  const { data: image } = usePage(did, page)
  const boxes = passage?.source.boxes.filter((b) => b.page === page) ?? []
  const label = passage ? t('review.pageLabelSel', { page, id: passage.label, loc: passageLocation(passage.source, i18n) }) : t('review.pageLabel', { page })
  return (
    <section className={`pane pane-src ${on ? 'on' : ''}`} aria-label={t('review.sourcePdf')}>
      <div className="phead">
        <span className="phead-title">{t('review.source')}</span>
        <span className="pager">
          <button type="button" className="ibtn compact" aria-label={t('review.prevPage')} onClick={() => onPage(page - 1)} disabled={page <= 1}>
            <Icon name="left" size={15} />
          </button>
          <span className="data">
            {t('loc.page', { n: page })} / {pageCount}
          </span>
          <button type="button" className="ibtn compact" aria-label={t('review.nextPage')} onClick={() => onPage(page + 1)} disabled={page >= pageCount}>
            <Icon name="chev" size={15} />
          </button>
        </span>
      </div>
      <div className="page-stage scroll">
        {image ? (
          <div className="sheet" role="img" aria-label={label} style={{ aspectRatio: `${image.width_pt} / ${image.height_pt}` }}>
            <img src={image.image_url} alt="" />
            {boxes.map((b, i) => (
              <div key={i} className="sel-box" style={{ left: `${b.x0 * 100}%`, top: `${b.y0 * 100}%`, width: `${(b.x1 - b.x0) * 100}%`, height: `${(b.y1 - b.y0) * 100}%` }}>
                {i === 0 && passage && <span className="sel-tag">{passage.label}</span>}
              </div>
            ))}
          </div>
        ) : (
          <p className="empty">{t('common.loading')}</p>
        )}
      </div>
    </section>
  )
}

// ------------------------------------------------------------------ Passages

const isTable = (p: Passage) => /^\|.*\|\s*$/m.test(p.text) && /^\|\s*:?-{3,}/m.test(p.text)
const isFigure = (p: Passage) => p.text.includes('[Figure]')

function PassagesPane({
  did,
  list,
  filter,
  setFilter,
  selected,
  onSelect,
  run,
  showOnPage,
}: {
  did: string
  list: PassageList
  filter: Filter
  setFilter: (f: Filter) => void
  selected: string | null
  onSelect: (p: Passage | null) => void
  run: Run
  showOnPage: () => void
}) {
  const { t } = useI18n()
  const items = useMemo(
    () => list.items.filter((p) => (filter === 'all' ? true : filter === 'warn' ? p.warnings.length > 0 : p.origin !== 'auto')),
    [list.items, filter],
  )
  return (
    <>
      <div className="filter-bar">
        <Segmented
          label={t('review.filter')}
          value={filter}
          onChange={setFilter}
          options={[
            { value: 'all', label: t('review.all') },
            { value: 'warn', label: `${t('review.warnings')} ${list.counts.warnings}` },
            { value: 'edit', label: `${t('review.edited')} ${list.counts.edited}` },
          ]}
        />
        <span className="hint">{t('review.oneTopic')}</span>
      </div>
      <ol className="passage-list scroll">
        {items.length === 0 && <li className="empty">{t('review.noMatch')}</li>}
        {items.map((p, i) => {
          const next = list.items[list.items.findIndex((x) => x.id === p.id) + 1]
          const canMerge = !!next && !isTable(p) && !isTable(next)
          const last = i === items.length - 1
          return (
            <li key={p.id}>
              <PassageCard did={did} p={p} next={canMerge ? next : null} selected={selected === p.id} onSelect={onSelect} run={run} showOnPage={showOnPage} />
              {!last &&
                (filter !== 'all' ? (
                  <div className="gap" />
                ) : (
                  <div className="seam">
                    {canMerge ? (
                      <button type="button" className="seam-btn" aria-label={t('review.mergeLabel', { a: p.label, b: next.label })} onClick={() => run((v) => api.mergePassages(did, v, [p.id, next.id]))}>
                        {t('review.merge')}
                      </button>
                    ) : (
                      <span className="hint">{t('review.tablesSeparate')}</span>
                    )}
                  </div>
                ))}
            </li>
          )
        })}
      </ol>
    </>
  )
}

// Sentence boundaries, mirroring backend shared/text.py: CJK sentences end at 。！？, Latin ones at
// .!? followed by a space and a new sentence. A Passage can be split where a sentence starts.
const CJK = '぀-ヿ㐀-䶿一-鿿豈-﫿가-힯'
const SENTENCE_END = new RegExp(`[。！？]+[」』”’）)]*|[.!?]+["'”’)]*(?=\\s+["'“‘(A-Z0-9${CJK}])|\\n+`, 'g')

function sentences(text: string): { start: number; text: string }[] {
  const out: { start: number; text: string }[] = []
  let start = 0
  for (const m of text.matchAll(SENTENCE_END)) {
    const end = m.index! + m[0].length
    out.push({ start, text: text.slice(start, end) })
    start = end
  }
  if (start < text.length) out.push({ start, text: text.slice(start) })
  return out.map((s) => ({ start: s.start + (s.text.length - s.text.trimStart().length), text: s.text }))
}

function PassageCard({
  did,
  p,
  next,
  selected,
  onSelect,
  run,
  showOnPage,
}: {
  did: string
  p: Passage
  next: Passage | null
  selected: boolean
  onSelect: (p: Passage | null) => void
  run: Run
  showOnPage: () => void
}) {
  const i18n = useI18n()
  const { t } = i18n
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(p.text)
  const [splitAt, setSplitAt] = useState<number | null>(null)
  const [confirmRemove, setConfirmRemove] = useState(false)
  const card = useRef<HTMLElement>(null)
  const segs = useMemo(() => sentences(p.text), [p.text])
  const table = isTable(p)
  const figure = isFigure(p)

  useEffect(() => {
    if (!editing) setDraft(p.text)
    setSplitAt(null)
  }, [p.text, editing])
  useEffect(() => {
    if (!selected) {
      setEditing(false)
      setSplitAt(null)
      return
    }
    // Scroll only the Passage list, never the window.
    const el = card.current
    const scroller = el?.closest('.passage-list') as HTMLElement | null
    if (!el || !scroller || scroller.scrollHeight <= scroller.clientHeight) return
    const top = el.offsetTop
    if (top < scroller.scrollTop || top + el.offsetHeight > scroller.scrollTop + scroller.clientHeight) scroller.scrollTo({ top: Math.max(0, top - 12), behavior: 'smooth' })
  }, [selected])

  const save = async () => {
    if (!draft.trim()) return setConfirmRemove(true)
    if (draft.trim() === p.text) return setEditing(false)
    if (await run((v) => api.editPassage(did, v, p.id, draft))) setEditing(false)
  }
  const split = () => splitAt !== null && run((v) => api.splitPassage(did, v, p.id, [p.text.slice(0, splitAt), p.text.slice(splitAt)]))
  const pick = (index: number) => {
    if (segs.length < 2) return
    const segment = segs[index > 0 ? index : 1]
    if (segment) setSplitAt(segment.start)
  }

  const restorable = p.origin === 'edited' || p.origin === 'merged' || p.origin === 'split'
  return (
    <article
      ref={card}
      className={`passage ${selected ? 'selected' : ''}`}
      onClick={() => !selected && onSelect(p)}
      onKeyDown={(e) => e.key === 'Escape' && selected && !editing && onSelect(null)}
    >
      <button type="button" className="passage-id" aria-pressed={selected} onClick={() => onSelect(selected ? null : p)}>
        <span className="loc">
          <b>{p.label}</b> · {passageLocation(p.source, i18n)}
        </span>
        <span className="chips">
          {table && <Chip kind="neutral">{t('review.table')}</Chip>}
          {figure && <Chip kind="neutral">{t('review.figure')}</Chip>}
          {p.origin !== 'auto' && <Chip kind="info">{t('review.editedChip')}</Chip>}
        </span>
      </button>

      {editing ? (
        <textarea
          className="input"
          autoFocus
          value={draft}
          rows={Math.max(3, Math.ceil(draft.length / 64) + (draft.match(/\n/g)?.length ?? 0))}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              e.stopPropagation()
              setEditing(false)
            }
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) save()
          }}
          aria-label={t('review.textOf', { id: p.label })}
        />
      ) : table ? (
        <PassageTable text={p.text} />
      ) : selected ? (
        <p className="passage-text">
          {segs.map((s, i) => (
            <span key={s.start}>
              {s.start === splitAt && (
                <button type="button" className="split-here" aria-label={t('review.splitHereLabel', { id: p.label })} onClick={split}>
                  {t('review.splitHere')}
                </button>
              )}
              <span className="sentence" onClick={() => pick(i)}>
                {display(s.text)}
              </span>
            </span>
          ))}
        </p>
      ) : (
        <p className="passage-text">{display(p.text)}</p>
      )}

      {figure && !editing && <span className="hint">{t('review.figureHint')}</span>}
      {p.warnings.map((w) => (
        <Callout key={w.code}>{w.code in WARNING_KEYS ? t(WARNING_KEYS[w.code as keyof typeof WARNING_KEYS]) : w.message}</Callout>
      ))}

      {selected && (
        <div className="passage-tools">
          {editing ? (
            <>
              <button type="button" className="tool" onClick={save}>
                {t('common.save')}
              </button>
              <button type="button" className="tool" onClick={() => setEditing(false)}>
                {t('common.cancel')}
              </button>
              <span className="hint">{t('review.editHint')}</span>
            </>
          ) : (
            <>
              <button type="button" className="tool" onClick={() => setEditing(true)}>
                {t('review.editText')}
              </button>
              {!table && (
                <button type="button" className="tool" disabled={splitAt === null} title={t('review.splitTip')} onClick={split}>
                  {t('review.splitAtCursor')}
                </button>
              )}
              <button type="button" className="tool" disabled={!next} onClick={() => next && run((v) => api.mergePassages(did, v, [p.id, next.id]))}>
                {t('review.mergeNext')}
              </button>
              {restorable && (
                <button type="button" className="tool" onClick={() => run((v) => api.restorePassage(did, v, p.id))}>
                  {t('review.restore')}
                </button>
              )}
              <button type="button" className="tool only-small-review" onClick={showOnPage}>
                {t('review.showOnPage')}
              </button>
              {!table && splitAt === null && segs.length > 1 && <span className="hint">{t('review.splitTip')}</span>}
            </>
          )}
        </div>
      )}

      {confirmRemove && (
        <ConfirmDialog
          title={t('review.removeTitle', { id: p.label })}
          confirmLabel={t('review.remove')}
          onCancel={() => {
            setConfirmRemove(false)
            setEditing(false)
          }}
          onConfirm={async () => {
            setConfirmRemove(false)
            await run((v) => api.deletePassage(did, v, p.id))
          }}
        >
          <p>{t('review.removeBody')}</p>
        </ConfirmDialog>
      )}
    </article>
  )
}

const display = (text: string) => text.replace(/\[Figure\] ?/g, '')

/** A Markdown table (from ingestion) as a real table; any caption lines stay as text. */
function PassageTable({ text }: { text: string }) {
  const lines = text.split('\n')
  const rows = lines.filter((l) => l.trim().startsWith('|') && !/^\|\s*:?-{3,}/.test(l.trim()))
  const caption = lines.filter((l) => l.trim() && !l.trim().startsWith('|')).join('\n')
  const cells = (line: string) =>
    line
      .trim()
      .replace(/^\||\|$/g, '')
      .split('|')
      .map((c) => c.trim())
  const [head, ...body] = rows.map(cells)
  return (
    <>
      {caption && <p className="passage-text">{caption}</p>}
      <table className="passage-table">
        {head && (
          <thead>
            <tr>
              {head.map((c, i) => (
                <th key={i}>{c}</th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {body.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j}>{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

// ------------------------------------------------------------------ Test

interface Turn {
  question: string
  answer: string
  citations: Citation[]
  done: { answered: boolean; fallback: { contact: string; message: string } | null } | null
  error: unknown
}

/**
 * Tests always use the latest edits. Before the Assistant is published nobody else can ask it,
 * so testing first publishes the Documents with changes, at any size. Once live, the backend
 * previews unpublished edits for the owner only; customers keep the published version.
 */
function TestPane({ aid, live, currentDoc, onCite }: { aid: string; live: boolean; currentDoc: string | null; onCite: (c: Citation) => void }) {
  const i18n = useI18n()
  const { t, tn } = i18n
  const queryClient = useQueryClient()
  const { data: docs = [] } = useDocuments(aid)
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const [preparing, setPreparing] = useState<{ done: number; total: number } | null>(null)
  const end = useRef<HTMLDivElement>(null)
  const pending = docs.filter(needsPublish)

  // Keep the newest answer in view, scrolling only the transcript (never the window).
  useEffect(() => {
    const box = end.current?.parentElement
    if (box) box.scrollTop = box.scrollHeight
  }, [turns, preparing])

  async function prepare() {
    const targets = docs.filter(needsPublish).map((d) => d.id)
    if (!targets.length) return
    await Promise.all(targets.map((did) => api.embed(did)))
    for (;;) {
      const current = await api.documents(aid)
      const running = current.filter((d) => targets.includes(d.id) && d.status === 'embedding')
      setPreparing(running.reduce((acc, d) => ({ done: acc.done + (d.progress?.done ?? 0), total: acc.total + (d.progress?.total ?? 0) }), { done: 0, total: 0 }))
      if (!running.length) break
      await new Promise((r) => setTimeout(r, 1500))
    }
    setPreparing(null)
    queryClient.invalidateQueries({ queryKey: keys.documents(aid) })
    targets.forEach((did) => queryClient.invalidateQueries({ queryKey: keys.passages(did) }))
  }

  const update = (patch: Partial<Turn>) => setTurns((ts) => ts.map((x, i) => (i === ts.length - 1 ? { ...x, ...patch } : x)))

  async function submit(e: FormEvent) {
    e.preventDefault()
    const q = question.trim()
    if (!q || busy) return
    setBusy(true)
    setQuestion('')
    setTurns((ts) => [...ts, { question: q, answer: '', citations: [], done: null, error: null }])
    try {
      if (!live) await prepare()
      await ask(
        aid,
        q,
        {
          onPreparing: (p) => setPreparing(p.done < p.total ? p : null),
          onToken: (text) => setTurns((ts) => ts.map((x, i) => (i === ts.length - 1 ? { ...x, answer: x.answer + text } : x))),
          onCitations: (citations) => update({ citations }),
          onDone: (done) => update({ done }),
        },
        { preview: true },
      )
    } catch (err) {
      setPreparing(null)
      update({ error: err })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="test" aria-label={t('review.test')}>
      <p className="hint test-note">
        {live ? t('test.noteLive') : t('test.noteDraft')}
        {live && pending.length > 0 && ` ${tn('test.pending', pending.length)}`}
      </p>
      <div className="transcript scroll">
        {turns.length === 0 && <p className="hint">{t('test.empty')}</p>}
        {turns.map((turn, i) => (
          <TurnView key={i} turn={turn} last={i === turns.length - 1} busy={busy} preparing={preparing} currentDoc={currentDoc} onCite={onCite} i18n={i18n} />
        ))}
        <div ref={end} />
      </div>
      <form className="ask-bar" onSubmit={submit}>
        <label htmlFor="ask" className="sr-only">
          {t('test.askLabel')}
        </label>
        <input id="ask" className="input" value={question} maxLength={1000} placeholder={t('test.placeholder')} onChange={(e) => setQuestion(e.target.value)} />
        <button type="submit" className="btn btn-dark" disabled={busy || !question.trim()}>
          {t('test.ask')}
        </button>
      </form>
    </section>
  )
}

function TurnView({
  turn,
  last,
  busy,
  preparing,
  currentDoc,
  onCite,
  i18n,
}: {
  turn: Turn
  last: boolean
  busy: boolean
  preparing: { done: number; total: number } | null
  currentDoc: string | null
  onCite: (c: Citation) => void
  i18n: I18n
}) {
  const { t } = i18n
  const streaming = last && busy
  const parts = turn.answer.split(/(\[\d+\])/)
  return (
    <>
      <div className="bubble">{turn.question}</div>
      <div className="bot-turn">
        <span className="bot-avatar" aria-hidden="true">
          <Mark size={22} />
        </span>
        {streaming && preparing ? (
          <p className="hint" role="status">
            {preparing.total ? t('test.preparingOf', { done: preparing.done, total: preparing.total }) : t('test.preparing')}
          </p>
        ) : turn.error ? (
          <ErrorPanel title={t('test.failed')}>
            {turn.error instanceof ApiError && turn.error.code === 'TOO_MANY_CHANGES'
              ? t('test.tooManyChanges', { n: Number(turn.error.details.passages), limit: Number(turn.error.details.limit) })
              : errorText(turn.error)}
          </ErrorPanel>
        ) : (
          <div className="panel answer">
            {turn.done && !turn.done.answered ? (
              <span className="answer-text">{turn.done.fallback?.message ?? t('test.noAnswer')}</span>
            ) : (
              <span className="answer-text">
                {parts.map((part, i) =>
                  /^\[\d+\]$/.test(part) ? (
                    <span key={i} className="fn">
                      {part.slice(1, -1)}
                    </span>
                  ) : (
                    <span key={i}>{part}</span>
                  ),
                )}
                {streaming && <span className="cursor" aria-hidden="true" />}
              </span>
            )}
            {turn.done?.answered && turn.citations.length > 0 && (
              <>
                <div className="cites">
                  {turn.citations.map((c) => (
                    <button key={c.chunk_id} type="button" className="cite-line" onClick={() => onCite(c)}>
                      [{c.n}] {c.document_id !== currentDoc ? `${c.document_title} · ` : ''}
                      {c.label} · {passageLocation({ page_start: c.page, page_end: c.page, para_start: c.para || null, para_end: null }, i18n)}
                      {c.edited ? ` · ${t('test.edited')}` : ''}
                    </button>
                  ))}
                </div>
                <span className="hint">{t('test.wrongAnswer')}</span>
              </>
            )}
          </div>
        )}
      </div>
    </>
  )
}
