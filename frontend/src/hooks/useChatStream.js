import { useState, useCallback } from 'react'
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

  const insertDivider = useCallback((content) => {
    setDisplayMessages((prev) => [
      ...prev,
      { id: `divider-${Date.now()}`, role: 'divider', content },
    ])
  }, [])

  const sendMessage = useCallback(
    // apiContent defaults to displayContent when pills are not involved.
    // pillPreviews is an array of {uri, label, content} for display in the thread.
    async (displayContent, apiContent, pillPreviews = []) => {
      const content = (typeof displayContent === 'string' ? displayContent : '').trim()
      if (!content || isStreaming) return

      const apiBody = typeof apiContent === 'string' && apiContent.trim()
        ? apiContent.trim()
        : content

      const timestamp = new Date().toISOString()
      const userMsg = {
        id: `u-${Date.now()}`,
        role: 'user',
        content,
        pillPreviews: pillPreviews.length > 0 ? pillPreviews : undefined,
        timestamp,
      }
      const assistantMsg = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: '',
        toolIndicators: [],
        isStreaming: true,
        timestamp,
      }

      const updatedApiMessages = [...apiMessages, { role: 'user', content: apiBody }]
      setDisplayMessages((prev) => [...prev, userMsg, assistantMsg])
      setApiMessages(updatedApiMessages)
      setIsStreaming(true)

      let fullContent = ''

      try {
        const res = await fetch('/api/chat/message', {
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
            setDisplayMessages((prev) => prev.slice(0, -2))
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
        setDisplayMessages((prev) =>
          updateLast(prev, (m) => ({
            ...m,
            content: m.content || `Error: ${err.message}`,
            isStreaming: false,
          }))
        )
      } finally {
        setIsStreaming(false)
        if (fullContent) {
          setApiMessages((prev) => [...prev, { role: 'assistant', content: fullContent }])
        }
        setDisplayMessages((prev) => updateLast(prev, (m) => ({ ...m, isStreaming: false })))
      }
    },
    [model, apiMessages, isStreaming, toast]
  )

  return { displayMessages, setDisplayMessages, apiMessages, isStreaming, sendMessage, insertDivider }
}
