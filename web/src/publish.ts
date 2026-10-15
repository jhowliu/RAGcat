// "Publish changes": embed every switched-on Document whose Passages changed, and make the
// Assistant answer customers. Used by Publish (P06), Assistant overview (P07) and Review.
import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from './api'
import { keys, useAssistant, useDocuments } from './hooks'
import { isPublished, needsPublish } from './model'

export function usePublishChanges(aid: string) {
  const queryClient = useQueryClient()
  const { data: assistant } = useAssistant(aid)
  const { data: docs = [] } = useDocuments(aid)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const goLive = useRef(false)

  const pending = docs.filter(needsPublish)
  const running = docs.filter((d) => d.status === 'embedding')
  const anyPublished = docs.some((d) => d.enabled && isPublished(d))
  const live = !!assistant?.published
  const progress = running.reduce((acc, d) => ({ done: acc.done + (d.progress?.done ?? 0), total: acc.total + (d.progress?.total ?? 0) }), { done: 0, total: 0 })
  const lastPublished = docs.reduce<string | null>((acc, d) => (d.last_embedded_at && (!acc || d.last_embedded_at > acc) ? d.last_embedded_at : acc), null)

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: keys.documents(aid) })
    queryClient.invalidateQueries({ queryKey: keys.assistant(aid) })
    queryClient.invalidateQueries({ queryKey: keys.assistants })
    queryClient.invalidateQueries({ queryKey: keys.jobs })
  }

  async function makeLive() {
    goLive.current = false
    const a = await api.updateAssistant(aid, { published: true })
    queryClient.setQueryData(keys.assistant(aid), a)
    queryClient.invalidateQueries({ queryKey: keys.assistants })
  }

  async function publish() {
    setError(null)
    setStarting(true)
    try {
      await Promise.all(pending.map((d) => api.embed(d.id)))
      // The backend only goes live once something answers; otherwise wait for the first publish.
      if (!live) {
        if (anyPublished) await makeLive()
        else goLive.current = true
      }
      refresh()
    } catch (e) {
      setError(e)
    } finally {
      setStarting(false)
    }
  }

  const wasRunning = useRef(false)
  useEffect(() => {
    if (running.length) {
      wasRunning.current = true
      return
    }
    if (!wasRunning.current) return
    wasRunning.current = false
    refresh()
  }, [running.length])

  useEffect(() => {
    if (goLive.current && !live && anyPublished && !running.length) makeLive().catch(setError)
  }, [live, anyPublished, running.length])

  return {
    assistant,
    docs,
    live,
    pendingCount: pending.length,
    publishing: starting || running.length > 0,
    progress,
    lastPublished,
    /** Something to publish: changed Documents, or a first go-live once a Document is published. */
    canPublish: !starting && running.length === 0 && (pending.length > 0 || (!live && anyPublished)),
    publish,
    error,
  }
}
