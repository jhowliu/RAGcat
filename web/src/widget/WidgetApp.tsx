// The Website widget's panel, inside the iframe that web/widget.js opens on an owner's site
// (docs/api-design.md §7). It is the Test pane handed to the customer: one question at a time,
// each answer naming the Document and page it used. Rendered as text only: the frame shares an
// origin with the owner's app, so Document text must never become HTML.
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Cat } from '../components/Cat'
import { ErrorPanel, Icon, Mark } from '../components/ui'
import { useI18n, type I18n } from '../i18n'
import { WidgetError, asker, type WidgetCitation, type WidgetConfig, type WidgetDone } from './ask'

interface Turn {
  question: string
  answer: string
  citations: WidgetCitation[]
  done: WidgetDone | null
  /** Seconds to wait, when the visitor asked too often. */
  limited: number | null
  failed: boolean
}

const UNAVAILABLE = new Set(['NOT_PUBLISHED', 'QUOTA_EXCEEDED', 'NOT_FOUND'])
const embedded = window.parent !== window

export function WidgetApp({ aid, config }: { aid: string; config: WidgetConfig }) {
  const { t, lang } = useI18n()
  const ask = useMemo(() => asker(aid, lang), [aid, lang])
  const [available, setAvailable] = useState(config.available)
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const [retryAt, setRetryAt] = useState(0)
  const [now, setNow] = useState(() => Date.now())
  // The finished answer, read once by screen readers (the streaming card itself stays quiet).
  const [announce, setAnnounce] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const end = useRef<HTMLDivElement>(null)
  const waitSeconds = Math.max(0, Math.ceil((retryAt - now) / 1000))

  // Keep the newest answer in view, scrolling only the transcript.
  useEffect(() => {
    const box = end.current?.parentElement
    if (box) box.scrollTop = box.scrollHeight
  }, [turns])

  // Count down while the visitor waits out the rate limit.
  useEffect(() => {
    if (retryAt <= Date.now()) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [retryAt])

  // The loader asks for focus when it opens the panel; Escape asks it to close.
  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.source === window.parent && e.data?.type === 'ragcat:open') input.current?.focus()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && embedded) close()
    }
    window.addEventListener('message', onMessage)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('message', onMessage)
      window.removeEventListener('keydown', onKey)
    }
  }, [])

  const update = (patch: Partial<Turn>) => setTurns((ts) => ts.map((x, i) => (i === ts.length - 1 ? { ...x, ...patch } : x)))

  async function run(q: string) {
    setBusy(true)
    setAnnounce('')
    let answer = ''
    let citations: WidgetCitation[] = []
    try {
      await ask(q, {
        onToken: (text) => {
          answer += text
          setTurns((ts) => ts.map((x, i) => (i === ts.length - 1 ? { ...x, answer: x.answer + text } : x)))
        },
        onCitations: (items) => {
          citations = items
          update({ citations: items })
        },
        onDone: (done) => {
          update({ done })
          setAnnounce(
            done.answered
              ? [answer, citations.length ? `${t('widget.sources')}: ${citations.map((c) => `[${c.n}] ${sourceText(c, t)}`).join('; ')}` : ''].join(' ')
              : [done.fallback?.message || t('widget.noAnswer'), done.fallback?.contact ?? ''].join(' '),
          )
        },
      })
    } catch (err) {
      if (err instanceof WidgetError && (err.status === 404 || UNAVAILABLE.has(err.code))) {
        setAvailable(false)
      } else if (err instanceof WidgetError && err.status === 429) {
        const seconds = err.retryAfter ?? 60
        setRetryAt(Date.now() + seconds * 1000)
        setNow(Date.now())
        update({ limited: seconds })
        setQuestion((current) => current || q)
      } else {
        update({ failed: true })
      }
    } finally {
      setBusy(false)
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    const q = question.trim()
    if (!q || busy || waitSeconds > 0) return
    setQuestion('')
    setTurns((ts) => [...ts, { question: q, answer: '', citations: [], done: null, limited: null, failed: false }])
    void run(q)
  }

  function retry() {
    const last = turns.at(-1)
    if (!last || busy) return
    update({ answer: '', citations: [], done: null, failed: false })
    void run(last.question)
  }

  return (
    <div className="w-app">
      <header className="w-head">
        <span className="bot-avatar w-avatar" aria-hidden="true">
          <Mark size={24} />
        </span>
        <div className="w-title">
          <h1 className="w-name">{config.name || t('widget.defaultName')}</h1>
          <p className="hint">{t('widget.tagline')}</p>
        </div>
        {embedded && (
          <button type="button" className="ibtn compact w-close" aria-label={t('widget.close')} onClick={close}>
            <Icon name="close" size={18} />
          </button>
        )}
      </header>

      <main className="transcript w-body" aria-label={t('widget.conversation')}>
        {!available ? (
          <div className="w-empty">
            <Cat pose="sleep" size={132} eager />
            <h2 className="display w-empty-title">{t('widget.offTitle')}</h2>
            <p className="w-empty-body">{config.contact ? t('widget.offBody') : t('widget.offBodyNoContact')}</p>
            {config.contact && <Contact value={config.contact} />}
          </div>
        ) : turns.length === 0 ? (
          <div className="w-empty">
            <Cat pose="read" size={84} eager />
            <h2 className="display w-empty-title">{t('widget.emptyTitle')}</h2>
            <p className="w-empty-body">{t('widget.emptyBody')}</p>
            <p className="hint">{t('widget.emptyHint')}</p>
          </div>
        ) : (
          turns.map((turn, i) => <TurnView key={i} id={`t${i}`} turn={turn} streaming={busy && i === turns.length - 1} waitSeconds={waitSeconds} onRetry={retry} />)
        )}
        <div ref={end} />
      </main>

      <p className="sr-only" aria-live="polite">
        {announce}
      </p>
      {available && (
        <form className="ask-bar w-ask" onSubmit={submit}>
          {turns.length > 0 && <p className="hint w-ask-hint">{t('widget.emptyHint')}</p>}
          <label htmlFor="w-question" className="sr-only">
            {t('widget.askLabel')}
          </label>
          <input
            ref={input}
            id="w-question"
            className="input"
            value={question}
            maxLength={1000}
            autoComplete="off"
            placeholder={t('widget.placeholder')}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <button type="submit" className="btn btn-dark" disabled={busy || waitSeconds > 0 || !question.trim()}>
            {waitSeconds > 0 ? <span className="mono">{t('widget.waitShort', { s: waitSeconds })}</span> : t('widget.ask')}
          </button>
        </form>
      )}
      <footer className="w-foot">
        <a href={new URL('/', location.href).href} target="_blank" rel="noopener">
          <Mark size={14} />
          {t('widget.poweredBy')}
        </a>
      </footer>
    </div>
  )
}

