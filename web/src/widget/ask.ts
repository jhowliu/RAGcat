// How the Website widget gets answers (docs/api-design.md §7): one question at a time, streamed over
// SSE from `POST /v1/widget/{aid}/ask`. No sign-in; the page is on RAGcat's own origin, so no CORS.
// Until that route exists, the dev-only demo Assistants ("demo…") answer from a short script built
// on samples/mochi-returns-policy.pdf, including the rate-limit and failure paths.
import type { Lang } from '../i18n'

export interface WidgetCitation {
  n: number
  document_title: string
  page: number
  /** Paragraph on the page; tells two sources on one page apart. */
  para: number | null
}

export interface WidgetDone {
  answered: boolean
  fallback: { contact: string; message: string } | null
}

export interface WidgetHandlers {
  onToken: (text: string) => void
  onCitations: (items: WidgetCitation[]) => void
  onDone: (done: WidgetDone) => void
}

export class WidgetError extends Error {
  status: number
  code: string
  /** Seconds until the visitor may ask again (429 only). */
  retryAfter: number | null
  constructor(status: number, code: string, message: string, retryAfter: number | null = null) {
    super(message)
    this.status = status
    this.code = code
    this.retryAfter = retryAfter
  }
}

export type Asker = (question: string, handlers: WidgetHandlers, signal?: AbortSignal) => Promise<void>

/** What the frame page knows before the first question: the api writes it into the frame's HTML
 * (data-name, data-contact, data-available on #root). */
export interface WidgetConfig {
  name: string
  contact: string
  available: boolean
}

export function widgetConfig(aid: string, root: HTMLElement): WidgetConfig {
  if (isDemo(aid)) return { name: 'Mochi Pet Co. support', contact: 'help@mochipet.example', available: aid !== 'demo-off' }
  const { name, contact, available } = root.dataset
  return { name: name ?? '', contact: contact ?? '', available: available === 'true' }
}

export function isDemo(aid: string): boolean {
  return import.meta.env.DEV && /^demo(-|$)/.test(aid)
}

export function asker(aid: string, lang: Lang): Asker {
  return isDemo(aid) ? demoAsker(aid, lang) : liveAsker(aid)
}

