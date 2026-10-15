// P06 Publish · step 3 of the create flow. One action publishes; after that the owner can add the
// Assistant to their website (panel 2). Discord comes later.
import { Link, useParams } from 'react-router'
import { Cat } from '../components/Cat'
import { WebsitePanel } from '../components/WebsitePanel'
import { BackLink, Chip, ErrorPanel, Progress, StatusDot, Stepper, errorText } from '../components/ui'
import { useDocumentTitle } from '../hooks'
import { useI18n } from '../i18n'
import { usePublishChanges } from '../publish'

export function PublishPage() {
  const { aid = '' } = useParams()
  const { t, tn, num, time, date } = useI18n()
  const publish = usePublishChanges(aid)
  const { assistant, docs } = publish
  useDocumentTitle(t('publish.title'))
  if (!assistant) return null

  const done = publish.live && publish.pendingCount === 0 && !publish.publishing
  const when = publish.lastPublished
  const publishedAt = when ? (new Date(when).toDateString() === new Date().toDateString() ? t('publish.today', { time: time(when) }) : t('publish.on', { date: date(when) })) : ''
  const used = docs.filter((d) => d.enabled && ['review', 'embedding', 'ready'].includes(d.status))
  const warnings = used.reduce((n, d) => n + d.warning_count, 0)

  return (
    <div className="wrap">
      <div className="page narrow">
        <BackLink to="/assistants">{t('nav.assistants')}</BackLink>
        <Stepper aid={aid} current={3} />
        <div className="stack tight">
          <h1 className="display page-title">{t('publish.title')}</h1>
          <p className="page-lead">{assistant.name}</p>
        </div>

        <section className="panel" aria-labelledby="publish-title">
          <div className="phead">
            <h2 id="publish-title" className="phead-title lg">
              {t('publish.button')}
            </h2>
            {done && <Chip kind="neutral">{t('stage.done')}</Chip>}
          </div>
          <div className="pbody">
            {done ? (
              <div className="publish-done">
                <Cat pose="cheer" size={84} className="publish-cat" />
                <StatusDot kind="success">
                  <strong>{t('publish.liveAt', { when: publishedAt })}</strong>
                </StatusDot>
              </div>
            ) : publish.publishing ? (
              <div className="meter" role="status">
                <div className="meter-head">
                  <span>{t('publish.publishing')}</span>
                  <span className="mono">{publish.progress.total ? `${num(publish.progress.done)} / ${num(publish.progress.total)}` : ''}</span>
                </div>
                <Progress value={publish.progress.done} max={publish.progress.total || 1} label={t('publish.publishing')} />
              </div>
            ) : (
              <>
                <dl className="summary">
                  <dt>{tn('publish.documents', used.length)}</dt>
                  <dd className="mono">{used.map((d) => d.filename).join(', ') || '—'}</dd>
                  <dt>{t('publish.warnings')}</dt>
                  <dd className="mono">{num(warnings)}</dd>
                </dl>
                <div className="row">
                  <button type="button" className="btn btn-dark" disabled={!publish.canPublish} onClick={publish.publish}>
                    {t('publish.button')}
                  </button>
                  <Link className="btn btn-line" to={`/assistants/${aid}/review`}>
                    {t('publish.back')}
                  </Link>
                </div>
                <p className="hint">{publish.canPublish ? t('publish.hint') : t('publish.nothing')}</p>
              </>
            )}
            {publish.error != null && <ErrorPanel title={t('publish.failed')}>{errorText(publish.error)}</ErrorPanel>}
          </div>
        </section>

        <WebsitePanel assistant={assistant} title={t('publish.websiteTitle')} locked={!assistant.published} />

        <div className="row between">
          {done ? <span /> : (
            <Link className="btn-text" to={`/assistants/${aid}`}>
              {t('publish.later')}
            </Link>
          )}
          {done && (
            <Link className="btn btn-dark" to={`/assistants/${aid}`}>
              {t('publish.finish')}
            </Link>
          )}
        </div>
      </div>
    </div>
  )
}
