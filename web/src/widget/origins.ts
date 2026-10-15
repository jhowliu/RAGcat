// The Website widget's domain list (docs/api-design.md §7). Owners paste whatever they have, such as
// "mochipet.example" or a full page URL; we keep only its origin. https only, except localhost so an
// owner can try the widget on their own machine. The backend validates the same rules again.

export const MAX_ORIGINS = 10

export type OriginError = 'empty' | 'invalid' | 'wildcard' | 'insecure' | 'duplicate' | 'limit'

export type OriginResult = { ok: true; origin: string } | { ok: false; error: OriginError }

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]'])

export function parseOrigin(input: string): OriginResult {
  const text = input.trim()
  if (!text) return { ok: false, error: 'empty' }
  if (text.includes('*')) return { ok: false, error: 'wildcard' }
  // No scheme: assume https, or http for this machine (`localhost:5173`).
  const bare = !/^[a-z][a-z0-9+.-]*:\/\//i.test(text)
  const local = /^(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/i.test(text)
  let url: URL
  try {
    url = new URL(bare ? `${local ? 'http' : 'https'}://${text}` : text)
  } catch {
    return { ok: false, error: 'invalid' }
  }
  const isLocal = LOCAL_HOSTS.has(url.hostname)
  if (!isLocal && !/^[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(url.hostname)) return { ok: false, error: 'invalid' }
  if (url.protocol === 'http:' && !isLocal) return { ok: false, error: 'insecure' }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return { ok: false, error: 'invalid' }
  return { ok: true, origin: url.origin }
}

/** The list with `input` added, or why it can't be. */
export function addOrigin(list: readonly string[], input: string): { ok: true; origins: string[]; origin: string } | { ok: false; error: OriginError } {
  const parsed = parseOrigin(input)
  if (!parsed.ok) return parsed
  if (list.includes(parsed.origin)) return { ok: false, error: 'duplicate' }
  if (list.length >= MAX_ORIGINS) return { ok: false, error: 'limit' }
  return { ok: true, origins: [...list, parsed.origin], origin: parsed.origin }
}

/** The one line an owner pastes before </body>. */
export function embedSnippet(base: string, aid: string): string {
  return `<script src="${base}/widget.js" data-assistant="${aid}" async></script>`
}
