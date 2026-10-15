// App header (DESIGN.md §8 Header & navigation) and the task rail (§9).
import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Link, Outlet } from 'react-router'
import { api, type Job } from '../api'
import { devUser, useAuth } from '../auth'
import { clock, keys, useElapsed, useJobs, useMe, useSignOut } from '../hooks'
import { useI18n } from '../i18n'
import { planName, stageText } from '../model'
import { LanguageSwitch, Mark, Progress, StatusDot } from './ui'
import { UsageMeters } from './UsageMeters'

export function AppLayout() {
  return (
    <>
      <AppHeader />
      <main>
        <Outlet />
      </main>
    </>
  )
}

function AppHeader() {
  const { t, tn } = useI18n()
  const { data: jobs = [] } = useJobs()
  return (
    <header className="app-header">
      <div className="wrap">
        {/* With one hub there is no nav row: the mark and wordmark lead back to the Assistants list. */}
        <Link to="/assistants" className="brand" aria-label={t('nav.home')}>
          <Mark size={26} />
          RAGcat
        </Link>
        <div className="header-right">
          {jobs.length > 0 && (
            <span className="task-pill">
              <StatusDot kind="warning">{tn('tasks.running', jobs.length)}</StatusDot>
            </span>
          )}
          <LanguageSwitch />
          <AccountMenu />
        </div>
      </div>
    </header>
  )
}

function AccountMenu() {
  const { t, date } = useI18n()
  const { data: me } = useMe()
  const session = useAuth()
  const signOut = useSignOut()
  const [open, setOpen] = useState(false)
  const anchor = useRef<HTMLDivElement>(null)
  // The profile name, once loaded, follows renames on the Account page.
  const name = me?.name || (session.status === 'signed-in' ? session.name : '') || devUser()

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !anchor.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [open])

  return (
    <div className="menu-anchor" ref={anchor}>
      <button type="button" className="avatar" aria-label={t('account.label', { name })} aria-expanded={open} onClick={() => setOpen(!open)}>
        {name.slice(0, 1).toUpperCase()}
      </button>
      {open && (
        <div className="menu">
          <div className="field">
            <span className="lbl">{name}</span>
            <span className="hint">{me?.email || (session.status === 'signed-in' ? session.email : null) || (session.status === 'signed-in' && session.mode === 'dev' ? t('account.dev') : '')}</span>
          </div>
          {me && (
            <section className="menu-usage" aria-label={t('usage.title')}>
              <div className="field">
                <span className="lbl">{t('usage.title')}</span>
                <span className="hint">{t('usage.lead', { plan: planName(me.plan), date: date(me.usage.period_start) })}</span>
              </div>
              <UsageMeters me={me} />
            </section>
          )}
          {session.status === 'signed-in' && (
            <button type="button" className="btn btn-line small" onClick={signOut}>
              {t('account.signOut')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

/** Background work for one Assistant: reading and publishing Documents. */
export function TaskRail({ jobs }: { jobs: Job[] }) {
  const i18n = useI18n()
  const { t } = i18n
  const queryClient = useQueryClient()
  const elapsed = useElapsed(jobs[0]?.progress?.started_at)
  if (!jobs.length) return null
  return (
    <div className="task-rail" role="status" aria-label={t('tasks.label')}>
      <div className="task-rail-head">
        <span>{t('tasks.head', { n: jobs.length })}</span>
        <span className="mono hint">{clock(elapsed)}</span>
      </div>
      {jobs.map((job) => (
        <div className="task" key={job.document_id}>
          <span className="mono task-file">{job.filename}</span>
          <Progress value={job.progress?.done ?? 0} max={job.progress?.total || 1} label={job.filename} />
          <div className="row between">
            <span className="hint">{stageText(job.progress, i18n)}</span>
            {job.type === 'parse' && (
              <button
                type="button"
                className="btn-text small"
                onClick={async () => {
                  await api.cancel(job.document_id)
                  queryClient.invalidateQueries({ queryKey: keys.jobs })
                  queryClient.invalidateQueries({ queryKey: keys.documents(job.assistant_id) })
                }}
              >
                {t('common.cancel')}
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
