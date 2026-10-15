// The owner's side of the Website widget (docs/api-design.md §7): the sites allowed to show it and
// the one line to paste. Shown on Publish (panel 2) and in the Assistant's Channels tab.
import { useEffect, useState, type FormEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api, type Assistant } from '../api'
import { keys } from '../hooks'
import { useI18n, type Key } from '../i18n'
import { MAX_ORIGINS, addOrigin, embedSnippet, type OriginError } from '../widget/origins'
import { Chip, Icon } from './ui'

const ERRORS: Record<OriginError, Key> = {
  empty: 'website.errEmpty',
  invalid: 'website.errInvalid',
  wildcard: 'website.errWildcard',
  insecure: 'website.errInsecure',
  duplicate: 'website.errDuplicate',
  limit: 'website.errLimit',
}

export function WebsitePanel({ assistant, title, locked = false }: { assistant: Assistant; title: string; locked?: boolean }) {
  const { t } = useI18n()
  const { origins, save } = useWidgetOrigins(assistant)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const snippet = embedSnippet(location.origin, assistant.id)
  const on = origins.length > 0

  useEffect(() => {
    if (!copied) return
    const id = setTimeout(() => setCopied(false), 2000)
    return () => clearTimeout(id)
  }, [copied])

  async function commit(next: string[]) {
    setBusy(true)
    try {
      await save(next)
      return true
    } catch {
      setError(t('website.saveFailed'))
      return false
    } finally {
      setBusy(false)
    }
  }

  async function add(e: FormEvent) {
    e.preventDefault()
    const result = addOrigin(origins, draft)
    if (!result.ok) {
      const origin = result.error === 'duplicate' ? draft.trim() : ''
      setError(t(ERRORS[result.error], { origin, n: MAX_ORIGINS }))
      return
    }
    setError(null)
    if (await commit(result.origins)) setDraft('')
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(snippet)
      setCopied(true)
    } catch {
      // No clipboard permission: select the line so the owner can copy it themselves.
      const code = document.getElementById(`snippet-${assistant.id}`)
      if (code) getSelection()?.selectAllChildren(code)
    }
  }

  return (
    <section className="panel" aria-labelledby={`website-${assistant.id}`}>
      <div className="phead">
        <h2 id={`website-${assistant.id}`} className="phead-title lg">
          {title}
        </h2>
        {!locked && <Chip kind={on ? 'done' : 'neutral'}>{on ? t('website.on') : t('website.off')}</Chip>}
      </div>
      <div className="pbody">
        <p className="website-lead">{t('website.lead')}</p>
        {locked ? (
          <p className="website-locked">
            <Icon name="lock" size={16} />
            {t('website.locked')}
          </p>
        ) : (
          <>
            <div className="field">
              <span className="lbl" id={`sites-${assistant.id}`}>
                {t('website.sites')}
              </span>
              <span className="hint">{t('website.sitesHint')}</span>
              {on ? (
                <ul className="origin-list" aria-labelledby={`sites-${assistant.id}`}>
                  {origins.map((o) => (
                    <li key={o} className="origin-row">
                      <span className="data">{o}</span>
                      <button
                        type="button"
                        className="btn-text small"
                        aria-label={t('website.removeLabel', { origin: o })}
                        disabled={busy}
                        onClick={() => {
                          setError(null)
                          void commit(origins.filter((x) => x !== o))
                        }}
                      >
                        {t('website.remove')}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="origin-empty">{t('website.noSites')}</p>
              )}
              <form className="origin-add" onSubmit={add} noValidate>
                <label htmlFor={`origin-${assistant.id}`} className="sr-only">
                  {t('website.address')}
                </label>
                <input
                  id={`origin-${assistant.id}`}
                  className="input mono"
                  value={draft}
                  inputMode="url"
                  autoComplete="url"
                  spellCheck={false}
                  placeholder={t('website.placeholder')}
                  aria-invalid={error ? true : undefined}
                  aria-describedby={error ? `origin-error-${assistant.id}` : undefined}
                  onChange={(e) => {
                    setDraft(e.target.value)
                    setError(null)
                  }}
                />
                <button type="submit" className="btn btn-line" disabled={busy || origins.length >= MAX_ORIGINS}>
                  <Icon name="plus" size={16} stroke={2} />
                  {t('website.add')}
                </button>
              </form>
              {error && (
                <span className="field-error" id={`origin-error-${assistant.id}`} role="alert">
                  {error}
                </span>
              )}
            </div>

            <div className="field">
              <span className="lbl">{t('website.code')}</span>
              <span className="hint">{t('website.codeHint')}</span>
              <div className="snippet">
                <code id={`snippet-${assistant.id}`} className="data">
                  {snippet}
                </code>
                <button type="button" className="btn btn-line compact" onClick={copy}>
                  <Icon name={copied ? 'check' : 'copy'} size={16} />
                  {copied ? t('website.copied') : t('website.copy')}
                </button>
              </div>
              <span className="sr-only" aria-live="polite">
                {copied ? t('website.copied') : ''}
              </span>
            </div>
          </>
        )}
      </div>
    </section>
  )
}

function useWidgetOrigins(assistant: Assistant) {
  const queryClient = useQueryClient()
  async function save(next: string[]) {
    const a = await api.updateAssistant(assistant.id, { widget_origins: next })
    queryClient.setQueryData(keys.assistant(a.id), a)
    queryClient.invalidateQueries({ queryKey: keys.assistants })
  }
  return { origins: assistant.widget_origins, save }
}
