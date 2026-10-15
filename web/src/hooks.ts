import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { api, type DocStatus } from './api'
import { auth } from './auth'

const ACTIVE: DocStatus[] = ['awaiting_upload', 'parsing', 'embedding', 'deleting']
export const isActive = (status: DocStatus) => ACTIVE.includes(status)

export const keys = {
  me: ['me'] as const,
  assistants: ['assistants'] as const,
  assistant: (aid: string) => ['assistant', aid] as const,
  documents: (aid: string) => ['documents', aid] as const,
  document: (did: string) => ['document', did] as const,
  passages: (did: string) => ['passages', did] as const,
  page: (did: string, page: number) => ['page', did, page] as const,
  jobs: ['jobs'] as const,
}

export const useMe = () => useQuery({ queryKey: keys.me, queryFn: api.me })

export const useAssistants = () =>
  useQuery({
    queryKey: keys.assistants,
    queryFn: api.assistants,
    refetchInterval: (q) => (q.state.data?.some((a) => a.status === 'processing') ? 3000 : false),
  })

export const useAssistant = (aid: string) => useQuery({ queryKey: keys.assistant(aid), queryFn: () => api.assistant(aid) })

export const useDocuments = (aid: string) =>
  useQuery({
    queryKey: keys.documents(aid),
    queryFn: () => api.documents(aid),
    refetchInterval: (q) => (q.state.data?.some((d) => isActive(d.status)) ? 2000 : false),
  })

/** Polls every 2 s while the document is being read or embedded (api-design.md §1 解析進度). */
export const useDocument = (did: string | null) =>
  useQuery({
    queryKey: keys.document(did ?? ''),
    queryFn: () => api.document(did!),
    enabled: !!did,
    refetchInterval: (q) => (q.state.data && isActive(q.state.data.status) ? 2000 : false),
  })

export const usePassages = (did: string | null) =>
  useQuery({ queryKey: keys.passages(did ?? ''), queryFn: () => api.passages(did!), enabled: !!did })

export const usePage = (did: string | null, page: number) =>
  useQuery({
    queryKey: keys.page(did ?? '', page),
    queryFn: () => api.pages(did!, page, page).then((items) => items[0] ?? null),
    enabled: !!did && page > 0,
    staleTime: 5 * 60_000,
  })

export const useJobs = () => useQuery({ queryKey: keys.jobs, queryFn: api.jobs, refetchInterval: 5000 })

/** Seconds since an ISO timestamp, ticking once a second. */
export function useElapsed(since: string | null | undefined): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!since) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [since])
  return since ? Math.max(0, Math.floor((now - Date.parse(since)) / 1000)) : 0
}

export function clock(seconds: number): string {
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}

/** Sets the browser tab title: "Page · RAGcat". */
export function useDocumentTitle(title: string | null | undefined) {
  useEffect(() => {
    document.title = title ? `${title} · RAGcat` : 'RAGcat'
  }, [title])
}

/** Signs out, forgets every cached response, and leaves for the landing page. */
export function useSignOut(): () => void {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  return () => {
    queryClient.clear()
    void auth.signOut()
    navigate('/')
  }
}