function TurnView({ id, turn, streaming, waitSeconds, onRetry }: { id: string; turn: Turn; streaming: boolean; waitSeconds: number; onRetry: () => void }) {
  const { t } = useI18n()
  const [active, setActive] = useState<number | null>(null)
  const parts = turn.answer.split(/(\[\d+\])/)
  return (
    <>
      <div className="bubble">{turn.question}</div>
      <div className="bot-turn">
        <span className="bot-avatar" aria-hidden="true">
          <Mark size={22} />
        </span>
        {turn.limited != null ? (
          <p className="hint w-note" role="status">
            <Icon name="clock" size={15} />
            {waitSeconds > 0 ? t('widget.limited', { s: waitSeconds }) : t('widget.limitedOver')}
          </p>
        ) : turn.failed ? (
          <ErrorPanel
            title={t('widget.failed')}
            action={
              <button type="button" className="btn-text small" onClick={onRetry}>
                {t('widget.retry')}
              </button>
            }
          >
            {t('widget.failedBody')}
          </ErrorPanel>
        ) : streaming && !turn.answer && !turn.done ? (
          <p className="hint" role="status">
            {t('widget.reading')}
          </p>
        ) : (
          <div className="panel answer">
            {turn.done && !turn.done.answered ? (
              <>
                <span className="answer-text">{turn.done.fallback?.message || t('widget.noAnswer')}</span>
                {turn.done.fallback?.contact && <Contact value={turn.done.fallback.contact} />}
              </>
            ) : (
              <span className="answer-text">
                {parts.map((part, i) => {
                  const n = /^\[(\d+)\]$/.exec(part)?.[1]
                  if (!n) return <span key={i}>{part}</span>
                  const cited = turn.citations.some((c) => c.n === Number(n))
                  return cited ? (
                    <button
                      key={i}
                      type="button"
                      className="fn"
                      aria-describedby={`${id}-src${n}`}
                      onMouseEnter={() => setActive(Number(n))}
                      onMouseLeave={() => setActive(null)}
                      onFocus={() => setActive(Number(n))}
                      onBlur={() => setActive(null)}
                    >
                      {n}
                    </button>
                  ) : (
                    <span key={i} className="fn">
                      {n}
                    </span>
                  )
                })}
                {streaming && <span className="cursor" aria-hidden="true" />}
              </span>
            )}
            {turn.done?.answered && turn.citations.length > 0 && (
              <ol className="cites w-sources" aria-label={t('widget.sources')}>
                {turn.citations.map((c) => (
                  <li key={c.n} id={`${id}-src${c.n}`} className="w-source">
                    <span className="w-source-n">[{c.n}]</span>
                    {active === c.n ? <mark className="cite sweep">{sourceText(c, t)}</mark> : <span>{sourceText(c, t)}</span>}
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}
      </div>
    </>
  )
}

/** returns-policy.pdf · p. 1 ¶2, the same page and paragraph form as the app's Test answers. */
function sourceText(c: WidgetCitation, t: I18n['t']): string {
  return `${c.document_title} · ${t('widget.page', { n: c.page })}${c.para ? ` ¶${c.para}` : ''}`
}

function Contact({ value }: { value: string }) {
  const email = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
  return (
    <p className="w-contact">
      <Icon name="mail" size={16} />
      {email ? (
        <a className="mono" href={`mailto:${value}`}>
          {value}
        </a>
      ) : (
        <span className="mono">{value}</span>
      )}
    </p>
  )
}

function close() {
  window.parent.postMessage({ type: 'ragcat:close' }, '*')
}
