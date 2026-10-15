// Typed client for the RAGcat API (docs/api-design.md).
import { authHeader } from './auth'

// ------------------------------------------------------------------ types

export type AssistantStatus = 'empty' | 'processing' | 'needs_review' | 'ready' | 'live'
export type DocStatus = 'awaiting_upload' | 'parsing' | 'review' | 'embedding' | 'ready' | 'failed' | 'cancelled' | 'deleting'
export type Stage = 'checking_file' | 'reading_pages' | 'describing_figures' | 'organizing_passages' | 'embedding'

export interface Progress {
  stage: Stage
  done: number
  total: number
  started_at: string
}

export interface Me {
  id: string
  email: string
  name: string
  plan: string
  usage: { period_start: string; pages_read: number; pages_limit: number; answers: number; answers_limit: number }
}

export interface Assistant {
  id: string
  label: string
  name: string
  fallback_contact: string
  status: AssistantStatus
  published: boolean
  document_count: number
  pending_changes: number
  content_version: number
  processing: Progress | null
  created_at: string
  updated_at: string
}

export interface Doc {
  id: string
  assistant_id: string
  filename: string
  size_bytes: number
  page_count: number | null
  status: DocStatus
  progress: Progress | null
  enabled: boolean
  edit_version: number
  pending_changes: number
  warning_count: number
  error: { code: string; message: string } | null
  last_embedded_at: string | null
  created_at: string
  updated_at: string
}

export interface Box {
  page: number
  x0: number
  y0: number
  x1: number
  y1: number
}

export interface Passage {
  id: string
  label: string
  document_id: string
  text: string
  original_text: string | null
  origin: 'auto' | 'edited' | 'merged' | 'split' | 'added'
  source: { page_start: number; page_end: number; para_start: number | null; para_end: number | null; boxes: Box[] }
  warnings: { code: string; message: string }[]
  token_count: number
  embedded: boolean
  context: string | null
  updated_at: string
}

export interface Counts {
  all: number
  warnings: number
  edited: number
  pending: number
  removed: number
}

export interface PassageList {
  items: Passage[]
  edit_version: number
  counts: Counts
}

export interface ChangeSet {
  edit_version: number
  upserted: Passage[]
  deleted: string[]
  document: { status: DocStatus; warning_count: number; pending_changes: number }
}

export interface PageImage {
  page: number
  width_pt: number
  height_pt: number
  image_url: string
}

export interface Upload {
  method: 'POST'
  url: string
  fields: Record<string, string>
  expires_at: string
}

export interface Citation {
  n: number
  chunk_id: string
  label: string
  document_id: string
  document_title: string
  page: number
  para: number
  boxes: Box[]
  edited: boolean
}

export interface Job {
  type: 'parse' | 'embed'
  assistant_id: string
  document_id: string
  filename: string
  progress: Progress | null
}

// ------------------------------------------------------------------ transport

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message)
  }
}

async function toError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json()
    return new ApiError(res.status, body.error?.code ?? 'ERROR', body.error?.message ?? res.statusText, body.error?.details ?? {})
  } catch {
    return new ApiError(res.status, 'ERROR', res.statusText)
  }
}

async function request<T>(method: string, path: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { ...await authHeader(), ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...headers },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  })
  if (!res.ok) throw await toError(res)
  return (res.status === 204 ? undefined : await res.json()) as T
}

const ifMatch = (version: number) => ({ 'If-Match': `"${version}"` })

// ------------------------------------------------------------------ endpoints

