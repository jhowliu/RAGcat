// Shared components (designs/DESIGN.md §8–9). Pages compose these; they don't restyle them.
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { useI18n, type Key } from '../i18n'

// ------------------------------------------------------------------ icons (designs/icons)

const PATHS = {
  alert: ['M12 4 3 20h18z', 'M12 10v4', 'M12 17v.5'],
  bell: ['M6 10a6 6 0 0 1 12 0v4l2 3H4l2-3z', 'M10 20h4'],
  // An open book: two pages meeting at the spine, read clearly at 16–18px.
  book: ['M12 7c-2-1.5-4.5-2-8-2v12.5c3.5 0 6 .5 8 2 2-1.5 4.5-2 8-2V5c-3.5 0-6 .5-8 2z', 'M12 7v12.5'],
  check: ['m5 12.5 4.5 4.5L19 7'],
  chev: ['m9 6 6 6-6 6'],
  close: ['M6.5 6.5l11 11M17.5 6.5l-11 11'],
  copy: ['M9 9h10v11H9z', 'M15 9V5H5v11h4'],
  down: ['m6 9 6 6 6-6'],
  clock: ['M12 8v4l3 2'],
  doc: ['M14 4H7v16h10V7z', 'M14 4v3h3', 'M9.5 12h5M9.5 15h5'],
  layers: ['m12 4 8 4-8 4-8-4z', 'm4 12 8 4 8-4', 'm4 16 8 4 8-4'],
  left: ['m15 6-6 6 6 6'],
  lens: ['m15 15 5 5'],
  link: ['M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1', 'M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1', 'M4 4l16 16'],
  lock: ['M8 11V8a4 4 0 0 1 8 0v3'],
  mail: ['m4 7 8 6 8-6'],
  person: ['M5 20a7 7 0 0 1 14 0'],
  plus: ['M12 5v14M5 12h14'],
  // A speech bubble with a footnote mark: an answer that cites its source.
  quote: ['M5 5.5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-8l-4 3v-3H5a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1z', 'M8.5 9.5h4M8.5 12.5h7', 'M16 8.5v2'],
  trash: ['M5 7h14', 'M10 7V5h4v2', 'M7 7l1 13h8l1-13'],
  undo: ['M9 14 4 9l5-5', 'M4 9h11a5 5 0 0 1 0 10h-3'],
  up: ['M12 16V5', 'm7 10 5-5 5 5', 'M5 19h14'],
} as const
const EXTRA: Partial<Record<keyof typeof PATHS, ReactNode>> = {
  clock: <circle cx="12" cy="12" r="8" />,
  lens: <circle cx="10.5" cy="10.5" r="6" />,
  lock: <rect x="5" y="11" width="14" height="9" rx="2" />,
  mail: <rect x="3.5" y="5.5" width="17" height="13" rx="2" />,
  person: <circle cx="12" cy="8.5" r="3.5" />,
}
export type IconName = keyof typeof PATHS

export function Icon({ name, size = 18, stroke, className }: { name: IconName; size?: number; stroke?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={stroke ?? (size <= 18 ? 1.9 : 1.75)}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {EXTRA[name]}
      {PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  )
}

/** Brand mark: the mascot's head, redrawn to stay legible from 16px. The white face reads on light
 * and dark grounds alike. Also the Assistant's avatar in the Test chat. Always decorative. */
export function Mark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <g fill="none" stroke="var(--rc-ink)" strokeLinecap="round" strokeLinejoin="round">
        <path d="M5.2 15.5 6.6 2.6l5.8 5.8h7.2l5.8-5.8 1.4 12.9c.2 6-4.4 11.7-10.8 11.7S5 21.5 5.2 15.5Z" fill="var(--rc-surface)" strokeWidth="1.8" />
        <path d="M7.7 5.6l2.9 3.1-3.4 2.5ZM24.3 5.6l-2.9 3.1 3.4 2.5Z" fill="var(--rc-brand)" stroke="none" />
        <circle cx="12" cy="16.4" r="3.4" strokeWidth="1.3" />
        <circle cx="20" cy="16.4" r="3.4" strokeWidth="1.3" />
        <path d="M15.4 16.2h1.2M1.4 18.4l5.6 1M1.6 22l5.4-.8M30.6 18.4l-5.6 1M30.4 22l-5.4-.8M14.3 22.6q.85.9 1.7 0 .85.9 1.7 0" strokeWidth="1" />
      </g>
      <g fill="var(--rc-ink)">
        <circle cx="12" cy="16.7" r="1" />
        <circle cx="20" cy="16.7" r="1" />
        <path d="M15.1 20.5h1.8l-.9 1.1Z" />
      </g>
    </svg>
  )
}

