// Monthly usage against the plan (account menu and the Assistant's Settings tab).
import type { Me } from '../api'
import { useI18n } from '../i18n'
import { Progress } from './ui'

const WARN_AT = 0.8

export const answersShare = (me: Me) => (me.usage.answers_limit ? me.usage.answers / me.usage.answers_limit : 0)

export function UsageMeters({ me }: { me: Me }) {
  const { t, num } = useI18n()
  const rows = [
    { label: t('usage.pages'), aria: t('usage.pagesMonth'), used: me.usage.pages_read, limit: me.usage.pages_limit },
    { label: t('usage.answers'), aria: t('usage.answersMonth'), used: me.usage.answers, limit: me.usage.answers_limit },
  ]
  return (
    <>
      {rows.map((r) => {
        const share = r.limit ? r.used / r.limit : 0
        return (
          <div className="meter" key={r.label}>
            <div className="meter-head">
              <span>{r.label}</span>
              <span className="mono">
                {num(r.used)} / {num(r.limit)}
              </span>
            </div>
            <Progress value={r.used} max={r.limit} label={r.aria} warning={share >= WARN_AT} />
            {share >= WARN_AT && <span className="meter-warn">{t('usage.used', { pct: Math.round(share * 100) })}</span>}
          </div>
        )
      })}
    </>
  )
}