export const api = {
  me: () => request<Me>('GET', '/v1/me'),

  assistants: () => request<{ items: Assistant[] }>('GET', '/v1/assistants').then((r) => r.items),
  assistant: (aid: string) => request<Assistant>('GET', `/v1/assistants/${aid}`),
  createAssistant: (name: string, fallback_contact = '') => request<Assistant>('POST', '/v1/assistants', { name, fallback_contact }),
  updateAssistant: (aid: string, patch: Partial<Pick<Assistant, 'name' | 'fallback_contact' | 'published'>>) =>
    request<Assistant>('PATCH', `/v1/assistants/${aid}`, patch),

  documents: (aid: string) => request<{ items: Doc[] }>('GET', `/v1/assistants/${aid}/documents`).then((r) => r.items),
  createDocument: (aid: string, file: File) =>
    request<{ document: Doc; upload: Upload }>('POST', `/v1/assistants/${aid}/documents`, {
      filename: file.name,
      size_bytes: file.size,
      content_type: 'application/pdf',
    }),
  document: (did: string) => request<Doc>('GET', `/v1/documents/${did}`),
  setEnabled: (did: string, enabled: boolean) => request<Doc>('PATCH', `/v1/documents/${did}`, { enabled }),
  deleteDocument: (did: string) => request<unknown>('DELETE', `/v1/documents/${did}`),
  cancel: (did: string) => request<Doc>('POST', `/v1/documents/${did}/cancel`),
  pages: (did: string, from: number, to: number) =>
    request<{ items: PageImage[] }>('GET', `/v1/documents/${did}/pages?from=${from}&to=${to}`).then((r) => r.items),
  embed: (did: string) => request<{ job: { id: string } }>('POST', `/v1/documents/${did}/embed`),
  jobs: () => request<{ items: Job[] }>('GET', '/v1/jobs?state=active').then((r) => r.items),

  passages: (did: string) => request<PassageList>('GET', `/v1/documents/${did}/chunks`),
  editPassage: (did: string, v: number, cid: string, text: string) =>
    request<ChangeSet>('PATCH', `/v1/documents/${did}/chunks/${cid}`, { text }, ifMatch(v)),
  addPassage: (did: string, v: number, after_id: string | null, text: string) =>
    request<ChangeSet>('POST', `/v1/documents/${did}/chunks`, { after_id, text }, ifMatch(v)),
  deletePassage: (did: string, v: number, cid: string) => request<ChangeSet>('DELETE', `/v1/documents/${did}/chunks/${cid}`, undefined, ifMatch(v)),
  splitPassage: (did: string, v: number, cid: string, parts: string[]) =>
    request<ChangeSet>('POST', `/v1/documents/${did}/chunks/${cid}/split`, { parts }, ifMatch(v)),
  mergePassages: (did: string, v: number, ids: string[]) => request<ChangeSet>('POST', `/v1/documents/${did}/chunks/merge`, { ids }, ifMatch(v)),
  restorePassage: (did: string, v: number, cid: string) =>
    request<ChangeSet>('POST', `/v1/documents/${did}/chunks/${cid}/restore`, undefined, ifMatch(v)),
}

/** Browser → object store with the presigned POST; XHR because fetch has no upload progress. */
export function uploadFile(upload: Upload, file: File, onProgress: (fraction: number) => void, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    Object.entries(upload.fields).forEach(([k, v]) => form.append(k, v))
    form.append('file', file)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', upload.url)
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
    xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new ApiError(xhr.status, 'UPLOAD_FAILED', 'Upload failed')))
    xhr.onerror = () => reject(new ApiError(0, 'UPLOAD_FAILED', 'Network error during upload'))
    xhr.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'))
    signal?.addEventListener('abort', () => xhr.abort())
    xhr.send(form)
  })
}

// ------------------------------------------------------------------ ask (SSE over POST)

export interface AskHandlers {
  onMeta?: (meta: { request_id: string; content_version: number; cached: boolean; preview: boolean }) => void
  /** Preview only: unpublished Passages being embedded before the answer. */
  onPreparing?: (progress: { done: number; total: number }) => void
  onToken: (text: string) => void
  onCitations: (items: Citation[]) => void
  onDone: (done: { answered: boolean; fallback: { contact: string; message: string } | null; latency_ms: number }) => void
}

/** `preview`: the owner's unpublished edits answer too (customers keep the published version). */
export async function ask(aid: string, question: string, handlers: AskHandlers, { preview = false, signal }: { preview?: boolean; signal?: AbortSignal } = {}): Promise<void> {
  const res = await fetch(`/v1/assistants/${aid}/ask`, {
    method: 'POST',
    headers: { ...await authHeader(), 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ question, stream: true, preview }),
    ...(signal ? { signal } : {}),
  })
  if (!res.ok || !res.body) throw await toError(res)
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
      if (event === 'meta') handlers.onMeta?.(data)
      else if (event === 'preparing') handlers.onPreparing?.(data)
      else if (event === 'token') handlers.onToken(data.text)
      else if (event === 'citations') handlers.onCitations(data.items)
      else if (event === 'done') handlers.onDone(data)
      else if (event === 'error') throw new ApiError(503, data.code, data.message)
    }
  }
}
