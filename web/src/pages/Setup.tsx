// Step 1 of the create flow: Upload (P03) and Processing (P04). Also "Add Document" for an
// existing Assistant. The Document comes first; the Assistant is named after it until renamed.
import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router'
import { api, uploadFile, type Assistant, type Doc } from '../api'
import { Cat } from '../components/Cat'
import { BackLink, ErrorPanel, Field, Icon, Progress, Saved, Stepper, errorText } from '../components/ui'
import { clock, keys, useAssistant, useDocument, useDocumentTitle, useDocuments, useElapsed, useMe } from '../hooks'
import { useI18n } from '../i18n'
import { FAILURE_KEYS, fileSize, nameFromFile, pct, planName } from '../model'

const MAX_BYTES = 50 * 1024 * 1024

/** /assistants/new and /assistants/:aid/add */
export function UploadPage() {
  const { aid } = useParams()
  return <UploadView aid={aid ?? null} mode={aid ? 'add' : 'new'} />
}

/** /assistants/:aid/setup: the Document being read, or the upload when there is none yet. */
export function SetupPage() {
  const { aid = '' } = useParams()
  const [params] = useSearchParams()
  const { data: docs } = useDocuments(aid)
  if (!docs) return null
  const latest = [...docs].sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
  const did = params.get('doc') ?? latest?.id
  if (!did || params.has('upload')) return <UploadView aid={aid} mode="setup" />
  return <ProcessingView aid={aid} did={did} />
}

// ------------------------------------------------------------------ P03 Upload

type Drop = { state: 'idle' | 'drag' } | { state: 'uploading'; file: File; progress: number }

function UploadView({ aid, mode }: { aid: string | null; mode: 'new' | 'add' | 'setup' }) {
  const { t, num } = useI18n()
  const { data: me } = useMe()
  const { data: assistant } = useAssistant(aid ?? '')
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const abort = useRef<AbortController | null>(null)
  const pendingDoc = useRef<string | null>(null)
  const [drop, setDrop] = useState<Drop>({ state: 'idle' })
  const [error, setError] = useState<string | null>(null)
  useDocumentTitle(mode === 'add' ? t('upload.addTitle') : t('upload.title'))

  async function start(file: File | undefined) {
    if (!file || drop.state === 'uploading') return
    setError(null)
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) return setError(t('upload.notPdf', { name: file.name }))
    if (file.size > MAX_BYTES) return setError(t('upload.tooLarge', { name: file.name }))
    const controller = new AbortController()
    abort.current = controller
    setDrop({ state: 'uploading', file, progress: 0 })
    try {
      const target = aid ?? (await api.createAssistant(nameFromFile(file.name))).id
      const { document, upload } = await api.createDocument(target, file)
      pendingDoc.current = document.id
      await uploadFile(upload, file, (progress) => setDrop({ state: 'uploading', file, progress }), controller.signal)
      queryClient.invalidateQueries({ queryKey: keys.assistants })
      queryClient.invalidateQueries({ queryKey: keys.documents(target) })
      queryClient.invalidateQueries({ queryKey: keys.jobs })
      navigate(mode === 'add' ? `/assistants/${target}` : `/assistants/${target}/setup?doc=${document.id}`, { replace: true })
    } catch (e) {
      setDrop({ state: 'idle' })
      if (!(e instanceof DOMException && e.name === 'AbortError')) setError(errorText(e))
    }
  }

  async function cancel() {
    abort.current?.abort()
    if (pendingDoc.current) await api.cancel(pendingDoc.current).catch(() => undefined)
    pendingDoc.current = null
  }

  // A PDF dropped on the Assistants page arrives in the navigation state.
  const handed = useRef(false)
  useEffect(() => {
    const file = (location.state as { file?: File } | null)?.file
    if (file && !handed.current) {
      handed.current = true
      start(file)
    }
  }, [location.state])

  const left = me ? me.usage.pages_limit - me.usage.pages_read : null
  return (
    <div className="wrap">
      <div className="page narrow">
        {mode === 'add' ? <BackLink to={`/assistants/${aid}`}>{assistant?.name ?? t('nav.assistants')}</BackLink> : <BackLink to="/assistants">{t('nav.assistants')}</BackLink>}
        {mode !== 'add' && <Stepper aid={aid} current={1} />}
        <div className="page-head">
          <div>
            <h1 className="display page-title">{mode === 'add' ? t('upload.addTitle') : t('upload.title')}</h1>
            <p className="page-lead">{t('upload.lead')}</p>
          </div>
          {me && left !== null && (
            <div className="quota">
              <span className="hint">{t('upload.pagesRemaining', { plan: planName(me.plan) })}</span>
              <span className="data">
                {num(left)} / {num(me.usage.pages_limit)}
              </span>
            </div>
          )}
        </div>
        <div
          className={`dropzone ${drop.state === 'drag' ? 'drag' : ''}`}
          onDragOver={(e) => {
            e.preventDefault()
            e.stopPropagation()
            if (drop.state === 'idle') setDrop({ state: 'drag' })
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node)) drop.state === 'drag' && setDrop({ state: 'idle' })
          }}
          onDrop={(e) => {
            e.preventDefault()
            e.stopPropagation()
            if (drop.state === 'drag') setDrop({ state: 'idle' })
            start(e.dataTransfer.files[0])
          }}
        >
          {drop.state === 'uploading' ? (
            <div className="file-row" role="status">
              <div className="row between">
                <span className="data">{drop.file.name}</span>
                <span className="mono hint">{fileSize(drop.file.size)}</span>
              </div>
              <Progress value={Math.round(drop.progress * 100)} max={100} label={t('upload.progress', { name: drop.file.name })} />
              <div className="row between">
                <span className="hint">{t('upload.uploading', { pct: Math.round(drop.progress * 100) })}</span>
                <button type="button" className="btn-text small" onClick={cancel}>
                  {t('common.cancel')}
                </button>
              </div>
            </div>
          ) : (
            <>
              <span className="tile">
                <Icon name="doc" size={20} />
              </span>
              <p className="display drop-title">{drop.state === 'drag' ? t('upload.release') : t('upload.drag')}</p>
              {drop.state === 'idle' && (
                <>
                  <p className="page-lead">{t('upload.or')}</p>
                  <button type="button" className="btn btn-line" onClick={() => input.current?.click()}>
                    {t('upload.choose')}
                  </button>
                  <p className="mono hint">{t('upload.limits')}</p>
                </>
              )}
            </>
          )}
          <input ref={input} type="file" accept="application/pdf,.pdf" hidden onChange={(e) => start(e.target.files?.[0])} />
        </div>
        {error && <ErrorPanel title={t('upload.failed')}>{error}</ErrorPanel>}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ P04 Processing

