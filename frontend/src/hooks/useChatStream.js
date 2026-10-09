import { useState, useCallback, useRef } from 'react'
import { authHeaders } from '@/services/api'
import { useToast } from '@/components/ui/toast'

const DEFAULT_MODEL = 'claude-haiku-4-5-20251001'

function updateLast(messages, updater) {
  if (!messages.length) return messages
  const next = [...messages]
  next[next.length - 1] = updater(next[next.length - 1])
  return next
}

export function useChatStream({
  model = DEFAULT_MODEL,
  initialDisplayMessages = [],
  initialApiMessages = [],
} = {}) {
  const [displayMessages, setDisplayMessages] = useState(initialDisplayMessages)
  const [apiMessages, setApiMessages] = useState(initialApiMessages)
  const [isStreaming, setIsStreaming] = useState(false)
  const { toast } = useToast()
  // Aborts the in-flight SSE fetch when the user taps Stop. Closing the
  // connection is the whole protocol: the backend stops streaming on client
  // disconnect, and whatever text already arrived is kept as the reply.
  const abortRef = useRef(null)

  const stop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const insertDivider = useCallback((content) => {
    setDisplayMessages((prev) => [
      ...prev,
      { id: `divider-${Date.now()}`, role: 'divider', content },
    ])
  }, [])

  // One streamed turn. `userMsg` is the bubble to show, or null for a hidden
  // turn — the confirmation-card follow-up, where the runner's decision goes
  // to the model as text but the thread shows the card, not a message.
  const runTurn = useCallback(
    async ({ userMsg, apiBody }) => {
      // RA2.2 §4 — chat send is a write over fetch() (not axios), so it bypasses
      // the api.js write-guard; block it here when offline rather than posting
      // into the void. Mirrors the "writes require connectivity" boundary.
      if (typeof navigator !== 'undefined' && navigator.onLine === false) {
        toast({
          variant: 'destructive',
          title: "You're offline",
          description: 'Sending a message needs a connection.',
        })
        return
      }

      const timestamp = new Date().toISOString()
      const assistantMsg = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: '',
        toolIndicators: [],
        isStreaming: true,
        timestamp,
      }

      const added = userMsg ? [userMsg, assistantMsg] : [assistantMsg]
      const updatedApiMessages = [...apiMessages, { role: 'user', content: apiBody }]
      setDisplayMessages((prev) => [...prev, ...added])
      setApiMessages(updatedApiMessages)
      setIsStreaming(true)

      let fullContent = ''
      // Held write calls end the turn with no tool result. Record what was
      // proposed in the model's history, since the card itself isn't text.
      const proposalNotes = []
      const controller = new AbortController()
      abortRef.current = controller

      try {
        const res = await fetch('/api/chat/message', {
          signal: controller.signal,
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders() },
          // RA2.1: send the httpOnly session cookie with the SSE POST.
          credentials: 'include',
          body: JSON.stringify({ messages: updatedApiMessages, model }),
        })

        if (!res.ok) {
          if (res.status === 429) {
            const retryAfter = res.headers.get('Retry-After')
            const description = retryAfter
              ? `Too many messages — wait ${retryAfter}s before trying again.`
              : 'Too many messages — please wait before trying again.'
            toast({ variant: 'destructive', title: 'Rate limit reached', description })
            // Roll back the optimistic user + assistant messages so the thread
            // is clean for retry.
            setDisplayMessages((prev) => prev.slice(0, -added.length))
            setApiMessages(apiMessages)
            return
          }
          const errData = await res.json().catch(() => ({}))
          throw new Error(errData.detail || `Request failed (${res.status})`)
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        outer: while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const parts = buffer.split(/\r?\n\r?\n/)
          buffer = parts.pop() ?? ''

          for (const part of parts) {
            for (const line of part.split(/\r?\n/)) {
              if (!line.startsWith('data: ')) continue
              const raw = line.slice(6).trim()
              if (!raw) continue

              let event
              try {
                event = JSON.parse(raw)
              } catch {
                continue
              }

              if (event.type === 'text') {
                fullContent += event.content
                setDisplayMessages((prev) =>
                  updateLast(prev, (m) => ({ ...m, content: m.content + event.content }))
                )
              } else if (event.type === 'tool_call') {
                setDisplayMessages((prev) =>
                  updateLast(prev, (m) => ({
                    ...m,
                    toolIndicators: [
                      ...m.toolIndicators,
                      { id: `${event.tool}-${Date.now()}`, tool: event.tool, status: 'calling' },
                    ],
                  }))
                )
              } else if (event.type === 'tool_result') {
                setDisplayMessages((prev) =>
                  updateLast(prev, (m) => {
                    const indicators = [...m.toolIndicators]
                    for (let i = indicators.length - 1; i >= 0; i--) {
                      if (indicators[i].tool === event.tool && indicators[i].status === 'calling') {
                        indicators[i] = { ...indicators[i], status: event.success ? 'done' : 'error' }
                        break
                      }
                    }
                    return { ...m, toolIndicators: indicators }
                  })
                )
              } else if (event.type === 'proposal') {
                // R7.2: a write call held for the runner. The card replaces the
                // tool's spinning indicator; nothing has run yet.
                const proposal = event.proposal
                proposalNotes.push(proposal.transcript_note)
                setDisplayMessages((prev) =>
                  updateLast(prev, (m) => {
                    const indicators = [...m.toolIndicators]
                    for (let i = indicators.length - 1; i >= 0; i--) {
                      if (indicators[i].tool === proposal.tool && indicators[i].status === 'calling') {
                        indicators.splice(i, 1)
                        break
                      }
                    }
                    return {
                      ...m,
                      toolIndicators: indicators,
                      proposals: [...(m.proposals ?? []), proposal],
                    }
                  })
                )
              } else if (event.type === 'error') {
                setDisplayMessages((prev) =>
                  updateLast(prev, (m) => ({
                    ...m,
                    content: m.content || `Error: ${event.message}`,
                    isStreaming: false,
                  }))
                )
                break outer
              } else if (event.type === 'done') {
                break outer
              }
            }
          }
        }
      } catch (err) {
        // A user-initiated Stop is not an error: keep the partial reply as-is.
        const stopped = err?.name === 'AbortError'
        setDisplayMessages((prev) =>
          updateLast(prev, (m) => ({
            ...m,
            content: m.content || (stopped ? '_Stopped._' : `Error: ${err.message}`),
            isStreaming: false,
          }))
        )
      } finally {
        abortRef.current = null
        setIsStreaming(false)
        const recorded = [fullContent, ...proposalNotes].filter(Boolean).join('\n\n')
        if (recorded) {
          setApiMessages((prev) => [...prev, { role: 'assistant', content: recorded }])
        }
        setDisplayMessages((prev) => updateLast(prev, (m) => ({ ...m, isStreaming: false })))
      }
    },
    [model, apiMessages, toast]
  )

  const sendMessage = useCallback(
    // apiContent defaults to displayContent when pills are not involved.
    // pillPreviews is an array of {uri, label, content} for display in the thread.
    (displayContent, apiContent, pillPreviews = []) => {
      const content = (typeof displayContent === 'string' ? displayContent : '').trim()
      if (!content || isStreaming) return
      const apiBody = typeof apiContent === 'string' && apiContent.trim() ? apiContent.trim() : content
      const userMsg = {
        id: `u-${Date.now()}`,
        role: 'user',
        content,
        pillPreviews: pillPreviews.length > 0 ? pillPreviews : undefined,
        timestamp: new Date().toISOString(),
      }
      return runTurn({ userMsg, apiBody })
    },
    [isStreaming, runTurn]
  )

  // A card reached a decision (confirmed, cancelled, edited, expired). Store
  // the new state on the message that holds it, then tell the model — the
  // server wrote the follow-up text (chat_proposals.followup_message).
  const resolveProposal = useCallback(
    (updated) => {
      setDisplayMessages((prev) =>
        prev.map((m) =>
          m.proposals?.some((p) => p.id === updated.id)
            ? { ...m, proposals: m.proposals.map((p) => (p.id === updated.id ? { ...p, ...updated } : p)) }
            : m
        )
      )
      if (updated.followup_message && !isStreaming) {
        runTurn({ userMsg: null, apiBody: updated.followup_message })
      }
    },
    [isStreaming, runTurn]
  )

  return {
    displayMessages,
    setDisplayMessages,
    apiMessages,
    isStreaming,
    sendMessage,
    resolveProposal,
    stop,
    insertDivider,
  }
}