// ------------------------------------------------------------------ status

export type ChipKind = 'attn' | 'neutral' | 'warn' | 'info' | 'done'

export function Chip({ kind, children }: { kind: ChipKind; children: ReactNode }) {
  return <span className={`chip chip-${kind}`}>{children}</span>
}

export function StatusDot({ kind, children }: { kind: 'success' | 'warning' | 'idle'; children: ReactNode }) {
  return (
    <span className="with-dot">
      <span className={`dot ${kind}`} aria-hidden="true" />
      {children}
    </span>
  )
}

export function Progress({ value, max, label, warning }: { value: number; max: number; label: string; warning?: boolean }) {
  const pct = max > 0 ? Math.min(100, Math.round((100 * value) / max)) : 0
  return (
    <div className={`progress ${warning ? 'warning' : ''}`} role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={value}>
      <span style={{ transform: `scaleX(${pct / 100})` }} />
    </div>
  )
}

export function Callout({ children }: { children: ReactNode }) {
  return (
    <p className="callout">
      <Icon name="alert" size={15} />
      <span>{children}</span>
    </p>
  )
}

export function ErrorPanel({ title, icon = 'alert', children, action }: { title: string; icon?: 'alert' | 'lock'; children?: ReactNode; action?: ReactNode }) {
  return (
    <section className="panel error-panel" role="alert">
      <div className="pbody">
        <span className="error-title">
          <Icon name={icon} size={18} />
          {title}
        </span>
        {children && <p>{children}</p>}
        {action}
      </div>
    </section>
  )
}

/** "● Saved 11:04" (aria-live so screen readers hear each save). */
export function Saved({ at, saving }: { at: Date | string | null; saving?: boolean }) {
  const { t, time } = useI18n()
  return (
    <span className="saved" aria-live="polite">
      {saving ? (
        t('common.saving')
      ) : at ? (
        <>
          <span className="dot success" aria-hidden="true" />
          {t('common.savedAt', { time: time(at) })}
        </>
      ) : null}
    </span>
  )
}

// ------------------------------------------------------------------ controls

/** EN / 中文. The label stays bilingual so a reader of either language can find it. */
export function LanguageSwitch() {
  const { lang, setLang } = useI18n()
  return (
    <Segmented
      label="Language / 語言"
      value={lang}
      onChange={setLang}
      options={[
        { value: 'en', label: <span lang="en">EN</span> },
        { value: 'zh', label: <span lang="zh-Hant">中文</span> },
      ]}
    />
  )
}

/** A value with an Edit button that turns into an input with Save and Cancel. Escape cancels, and
 * focus returns to Edit afterwards. The caller shows a failed save; the field stays open to retry. */
export function InlineEdit({
  value,
  label,
  onSave,
  mono,
  empty,
  action,
  required,
}: {
  value: string
  label: string
  onSave: (value: string) => Promise<unknown>
  mono?: boolean
  empty?: string
  action?: string
  required?: boolean
}) {
  const { t } = useI18n()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const [busy, setBusy] = useState(false)
  const editButton = useRef<HTMLButtonElement>(null)
  const refocus = useRef(false)

  useEffect(() => {
    if (editing || !refocus.current) return
    refocus.current = false
    editButton.current?.focus()
  }, [editing])

  const close = () => {
    refocus.current = true
    setEditing(false)
  }

  if (!editing) {
    return (
      <div className="row between">
        <span className={mono ? 'inline-value data' : 'inline-value'}>{value || <span className="hint">{empty}</span>}</span>
        <button
          ref={editButton}
          type="button"
          className="btn-text small"
          onClick={() => {
            setDraft(value)
            setEditing(true)
          }}
        >
          {action ?? t('settings.edit')}
        </button>
      </div>
    )
  }
  const invalid = required && !draft.trim()
  return (
    <form
      className="row inline-edit"
      onKeyDown={(e) => {
        if (e.key !== 'Escape') return
        e.stopPropagation()
        close()
      }}
      onSubmit={async (e) => {
        e.preventDefault()
        if (invalid) return
        setBusy(true)
        try {
          await onSave(draft.trim())
          close()
        } catch {
          // Shown by the caller; keep the draft so the owner can fix it and save again.
        } finally {
          setBusy(false)
        }
      }}
    >
      <input className={`input ${mono ? 'mono' : ''}`} aria-label={label} value={draft} autoFocus maxLength={mono ? 200 : 80} aria-invalid={invalid} onChange={(e) => setDraft(e.target.value)} />
      <span className="row">
        <button type="submit" className="btn btn-line compact" disabled={busy || invalid}>
          {t('common.save')}
        </button>
        <button type="button" className="btn-text small" onClick={close}>
          {t('common.cancel')}
        </button>
      </span>
    </form>
  )
}