const STAGES = ['stage.checking', 'stage.reading', 'stage.organizing', 'stage.ready'] as const

/** Index of the stage in progress; 4 when every stage is done. */
function stageIndex(doc: Doc): number {
  if (doc.status === 'awaiting_upload') return 0
  if (['parsing', 'failed', 'cancelled'].includes(doc.status)) {
    const stage = doc.progress?.stage
    return stage === 'organizing_passages' ? 2 : stage === 'reading_pages' || stage === 'describing_figures' ? 1 : 0
  }
  return 4
}

function ProcessingView({ aid, did }: { aid: string; did: string }) {
  const i18n = useI18n()
  const { t, num } = i18n
  const { data: doc, error } = useDocument(did)
  const { data: assistant } = useAssistant(aid)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const elapsed = useElapsed(doc?.status === 'parsing' ? doc.progress?.started_at : null)
  const cancel = useMutation({ mutationFn: () => api.cancel(did), onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.document(did) }) })
  useDocumentTitle(t('processing.title'))

  const finishedStatus = doc && !['awaiting_upload', 'parsing'].includes(doc.status)
  useEffect(() => {
    if (!finishedStatus) return
    queryClient.invalidateQueries({ queryKey: keys.assistant(aid) })
    queryClient.invalidateQueries({ queryKey: keys.documents(aid) })
    queryClient.invalidateQueries({ queryKey: keys.jobs })
  }, [finishedStatus, aid, queryClient])

  if (!doc) return <div className="wrap page">{error && <ErrorPanel title={t('common.loadFailed')}>{errorText(error)}</ErrorPanel>}</div>

  const step = stageIndex(doc)
  const finished = step === 4
  const stopped = doc.status === 'failed' || doc.status === 'cancelled'
  const describing = doc.progress?.stage === 'describing_figures'
  const counting = doc.progress && (doc.progress.stage === 'reading_pages' || describing) ? doc.progress : null
  const failure = doc.error ? FAILURE_KEYS[doc.error.code as keyof typeof FAILURE_KEYS] : undefined
  const again = `/assistants/${aid}/setup?upload=1`

  return (
    <div className="wrap">
      <div className="page">
        <BackLink to="/assistants">{t('nav.assistants')}</BackLink>
        <Stepper aid={aid} current={1} />
        <div className="two">
          <section className="panel" aria-labelledby="reading-title">
            <div className="file-head">
              <span className="row">
                <Icon name="doc" size={16} />
                <span>
                  {doc.filename}
                  {doc.page_count ? ` · ${t('processing.pages', { n: num(doc.page_count) })}` : ''} · {fileSize(doc.size_bytes)}
                </span>
              </span>
              {doc.status === 'parsing' && <span className="elapsed">{t('processing.elapsed', { time: clock(elapsed) })}</span>}
            </div>
            <div className="reading">
              <div className="reading-title">
                <div className="stack tight">
                  <h1 id="reading-title" className="display page-title sm">
                    {finished ? t('processing.readyTitle') : stopped ? t('processing.stoppedTitle') : t('processing.title')}
                  </h1>
                  <p className="page-lead" aria-live="polite">
                    {finished ? t('processing.readyLead') : stopped ? t('processing.stoppedLead') : t('processing.lead')}
                  </p>
                </div>
                {!stopped && <Cat pose={finished ? 'cheer' : 'read'} size={76} className="reading-cat" />}
              </div>

              {doc.status === 'failed' && (
                <ErrorPanel
                  title={failure ? t(failure[0]) : t('fail.generic.title')}
                  icon={doc.error?.code === 'ENCRYPTED_PDF' ? 'lock' : 'alert'}
                  action={
                    <Link className="btn btn-line" to={again}>
                      {t('fail.chooseAnother')}
                    </Link>
                  }
                >
                  {failure ? t(failure[1], { name: doc.filename }) : doc.error?.message}
                </ErrorPanel>
              )}

              <ol className="stages">
                {STAGES.map((label, i) => {
                  const state = finished || i < step ? 'done' : i === step ? (stopped ? 'stopped' : 'current') : 'waiting'
                  const status = { done: t('stage.done'), current: t('stage.inProgress'), stopped: doc.status === 'cancelled' ? t('stage.cancelled') : t('stage.stopped'), waiting: t('stage.waiting') }[state]
                  return (
                    <li key={label} className={state}>
                      <span className="stage-circle">{state === 'done' ? <Icon name="check" size={14} stroke={2.2} /> : i + 1}</span>
                      <span className="stage-label">
                        {t(label)}
                        {i === 1 && describing && state === 'current' && <span className="hint"> · {t('stage.figures')}</span>}
                      </span>
                      <span className="stage-status">{status}</span>
                    </li>
                  )
                })}
              </ol>

              <div className="meter">
                <Progress
                  value={counting ? counting.done : finished ? 1 : 0}
                  max={counting ? counting.total || 1 : 1}
                  label={describing ? t('processing.figuresDescribed') : t('processing.pagesRead')}
                />
                <div className="meter-head hint">
                  <span>{describing ? t('processing.figuresDescribed') : t('processing.pagesRead')}</span>
                  <span className="mono">
                    {counting
                      ? `${num(counting.done)} / ${num(counting.total)} · ${pct(counting)}%`
                      : finished && doc.page_count
                        ? `${num(doc.page_count)} / ${num(doc.page_count)} · 100%`
                        : '—'}
                  </span>
                </div>
              </div>

              <div className="reading-actions">
                <div className="row">
                  <button type="button" className="btn btn-dark" disabled={!finished} onClick={() => navigate(`/assistants/${aid}/review?doc=${did}`)}>
                    {t('processing.next')}
                  </button>
                  <Link className="btn btn-line" to="/assistants">
                    {t('processing.back')}
                  </Link>
                </div>
                {(doc.status === 'parsing' || doc.status === 'awaiting_upload') && (
                  <span className="row">
                    <span className="hint">{t('processing.cancelHint')}</span>
                    <button type="button" className="btn-text small" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
                      {t('common.cancel')}
                    </button>
                  </span>
                )}
                {doc.status === 'cancelled' && (
                  <Link className="btn btn-line" to={again}>
                    {t('fail.chooseAnother')}
                  </Link>
                )}
              </div>
            </div>
          </section>
          {assistant && <AssistantDetails assistant={assistant} />}
        </div>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ Assistant details (autosave)

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function AssistantDetails({ assistant }: { assistant: Assistant }) {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const [name, setName] = useState(assistant.name)
  const [contact, setContact] = useState(assistant.fallback_contact)
  const [savedAt, setSavedAt] = useState<Date | null>(null)
  const save = useMutation({
    mutationFn: (patch: { name?: string; fallback_contact?: string }) => api.updateAssistant(assistant.id, patch),
    onSuccess: (a) => {
      queryClient.setQueryData(keys.assistant(a.id), a)
      queryClient.invalidateQueries({ queryKey: keys.assistants })
      setSavedAt(new Date())
    },
  })
  const nameError = !name.trim() ? t('details.nameRequired') : null
  const contactError = contact.trim() && !EMAIL.test(contact.trim()) ? t('details.contactInvalid') : null

  return (
    <aside className="panel" aria-labelledby="details-title">
      <div className="phead">
        <h2 id="details-title" className="phead-title">
          {t('details.title')}
        </h2>
        <Saved at={savedAt} saving={save.isPending} />
      </div>
      <div className="pbody">
        <Field id="assistant-name" label={t('details.name')} hint={t('details.nameHint')} error={nameError}>
          <input
            id="assistant-name"
            className="input"
            value={name}
            maxLength={80}
            aria-invalid={!!nameError}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => !nameError && name.trim() !== assistant.name && save.mutate({ name: name.trim() })}
          />
        </Field>
        <Field id="assistant-contact" label={t('details.contact')} hint={t('details.contactHint')} error={contactError}>
          <input
            id="assistant-contact"
            className="input mono"
            type="email"
            value={contact}
            maxLength={200}
            placeholder="help@yourshop.example"
            aria-invalid={!!contactError}
            onChange={(e) => setContact(e.target.value)}
            onBlur={() => !contactError && contact.trim() !== assistant.fallback_contact && save.mutate({ fallback_contact: contact.trim() })}
          />
        </Field>
        {save.error && <p className="field-error">{errorText(save.error)}</p>}
      </div>
    </aside>
  )
}
