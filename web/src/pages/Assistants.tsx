// P02 Assistants: the hub. Each card is one link; a chip appears only when something needs action.
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import type { Assistant } from '../api'
import { Cat } from '../components/Cat'
import { Chip, ErrorPanel, Icon, StatusDot, errorText } from '../components/ui'
import { useAssistants, useDocumentTitle, useMe } from '../hooks'
import { useI18n, type I18n } from '../i18n'
import { planName, ASSISTANT_LIMIT } from '../model'

export function AssistantsPage() {
  const i18n = useI18n()
  const { t } = i18n
  const { data: assistants, error } = useAssistants()
  const { data: me } = useMe()
  const dragging = usePageDrop()
  useDocumentTitle(t('assistants.title'))

  return (
    <div className="wrap">
      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="display page-title lg">{t('assistants.title')}</h1>
            {me && assistants && (
              <p className="page-lead">{t('assistants.plan', { n: assistants.length, limit: ASSISTANT_LIMIT, plan: planName(me.plan) })}</p>
            )}
          </div>
          {assistants?.length !== 0 && (
            <Link className="btn btn-dark" to="/assistants/new">
              <Icon name="plus" size={16} stroke={2} />
              {t('assistants.new')}
            </Link>
          )}
        </div>
        {error && <ErrorPanel title={t('common.loadFailed')}>{errorText(error)}</ErrorPanel>}
        {assistants?.length === 0 ? (
          <section className="panel empty-state" aria-labelledby="empty-title">
            <Cat pose="sleep" size={190} />
            <h2 id="empty-title" className="display title">
              {t('assistants.emptyTitle')}
            </h2>
            <p>{t('assistants.emptyBody')}</p>
            <Link className="btn btn-dark" to="/assistants/new">
              <Icon name="up" size={16} stroke={2} />
              {t('land.hero.upload')}
            </Link>
          </section>
        ) : (
          <ul className="cards">
            {assistants?.map((a) => (
              <li key={a.id}>
                <AssistantCard a={a} i18n={i18n} />
              </li>
            ))}
            <li>
              <Link className="panel acard new" to="/assistants/new">
                <span className="tile">
                  <Icon name="plus" size={18} />
                </span>
                <span className="acard-new-title">{t('assistants.new')}</span>
                <span className="hint">{t('assistants.newHint')}</span>
              </Link>
            </li>
          </ul>
        )}
        <p className="hint">{t('assistants.dropTip')}</p>
      </div>
      {dragging && (
        <div className="drop-overlay" aria-hidden="true">
          {t('assistants.dropRelease')}
        </div>
      )}
    </div>
  )
}

function AssistantCard({ a, i18n }: { a: Assistant; i18n: I18n }) {
  const { t, tn, time, date } = i18n
  const reading = a.processing?.stage === 'reading_pages' ? a.processing : null
  const updated = new Date(a.updated_at).toDateString() === new Date().toDateString() ? t('card.updatedToday', { time: time(a.updated_at) }) : t('card.updated', { date: date(a.updated_at) })
  const meta = !a.document_count
    ? t('card.noDocs')
    : `${tn('card.docs', a.document_count)} · ${reading ? t('card.readingOf', { done: reading.done, total: reading.total }) : updated}`
  const chip = a.status === 'processing' ? <Chip kind="neutral">{t('card.reading')}</Chip> : a.published && a.pending_changes > 0 ? <Chip kind="attn">{t('doc.unpublished')}</Chip> : null

  return (
    <Link className="panel acard" to={a.document_count ? `/assistants/${a.id}` : `/assistants/${a.id}/setup`}>
      <div className="acard-top">
        <h2 className="display acard-name">{a.name}</h2>
        <span className="hint">{meta}</span>
      </div>
      <div className="acard-bottom">
        {a.published ? <StatusDot kind="success">{t('status.live')}</StatusDot> : <StatusDot kind="idle">{t('status.notPublished')}</StatusDot>}
        {chip}
      </div>
    </Link>
  )
}

/** Drop a PDF anywhere on the page to start a new Assistant with it. */
function usePageDrop(): boolean {
  const navigate = useNavigate()
  const [dragging, setDragging] = useState(false)
  useEffect(() => {
    const hasFile = (e: DragEvent) => !!e.dataTransfer && Array.from(e.dataTransfer.types).includes('Files')
    const over = (e: DragEvent) => {
      if (!hasFile(e)) return
      e.preventDefault()
      setDragging(true)
    }
    const leave = (e: DragEvent) => {
      if (!e.relatedTarget) setDragging(false)
    }
    const drop = (e: DragEvent) => {
      if (!hasFile(e)) return
      e.preventDefault()
      setDragging(false)
      const file = e.dataTransfer?.files[0]
      if (file) navigate('/assistants/new', { state: { file } })
    }
    window.addEventListener('dragover', over)
    window.addEventListener('dragleave', leave)
    window.addEventListener('drop', drop)
    return () => {
      window.removeEventListener('dragover', over)
      window.removeEventListener('dragleave', leave)
      window.removeEventListener('drop', drop)
    }
  }, [navigate])
  return dragging
}