export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (next: boolean) => void; label: string; disabled?: boolean }) {
  return <button type="button" role="switch" className="switch" aria-checked={checked} aria-label={label} disabled={disabled} onClick={() => onChange(!checked)} />
}

/** Filters use aria-pressed; a view switcher (`tabs`) uses role="tab" with aria-selected. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  tabs = false,
}: {
  options: { value: T; label: ReactNode }[]
  value: T
  onChange: (value: T) => void
  label: string
  tabs?: boolean
}) {
  return (
    <div className="seg-group" role={tabs ? 'tablist' : 'group'} aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className="seg"
          {...(tabs ? { role: 'tab', 'aria-selected': o.value === value } : { 'aria-pressed': o.value === value })}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Tabs<T extends string>({
  items,
  value,
  onChange,
  label,
}: {
  items: { value: T; label: string; count?: number }[]
  value: T
  onChange: (value: T) => void
  label: string
}) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {items.map((it) => (
        <button key={it.value} type="button" role="tab" className="tabbtn" aria-selected={it.value === value} onClick={() => onChange(it.value)}>
          {it.label}
          {it.count !== undefined && <span className="cnt">{it.count}</span>}
        </button>
      ))}
    </div>
  )
}

export function Field({ id, label, hint, error, children }: { id: string; label: string; hint?: string; error?: string | null; children: ReactNode }) {
  return (
    <div className="field">
      <label className="lbl" htmlFor={id}>
        {label}
      </label>
      {children}
      {error ? <span className="field-error">{error}</span> : hint && <span className="hint">{hint}</span>}
    </div>
  )
}

// ------------------------------------------------------------------ navigation

export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="back">
      <Icon name="left" size={16} stroke={1.75} />
      {children}
    </Link>
  )
}

const STEPS: { path: string; label: Key }[] = [
  { path: 'setup', label: 'steps.setup' },
  { path: 'review', label: 'steps.review' },
  { path: 'publish', label: 'steps.publish' },
]

/** Create flow: Setup → Review & test → Publish. Done steps link back; upcoming ones don't. */
export function Stepper({ aid, current }: { aid: string | null; current: 1 | 2 | 3 }) {
  const { t } = useI18n()
  return (
    <nav className="stepper" aria-label={t('steps.label')}>
      <ol>
        {STEPS.map((s, i) => {
          const n = i + 1
          const state = n < current ? 'done' : n === current ? 'current' : 'upcoming'
          const circle = (
            <span className="step-circle">{state === 'done' ? <Icon name="check" size={14} stroke={2.2} /> : n}</span>
          )
          return [
            i > 0 && <li key={`line-${n}`} className="line" aria-hidden="true" />,
            <li key={s.path} className={`step ${state}`} aria-current={state === 'current' ? 'step' : undefined}>
              {state === 'done' && aid ? (
                <Link to={`/assistants/${aid}/${s.path}`}>
                  {circle}
                  <span className="step-label">{t(s.label)}</span>
                </Link>
              ) : (
                <>
                  {circle}
                  <span className="step-label">{t(s.label)}</span>
                  {state === 'current' && <span className="hint">· {t('steps.stepOf', { n })}</span>}
                </>
              )}
            </li>,
          ]
        })}
      </ol>
    </nav>
  )
}

// ------------------------------------------------------------------ dialog

/** Modal confirmation on <dialog>: Esc or a click on the backdrop cancels. */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  title: string
  children: ReactNode
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
}) {
  const { t } = useI18n()
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
    return () => dialog?.close()
  }, [])
  return (
    <dialog
      ref={ref}
      className="confirm"
      aria-labelledby="confirm-title"
      onCancel={(e) => {
        e.preventDefault()
        onCancel()
      }}
      onClick={(e) => e.target === ref.current && onCancel()}
    >
      <div className="pbody">
        <h2 id="confirm-title" className="display title">
          {title}
        </h2>
        {children}
      </div>
      <div className="dialog-actions">
        <button type="button" className="btn btn-line" onClick={onCancel}>
          {t('common.cancel')}
        </button>
        <button type="button" className="btn btn-dark" autoFocus onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </dialog>
  )
}

export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}