function liveAsker(aid: string): Asker {
  return async (question, handlers, signal) => {
    let res: Response
    try {
      res = await fetch(`/v1/widget/${encodeURIComponent(aid)}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ question, stream: true }),
        ...(signal ? { signal } : {}),
      })
    } catch {
      throw new WidgetError(0, 'NETWORK', 'Network error')
    }
    if (!res.ok || !res.body) {
      const retry = Number(res.headers.get('Retry-After'))
      let code = 'ERROR'
      let message = res.statusText
      try {
        const body = await res.json()
        code = body.error?.code ?? code
        message = body.error?.message ?? message
      } catch {
        /* not JSON: keep the status text */
      }
      throw new WidgetError(res.status, code, message, Number.isFinite(retry) && retry > 0 ? retry : null)
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let end: number
      while ((end = buffer.indexOf('\n\n')) >= 0) {
        const raw = buffer.slice(0, end)
        buffer = buffer.slice(end + 2)
        const event = /^event: (.*)$/m.exec(raw)?.[1]
        const data = JSON.parse(/^data: (.*)$/m.exec(raw)?.[1] ?? 'null')
        if (event === 'token') handlers.onToken(data.text)
        else if (event === 'citations') handlers.onCitations(data.items)
        else if (event === 'done') handlers.onDone(data)
        else if (event === 'error') throw new WidgetError(503, data.code, data.message)
      }
    }
  }
}

// ------------------------------------------------------------------ dev demo

interface Scripted {
  match: RegExp
  answer: Record<Lang, string>
  citations: WidgetCitation[]
}

const FILE = 'returns-policy.pdf'

const SCRIPT: Scripted[] = [
  {
    match: /return|refund|open|defect|退|開封|瑕疵/i,
    answer: {
      en: 'Opened items can only be returned if they are defective: damaged, spoiled or different from the listing. [1] To start a return, contact support within 7 days with your order number and a photo of the item and its packaging. [2]',
      zh: '開封的商品只有在有瑕疵時才能退貨，例如送達時損壞、變質，或與商品頁不符。[1] 要申請退貨，請在 7 天內聯絡客服，附上訂單編號和商品與包裝的照片。[2]',
    },
    citations: [
      { n: 1, document_title: FILE, page: 1, para: 2 },
      { n: 2, document_title: FILE, page: 1, para: 3 },
    ],
  },
  {
    match: /ship|deliver|express|postage|free|運|寄|配送|免運/i,
    answer: {
      en: 'Orders over $89 ship free with standard shipping. [1] Below that, standard delivery costs $9.95 to metro areas, $12.95 to regional areas and $18.95 to remote areas. [1] Standard shipping takes three to five business days within Australia. [2]',
      zh: '訂單滿 $89 可享標準運送免運費。[1] 未滿時，標準運費為都會區 $9.95、區域 $12.95、偏遠地區 $18.95。[1] 標準運送在澳洲境內需要 3 到 5 個工作天。[2]',
    },
    citations: [
      { n: 1, document_title: FILE, page: 2, para: 1 },
      { n: 2, document_title: FILE, page: 1, para: 4 },
    ],
  },
  {
    match: /kibble|stor|fresh|wet food|飼料|保存|新鮮/i,
    answer: {
      en: 'Keep kibble in a cool, dry place with the bag sealed, and finish an opened bag within six weeks. Wet food goes in the fridge once opened and should be used within three days. [1]',
      zh: '乾飼料請放在陰涼乾燥處並封好袋口，開封後六週內吃完。濕食開封後要冷藏，並在三天內用完。[1]',
    },
    citations: [{ n: 1, document_title: FILE, page: 2, para: 3 }],
  },
  {
    match: /contact|phone|call|email|hours|聯絡|電話|客服/i,
    answer: {
      en: 'Email help@mochipet.example or call 1300 664 244, 9am to 5pm AEST, Monday to Friday. [1]',
      zh: '請寄信到 help@mochipet.example，或在週一到週五上午 9 點到下午 5 點（澳洲東部時間）撥打 1300 664 244。[1]',
    },
    citations: [{ n: 1, document_title: FILE, page: 2, para: 4 }],
  },
]

const NO_ANSWER: Record<Lang, string> = {
  en: "Our documents don't cover this question. Contact us and we'll help.",
  zh: '我們的文件沒有提到這個問題。請聯絡我們，我們會協助你。',
}

/** The demo allows 4 questions a minute so the limit is easy to reach; the backend allows 10. */
const DEMO_LIMIT = 4

function demoAsker(aid: string, lang: Lang): Asker {
  const asked: number[] = []
  return async (question, handlers, signal) => {
    const now = Date.now()
    while (asked.length && asked[0]! <= now - 60_000) asked.shift()
    if (asked.length >= DEMO_LIMIT) {
      throw new WidgetError(429, 'RATE_LIMITED', 'Too many questions', Math.ceil((asked[0]! + 60_000 - now) / 1000))
    }
    asked.push(now)
    await wait(650, signal)
    const q = question.trim().toLowerCase()
    if (q === '/error') throw new WidgetError(503, 'UPSTREAM_UNAVAILABLE', 'The model is busy')
    if (q === '/quota' || aid === 'demo-quota') throw new WidgetError(403, 'QUOTA_EXCEEDED', 'No answers left this month')
    const hit = SCRIPT.find((s) => s.match.test(question))
    if (!hit) {
      handlers.onCitations([])
      handlers.onDone({ answered: false, fallback: { contact: 'help@mochipet.example', message: NO_ANSWER[lang] } })
      return
    }
    for (const piece of hit.answer[lang].match(lang === 'zh' ? /.{1,3}/gsu : /\S+\s*/g) ?? []) {
      await wait(28, signal)
      handlers.onToken(piece)
    }
    handlers.onCitations(hit.citations)
    handlers.onDone({ answered: true, fallback: null })
  }
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const id = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(id)
      reject(new DOMException('Aborted', 'AbortError'))
    })
  })
}
