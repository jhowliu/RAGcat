// Translation keys (designs/DESIGN.md §11): English is the default, zh-Hant is complete.
// `t(key, vars)` fills {name} placeholders; `tn(base, n)` picks `${base}_one` or `${base}_other`.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { en, type Messages } from './locales/en'
import { zh } from './locales/zh'

export type Lang = 'en' | 'zh'
export type Key = keyof Messages
type PluralBase = { [K in Key]: K extends `${infer B}_one` ? B : never }[Key]
type Vars = Record<string, string | number>

const DICTS: Record<Lang, Messages> = { en, zh }
const LOCALE: Record<Lang, string> = { en: 'en-US', zh: 'zh-TW' }
const STORAGE_KEY = 'ragcat-lang'

function storedLang(): Lang {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'zh' ? 'zh' : 'en'
  } catch {
    return 'en'
  }
}

function fill(text: string, vars?: Vars): string {
  return vars ? text.replace(/\{(\w+)\}/g, (m, name: string) => (name in vars ? String(vars[name]) : m)) : text
}

export interface I18n {
  lang: Lang
  setLang: (lang: Lang) => void
  t: (key: Key, vars?: Vars) => string
  tn: (base: PluralBase, n: number, vars?: Vars) => string
  /** 1,640 */
  num: (n: number) => string
  /** Sep 28 */
  date: (iso: string) => string
  /** Sep 28, 14:02 */
  dateTime: (iso: string) => string
  /** 14:02 */
  time: (when: string | Date) => string
}

const Ctx = createContext<I18n | null>(null)

/** `initialLang` lets an embedded surface (the Website widget) follow its host page instead of the
 * language saved for the app. */
export function I18nProvider({ children, initialLang }: { children: ReactNode; initialLang?: Lang }) {
  const [lang, setLangState] = useState<Lang>(() => initialLang ?? storedLang())
  const setLang = useCallback((next: Lang) => {
    setLangState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* private mode: the choice lasts for this visit */
    }
  }, [])
  useEffect(() => {
    document.documentElement.lang = lang === 'zh' ? 'zh-Hant' : 'en'
  }, [lang])

  const value = useMemo<I18n>(() => {
    const dict = DICTS[lang]
    const locale = LOCALE[lang]
    const t = (key: Key, vars?: Vars) => fill(dict[key], vars)
    const day = new Intl.DateTimeFormat(locale, { month: 'short', day: 'numeric' })
    const clock = new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
    return {
      lang,
      setLang,
      t,
      tn: (base, n, vars) => t(`${base}_${n === 1 ? 'one' : 'other'}` as Key, { n: n.toLocaleString(locale), ...vars }),
      num: (n) => n.toLocaleString(locale),
      date: (iso) => day.format(new Date(iso)),
      dateTime: (iso) => `${day.format(new Date(iso))}, ${clock.format(new Date(iso))}`,
      time: (when) => clock.format(typeof when === 'string' ? new Date(when) : when),
    }
  }, [lang, setLang])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useI18n(): I18n {
  const value = useContext(Ctx)
  if (!value) throw new Error('useI18n outside I18nProvider')
  return value
}
