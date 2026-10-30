// P07 Assistant overview: day-to-day management. Documents, Channels (the Website widget; Discord
// later) and Settings tabs.
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { api, type Assistant, type Doc, type Me } from '../api'
import { TaskRail } from '../components/AppShell'
import { UsageMeters, answersShare } from '../components/UsageMeters'
import { WebsitePanel } from '../components/WebsitePanel'
import { BackLink, Chip, ConfirmDialog, ErrorPanel, Icon, InlineEdit, StatusDot, Switch, Tabs, errorText } from '../components/ui'
import { keys, useDocumentTitle, useJobs, useMe } from '../hooks'
import { useI18n } from '../i18n'
import { REVIEWABLE, docChip, planName } from '../model'
import { usePublishChanges } from '../publish'

type Tab = 'documents' | 'channels' | 'settings'
const TAB_LABEL = { documents: 'overview.documents', channels: 'overview.channels', settings: 'overview.settings' } as const

export function AssistantPage() {
  const { aid = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const i18n = useI18n()
  const { t, tn, dateTime, num } = i18n
  const requested = params.get('tab')
  const tab: Tab = requested === 'settings' ? 'settings' : requested === 'channels' ? 'channels' : 'documents'
  const publish = usePublishChanges(aid)
  const { assistant, docs } = publish
  const { data: me } = useMe()
  const { data: jobs = [] } = useJobs()
  useDocumentTitle(assistant?.name)
  if (!assistant) return null

  const share = me ? answersShare(me) : 0
  return (
    <div className="wrap">
      <div className="page with-rail">
        <BackLink to="/assistants">{t('nav.assistants')}</BackLink>
        <div className="page-head">
          <h1 className="display page-title">{assistant.name}</h1>
          <div className="row">
            <Link className="btn btn-line" to={`/assistants/${aid}/review?view=test`}>
              {t('overview.test')}
            </Link>
            <button type="button" className="btn btn-dark" disabled={!publish.canPublish} onClick={publish.publish}>
              {publish.publishing ? t('publish.publishing') : t('publish.button')}
              {!publish.publishing && publish.pendingCount > 0 && <span className="count">{publish.pendingCount}</span>}
            </button>
          </div>
        </div>

        <div className="statusbar" role="status">
          {publish.live ? (
            <StatusDot kind="success">{publish.lastPublished ? t('overview.liveLast', { when: dateTime(publish.lastPublished) }) : t('status.live')}</StatusDot>
          ) : (
            <StatusDot kind="idle">{t('status.notPublished')}</StatusDot>
          )}
          {publish.publishing && publish.progress.total > 0 && (
            <span>{t('stage.publishingOf', { done: num(publish.progress.done), total: num(publish.progress.total) })}</span>
          )}
          {!publish.publishing && publish.pendingCount > 0 && <span>{tn('overview.pendingDocs', publish.pendingCount)}</span>}
          {share >= 0.8 && (
            <span className="with-dot warn">
              <Icon name="alert" size={14} />
              {t('overview.answersAt', { pct: Math.round(share * 100) })}
            </span>
          )}
        </div>
        {publish.error != null && <ErrorPanel title={t('publish.failed')}>{errorText(publish.error)}</ErrorPanel>}

        <div>
          <Tabs
            label={t('overview.sections')}
            value={tab}
            onChange={(v) => setParams(v === 'documents' ? {} : { tab: v }, { replace: true })}
            items={[
              { value: 'documents', label: t('overview.documents'), count: docs.length },
              { value: 'channels', label: t('overview.channels') },
              { value: 'settings', label: t('overview.settings') },
            ]}
          />
          <div role="tabpanel" aria-label={t(TAB_LABEL[tab])} className="tabpanel">
            {tab === 'documents' ? (
              <DocumentsTab aid={aid} docs={docs} />
            ) : tab === 'channels' ? (
              <div className="channels">
                <WebsitePanel assistant={assistant} title={t('website.title')} locked={!assistant.published} />
              </div>
            ) : (
              me && <SettingsTab assistant={assistant} me={me} />
            )}
          </div>
        </div>
      </div>
      <TaskRail jobs={jobs.filter((j) => j.assistant_id === aid)} />
    </div>
  )
}

// ------------------------------------------------------------------ Documents

function DocumentsTab({ aid, docs }: { aid: string; docs: Doc[] }) {
  const i18n = useI18n()
  const { t, tn, date } = i18n
  const queryClient = useQueryClient()
  const toggle = useMutation({
    mutationFn: ({ did, enabled }: { did: string; enabled: boolean }) => api.setEnabled(did, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.documents(aid) })
      queryClient.invalidateQueries({ queryKey: keys.assistant(aid) })
    },
  })
  const sorted = [...docs].sort((a, b) => a.created_at.localeCompare(b.created_at))

  return (
    <div className="stack mid">
      <div className="row between">
        <span className="hint">{t('overview.docsHint')}</span>
        <Link className="btn btn-line compact" to={`/assistants/${aid}/add`}>
          <Icon name="plus" size={16} stroke={2} />
          {t('overview.addDocument')}
        </Link>
      </div>
      {toggle.error != null && <ErrorPanel title={t('overview.toggleFailed')}>{errorText(toggle.error)}</ErrorPanel>}
      <div className="panel" role="table" aria-label={t('overview.documents')}>
        <div role="row" className="drow head">
          <span role="columnheader">{t('overview.colName')}</span>
          <span role="columnheader">{t('overview.colPages')}</span>
          <span role="columnheader">{t('overview.colPublished')}</span>
          <span role="columnheader">{t('overview.colStatus')}</span>
          <span role="columnheader">{t('overview.colOn')}</span>
        </div>
        {sorted.length === 0 && <p className="empty">{t('overview.noDocs')}</p>}
        {sorted.map((d) => {
          const chip = docChip(d, i18n)
          const reviewable = REVIEWABLE.includes(d.status)
          const published = d.last_embedded_at ? date(d.last_embedded_at) : '—'
          const phone = [d.page_count ? tn('review.pages', d.page_count) : null, d.last_embedded_at ? t('overview.publishedOn', { date: published }) : null, chip?.text]
            .filter(Boolean)
            .join(' · ')
          return (
            <div role="row" key={d.id} className={`drow ${d.enabled ? '' : 'paused'}`}>
              <span role="cell" className="name">
                {reviewable ? <Link to={`/assistants/${aid}/review?doc=${d.id}`}>{d.filename}</Link> : <Link to={`/assistants/${aid}/setup?doc=${d.id}`}>{d.filename}</Link>}
                <span className="hint phone-meta">{phone}</span>
              </span>
              <span role="cell" className="cell">
                {d.page_count ?? '—'}
              </span>
              <span role="cell" className="cell published">
                {published}
              </span>
              <span role="cell" className="cell status">
                {chip && <Chip kind={chip.kind}>{chip.text}</Chip>}
              </span>
              <span role="cell">
                <Switch
                  checked={d.enabled}
                  disabled={!reviewable || toggle.isPending}
                  label={t('overview.useDoc', { name: d.filename })}
                  onChange={(enabled) => toggle.mutate({ did: d.id, enabled })}
                />
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ Settings

function SettingsTab({ assistant, me }: { assistant: Assistant; me: Me }) {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [confirm, setConfirm] = useState<'offline' | 'delete' | null>(null)
  const update = useMutation({
    mutationFn: (patch: Partial<Pick<Assistant, 'name' | 'fallback_contact' | 'published'>>) => api.updateAssistant(assistant.id, patch),
    onSuccess: (a) => {
      queryClient.setQueryData(keys.assistant(a.id), a)
      queryClient.invalidateQueries({ queryKey: keys.assistants })
    },
  })
  const remove = useMutation({
    mutationFn: () => api.deleteAssistant(assistant.id),
    onSuccess: () => {
      navigate('/assistants', { replace: true })
      queryClient.removeQueries({ queryKey: keys.assistant(assistant.id) })
      queryClient.removeQueries({ queryKey: keys.documents(assistant.id) })
      queryClient.invalidateQueries({ queryKey: keys.assistants })
      queryClient.invalidateQueries({ queryKey: keys.jobs })
    },
  })

  return (
    <div className="settings-grid">
      <section className="panel" aria-label={t('settings.usage')}>
        <div className="row between">
          <span className="lbl">{t('settings.usage')}</span>
          <span className="hint">{planName(me.plan)}</span>
        </div>
        <UsageMeters me={me} />
      </section>
      <section className="panel" aria-label={t('details.contact')}>
        <span className="lbl">{t('details.contact')}</span>
        <span className="hint">{t('details.contactHint')}</span>
        <InlineEdit value={assistant.fallback_contact} mono empty={t('settings.noContact')} label={t('details.contact')} onSave={(v) => update.mutateAsync({ fallback_contact: v })} />
      </section>
      <section className="panel" aria-label={t('settings.assistant')}>
        <span className="lbl">{t('settings.assistant')}</span>
        <InlineEdit value={assistant.name} label={t('details.name')} action={t('settings.rename')} required onSave={(v) => update.mutateAsync({ name: v })} />
        {assistant.published && (
          <button type="button" className="btn-text small danger" onClick={() => setConfirm('offline')}>
            {t('settings.unpublish')}
          </button>
        )}
        {update.error != null && <p className="field-error">{errorText(update.error)}</p>}
      </section>
      <section className="panel" aria-label={t('settings.delete')}>
        <span className="lbl">{t('settings.delete')}</span>
        <span className="hint">{t('settings.deleteHint')}</span>
        <button type="button" className="btn-text small danger" disabled={remove.isPending} onClick={() => setConfirm('delete')}>
          {remove.isPending ? t('settings.deleting') : t('settings.delete')}
        </button>
        {remove.error != null && <p className="field-error">{errorText(remove.error)}</p>}
      </section>
      {confirm === 'offline' && (
        <ConfirmDialog
          title={t('settings.unpublishTitle')}
          confirmLabel={t('settings.unpublish')}
          onCancel={() => setConfirm(null)}
          onConfirm={() => {
            setConfirm(null)
            update.mutate({ published: false })
          }}
        >
          <p>{t('settings.unpublishBody')}</p>
        </ConfirmDialog>
      )}
      {confirm === 'delete' && (
        <ConfirmDialog
          title={t('settings.deleteTitle', { name: assistant.name })}
          confirmLabel={t('settings.delete')}
          onCancel={() => setConfirm(null)}
          onConfirm={() => {
            setConfirm(null)
            remove.mutate()
          }}
        >
          <p>{t('settings.deleteBody')}</p>
        </ConfirmDialog>
      )}
    </div>
  )
}
