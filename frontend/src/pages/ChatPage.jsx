import { useState, useEffect, useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  MessageCircle,
  Plus,
  Trash2,
  ChevronDown,
  Check,
  Loader2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { UserMessage, AssistantMessage, ModelDivider, EmptyState } from '@/components/chat/ChatMessages'
import ChatInput from '@/components/chat/ChatInput'
import { useChatStream } from '@/hooks/useChatStream'
import {
  useConversations,
  useUpsertConversation,
  useDeleteConversation,
  queryKeys,
} from '@/hooks/useApi'
import { authHeaders, chatHistoryApi } from '@/services/api'
import { createConversation, generateTitle } from '@/lib/conversations'

const DEFAULT_MODEL = 'claude-haiku-4-5-20251001'

function formatRelativeTime(isoString) {
  const diff = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

// ChatArea is a separate component so key={conversationId} remounts it (and useChatStream)
// when the active conversation changes, resetting all in-flight state cleanly.
function ChatArea({
  initialDisplayMessages,
  initialApiMessages,
  model,
  onUpdate,
  modelSwitchMessage,
  onModelSwitchApplied,
}) {
  const { displayMessages, setDisplayMessages, apiMessages, isStreaming, sendMessage } = useChatStream({
    model,
    initialDisplayMessages,
    initialApiMessages,
  })

  const messagesEndRef = useRef(null)
  const isFirstRun = useRef(true)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [displayMessages])

  // Insert model switch divider and persist immediately (isStreaming doesn't change here)
  useEffect(() => {
    if (!modelSwitchMessage) return
    if (displayMessages.length === 0) return
    const dividerMsg = { id: `divider-${Date.now()}`, role: 'divider', content: modelSwitchMessage }
    const newDisplay = [...displayMessages, dividerMsg]
    setDisplayMessages(newDisplay)
    onUpdate(newDisplay, apiMessages)
    onModelSwitchApplied()
  }, [modelSwitchMessage])

  // Save when streaming ends (skip the initial mount run)
  useEffect(() => {
    if (isFirstRun.current) {
      isFirstRun.current = false
      return
    }
    if (!isStreaming && displayMessages.length > 0) {
      // Strip in-flight isStreaming flag before persisting
      const clean = displayMessages.map((m) =>
        m.isStreaming ? { ...m, isStreaming: false } : m
      )
      onUpdate(clean, apiMessages)
    }
  }, [isStreaming])

  // Called by ChatInput and EmptyState prompt clicks
  const handleSend = useCallback(
    (displayContent, apiContent, pillPreviews) => {
      const trimmed = typeof displayContent === 'string' ? displayContent.trim() : ''
      if (!trimmed || isStreaming) return
      sendMessage(trimmed, apiContent, pillPreviews)
    },
    [isStreaming, sendMessage]
  )

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {displayMessages.length === 0 ? (
          <div className="mx-auto max-w-3xl">
            <EmptyState onPromptClick={handleSend} isStreaming={isStreaming} />
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-4">
            {displayMessages.map((msg) => {
              if (msg.role === 'user') return <UserMessage key={msg.id} content={msg.content} pillPreviews={msg.pillPreviews} />
              if (msg.role === 'divider') return <ModelDivider key={msg.id} content={msg.content} />
              return <AssistantMessage key={msg.id} message={msg} />
            })}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-border px-6 py-4">
        <div className="mx-auto max-w-3xl">
          <ChatInput onSend={handleSend} isStreaming={isStreaming} maxHeight={160} />
        </div>
      </div>
    </div>
  )
}

export default function ChatPage() {
  const qc = useQueryClient()
  // Server-persisted conversations (R2.6). `conversations` is the local working
  // list: summary fields from the server, plus a `displayMessages`/`apiMessages`
  // pair that is `undefined` until the conversation is opened (loaded on
  // select), and an in-memory unsaved conversation that isn't on the server yet.
  const { data: serverConversations } = useConversations()
  const upsertMutation = useUpsertConversation()
  const deleteMutation = useDeleteConversation()

  const [conversations, setConversations] = useState([])
  const [activeConversationId, setActiveConversationId] = useState(null)
  const [model, setModel] = useState(DEFAULT_MODEL)
  const [providers, setProviders] = useState(null)
  const [showModelMenu, setShowModelMenu] = useState(false)
  const [modelSwitchMessage, setModelSwitchMessage] = useState(null)
  const [deleteConfirm, setDeleteConfirm] = useState(null)
  // id of a conversation that exists only in memory (not yet written to the
  // server) because the user hasn't sent a message in it yet.
  const [unsavedId, setUnsavedId] = useState(null)
  const didAutoSelect = useRef(false)

  const activeConv = conversations.find((c) => c.id === activeConversationId) ?? null

  // Fetch a conversation's full message arrays and merge them into local state.
  // Idempotently upserts the entry (so it works whether or not the merge effect
  // has added the summary row yet).
  const loadMessages = useCallback(
    async (id) => {
      const full = await qc.fetchQuery({
        queryKey: queryKeys.conversation(id),
        queryFn: () => chatHistoryApi.get(id),
      })
      setConversations((prev) => {
        const entry = {
          id,
          title: full.title,
          model: full.model ?? DEFAULT_MODEL,
          updatedAt: full.updated_at,
          displayMessages: full.display_messages ?? [],
          apiMessages: full.api_messages ?? [],
        }
        const idx = prev.findIndex((c) => c.id === id)
        if (idx === -1) return [...prev, entry]
        return prev.map((c) => (c.id === id ? { ...c, ...entry } : c))
      })
    },
    [qc]
  )

  // Merge the server summary list into local state, preserving any messages
  // already loaded and any in-memory unsaved conversation (absent from server).
  useEffect(() => {
    if (!serverConversations) return
    setConversations((prev) => {
      const prevById = new Map(prev.map((c) => [c.id, c]))
      const fromServer = serverConversations.map((s) => {
        const existing = prevById.get(s.id)
        return {
          id: s.id,
          title: s.title,
          model: s.model ?? DEFAULT_MODEL,
          updatedAt: s.updated_at,
          displayMessages: existing?.displayMessages,
          apiMessages: existing?.apiMessages,
        }
      })
      const localOnly = prev.filter(
        (c) => !serverConversations.some((s) => s.id === c.id)
      )
      return [...localOnly, ...fromServer]
    })
  }, [serverConversations])

  // Once the server list has loaded, auto-select the newest conversation (or a
  // drawer handoff) — exactly once.
  useEffect(() => {
    if (didAutoSelect.current) return
    if (!serverConversations) return
    didAutoSelect.current = true

    const handoffRaw = sessionStorage.getItem('son-of-anton:drawer-handoff')
    if (handoffRaw) {
      sessionStorage.removeItem('son-of-anton:drawer-handoff')
      try {
        const { displayMessages, apiMessages } = JSON.parse(handoffRaw)
        const conv = createConversation(model)
        const firstUser = displayMessages.find((m) => m.role === 'user')
        if (firstUser) conv.title = generateTitle(firstUser.content)
        conv.displayMessages = displayMessages
        conv.apiMessages = apiMessages
        setConversations((prev) => [conv, ...prev])
        setActiveConversationId(conv.id)
        // Persist the handoff conversation immediately (it already has messages).
        upsertMutation.mutate({
          id: conv.id,
          title: conv.title,
          model: conv.model,
          display_messages: displayMessages,
          api_messages: apiMessages,
        })
        return
      } catch {
        // Fall through to normal auto-select
      }
    }

    if (serverConversations.length > 0) {
      const first = serverConversations[0]
      setActiveConversationId(first.id)
      setModel(first.model ?? DEFAULT_MODEL)
      loadMessages(first.id)
    }
  }, [serverConversations, model, loadMessages, upsertMutation])

  // Fetch provider/model list
  useEffect(() => {
    fetch('/api/chat/providers', { headers: authHeaders() })
      .then((r) => r.json())
      .then(setProviders)
      .catch(() => {})
  }, [])

  // Drops the current unsaved-empty conversation (if any) from in-memory state
  // — used whenever we're about to navigate away from it. Nothing was ever
  // persisted, so there's no server call.
  const discardUnsavedIfEmpty = useCallback(() => {
    if (!unsavedId) return
    setConversations((prev) => {
      const conv = prev.find((c) => c.id === unsavedId)
      if (conv && (conv.displayMessages?.length ?? 0) === 0) {
        return prev.filter((c) => c.id !== unsavedId)
      }
      return prev
    })
    setUnsavedId(null)
  }, [unsavedId])

  const handleNewConversation = () => {
    discardUnsavedIfEmpty()
    const conv = createConversation(model)
    // Held in memory only — NOT persisted to the server until the first message
    // is sent (see handleMessagesUpdate).
    setConversations((prev) => [conv, ...prev])
    setActiveConversationId(conv.id)
    setUnsavedId(conv.id)
    setModelSwitchMessage(null)
  }

  const handleSelectConversation = (id) => {
    if (id === activeConversationId) return
    discardUnsavedIfEmpty()
    setActiveConversationId(id)
    const conv = conversations.find((c) => c.id === id)
    if (conv?.model) setModel(conv.model)
    if (conv && conv.displayMessages === undefined) loadMessages(id)
    setModelSwitchMessage(null)
    setDeleteConfirm(null)
  }

  const handleDeleteConversation = (id) => {
    setConversations((prev) => {
      const updated = prev.filter((c) => c.id !== id)
      if (id === activeConversationId) {
        setActiveConversationId(updated.length > 0 ? updated[0].id : null)
      }
      return updated
    })
    // Only the never-persisted (unsaved) conversation skips the server delete.
    if (id === unsavedId) setUnsavedId(null)
    else deleteMutation.mutate(id)
    setDeleteConfirm(null)
  }

  // Called by ChatArea when streaming ends; persists the updated messages to
  // the server. This is also the moment an unsaved (brand-new) conversation
  // gets written for the first time.
  const handleMessagesUpdate = useCallback(
    (displayMessages, apiMessages) => {
      if (!activeConversationId) return
      const conv = conversations.find((c) => c.id === activeConversationId)
      if (!conv) return
      let title = conv.title
      if (!title) {
        const firstUser = displayMessages.find((m) => m.role === 'user')
        if (firstUser) title = generateTitle(firstUser.content)
      }
      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeConversationId
            ? { ...c, displayMessages, apiMessages, title, updatedAt: new Date().toISOString() }
            : c
        )
      )
      upsertMutation.mutate({
        id: activeConversationId,
        title,
        model: conv.model,
        display_messages: displayMessages,
        api_messages: apiMessages,
      })
      if (activeConversationId === unsavedId) setUnsavedId(null)
    },
    [activeConversationId, conversations, unsavedId, upsertMutation]
  )

  const getModelName = (modelId) => {
    if (!providers) return modelId
    for (const p of Object.values(providers.providers ?? {})) {
      const found = p.models?.find((m) => m.id === modelId)
      if (found) return found.name
    }
    return modelId
  }

  const handleModelChange = (newModelId) => {
    setShowModelMenu(false)
    if (newModelId === model) return
    setModelSwitchMessage(`── Switched to ${getModelName(newModelId)} ──`)
    setModel(newModelId)
    if (!activeConversationId) return
    setConversations((prev) =>
      prev.map((c) => (c.id === activeConversationId ? { ...c, model: newModelId } : c))
    )
    // Persist the model change on an already-saved conversation so it survives
    // a reload even if no further message is sent. An unsaved/empty conversation
    // just updates in memory (it persists on its first message).
    const conv = conversations.find((c) => c.id === activeConversationId)
    if (conv && conv.id !== unsavedId && conv.displayMessages !== undefined) {
      upsertMutation.mutate({
        id: conv.id,
        title: conv.title,
        model: newModelId,
        display_messages: conv.displayMessages,
        api_messages: conv.apiMessages,
      })
    }
  }

  return (
    <div className="flex h-screen bg-background">
      {/* ── Conversation list panel — lives inside the main content area,
          to the right of the app sidebar (rendered by Layout) ── */}
      <aside className="flex w-[280px] shrink-0 flex-col border-r border-border bg-sidebar">
        {/* New conversation */}
        <div className="px-3 pt-3 pb-1">
          <button
            onClick={handleNewConversation}
            className="flex w-full items-center gap-2 rounded-[9px] px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <Plus className="h-4 w-4 shrink-0" />
            New conversation
          </button>
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto px-3 py-1 space-y-px">
          {conversations.length === 0 ? (
            <p className="px-3 py-3 text-xs text-faint">No conversations yet</p>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                role="button"
                tabIndex={0}
                onClick={() => handleSelectConversation(conv.id)}
                onKeyDown={(e) => e.key === 'Enter' && handleSelectConversation(conv.id)}
                className={cn(
                  'group relative flex items-start gap-2 rounded-[9px] px-3 py-2 cursor-pointer transition-colors select-none',
                  conv.id === activeConversationId
                    ? 'bg-accent text-accent-foreground'
                    : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                )}
              >
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium truncate leading-snug">
                    {conv.title ?? 'New conversation'}
                  </p>
                  <p className="text-[10px] text-faint mt-0.5">
                    {formatRelativeTime(conv.updatedAt)}
                  </p>
                </div>

                {/* Delete button / confirm */}
                {deleteConfirm === conv.id ? (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      handleDeleteConversation(conv.id)
                    }}
                    className="shrink-0 rounded p-0.5 text-red-400 hover:text-red-300 transition-colors"
                    aria-label="Confirm delete"
                  >
                    <Check className="h-3 w-3" />
                  </button>
                ) : (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setDeleteConfirm(conv.id)
                    }}
                    className="shrink-0 rounded p-0.5 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-foreground transition-opacity"
                    aria-label="Delete conversation"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                )}
              </div>
            ))
          )}
        </div>

        {/* Current model indicator */}
        <div className="border-t border-border px-4 py-3">
          <p className="text-[10px] text-faint truncate">{getModelName(model)}</p>
        </div>
      </aside>

      {/* ── Main area ── */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-3">
          <span className="font-semibold text-foreground">Son of Anton</span>

          <div className="flex items-center gap-2">
            {/* Model selector */}
            <div className="relative">
              <button
                onClick={() => setShowModelMenu((v) => !v)}
                className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                {getModelName(model)}
                <ChevronDown className="h-3 w-3 shrink-0" />
              </button>

              {showModelMenu && (
                <>
                  {/* Click-away overlay */}
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setShowModelMenu(false)}
                  />
                  <div className="absolute right-0 top-full mt-1 z-20 w-60 rounded-[10px] border border-border bg-sidebar py-1 shadow-xl">
                    {providers &&
                      Object.entries(providers.providers ?? {}).map(([key, provider]) => (
                        <div key={key}>
                          <div className="flex items-center gap-2 px-3 py-1.5">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-faint">
                              {provider.name}
                            </span>
                            {!provider.available && (
                              <span className="text-[9px] text-faint border border-border rounded px-1 py-0.5">
                                no key
                              </span>
                            )}
                          </div>
                          {(provider.models ?? []).map((m) => (
                            <button
                              key={m.id}
                              onClick={() => provider.available && handleModelChange(m.id)}
                              disabled={!provider.available}
                              className={cn(
                                'flex w-full items-center gap-2 px-3 py-2 text-sm transition-colors',
                                !provider.available
                                  ? 'text-muted-foreground/40 cursor-not-allowed'
                                  : m.id === model
                                  ? 'text-foreground bg-accent/40'
                                  : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                              )}
                            >
                              <span className="w-3.5 shrink-0">
                                {m.id === model && provider.available && (
                                  <Check className="h-3 w-3 text-primary" />
                                )}
                              </span>
                              <span className="flex-1 text-left">{m.name}</span>
                              <span className="text-[10px] text-faint">{m.description}</span>
                            </button>
                          ))}
                        </div>
                      ))}
                  </div>
                </>
              )}
            </div>

            {/* New conversation shortcut */}
            <button
              onClick={handleNewConversation}
              className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              <Plus className="h-3 w-3 shrink-0" />
              New
            </button>
          </div>
        </header>

        {/* Chat area — keyed so useChatStream resets on conversation change.
            While a selected conversation's messages are still loading, show a
            spinner rather than mounting ChatArea with an empty history. */}
        {activeConversationId && activeConv && activeConv.displayMessages !== undefined ? (
          <ChatArea
            key={activeConversationId}
            initialDisplayMessages={activeConv.displayMessages}
            initialApiMessages={activeConv.apiMessages}
            model={model}
            onUpdate={handleMessagesUpdate}
            modelSwitchMessage={modelSwitchMessage}
            onModelSwitchApplied={() => setModelSwitchMessage(null)}
          />
        ) : activeConversationId ? (
          <div className="flex flex-1 items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/40" />
          </div>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
            <MessageCircle className="h-10 w-10 text-muted-foreground/20" />
            <div>
              <p className="text-sm font-medium text-foreground">No conversation selected</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Start a new conversation to begin
              </p>
            </div>
            <button
              onClick={handleNewConversation}
              className="flex items-center gap-2 rounded-[10px] bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              <Plus className="h-4 w-4" />
              New conversation
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
