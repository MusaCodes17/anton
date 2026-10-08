import { useState, useEffect, useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import {
  MessageCircle,
  Plus,
  Trash2,
  ChevronDown,
  Check,
  Loader2,
  PanelLeft,
  X,
  SquarePen,
  Menu,
  ArrowDown,
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
  const { displayMessages, setDisplayMessages, apiMessages, isStreaming, sendMessage, stop } = useChatStream({
    model,
    initialDisplayMessages,
    initialApiMessages,
  })

  const scrollRef = useRef(null)
  const isFirstRun = useRef(true)
  // Stick-to-bottom: follow the stream only while the reader is already at
  // the bottom. Scrolling up to re-read pauses following and offers a
  // "latest" button instead of yanking the thread back on every token.
  const [atBottom, setAtBottom] = useState(true)
  const atBottomRef = useRef(true)

  const scrollToBottom = useCallback((behavior = 'auto') => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior })
  }, [])

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    atBottomRef.current = near
    setAtBottom(near)
  }

  // 'auto' (instant) while streaming: a smooth scroll per token stutters on
  // phones because each one restarts before the last finishes.
  useEffect(() => {
    if (atBottomRef.current) scrollToBottom('auto')
  }, [displayMessages, scrollToBottom])

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
      // Sending always returns the reader to the bottom to watch the reply.
      atBottomRef.current = true
      setAtBottom(true)
      sendMessage(trimmed, apiContent, pillPreviews)
    },
    [isStreaming, sendMessage]
  )

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {/* Messages */}
      <div className="relative min-h-0 flex-1">
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="h-full overflow-y-auto overscroll-contain px-4 py-4 md:px-6"
        >
          {displayMessages.length === 0 ? (
            // min-h-full + justify-end pins the empty state above the composer.
            <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-end">
              <EmptyState onPromptClick={handleSend} isStreaming={isStreaming} />
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-5">
              {displayMessages.map((msg) => {
                if (msg.role === 'user') return <UserMessage key={msg.id} content={msg.content} pillPreviews={msg.pillPreviews} />
                if (msg.role === 'divider') return <ModelDivider key={msg.id} content={msg.content} />
                return <AssistantMessage key={msg.id} message={msg} />
              })}
            </div>
          )}
        </div>
        {!atBottom && displayMessages.length > 0 && (
          <button
            type="button"
            onClick={() => scrollToBottom('smooth')}
            className="focus-ring absolute bottom-3 left-1/2 flex h-9 -translate-x-1/2 items-center gap-1.5 rounded-full border border-edge bg-secondary px-3.5 text-sm font-semibold text-secondary-foreground"
          >
            <ArrowDown className="h-4 w-4" />
            Latest
          </button>
        )}
      </div>

      {/* Composer. Bottom padding clears the iOS home indicator, except while
          the keyboard is up (Layout sets html.keyboard-open) — the keyboard
          already covers that inset, and the extra gap would float the field. */}
      <div className="shrink-0 border-t border-divider px-3 pt-2 pb-[calc(0.625rem+env(safe-area-inset-bottom))] md:px-6 md:py-4 [.keyboard-open_&]:pb-2">
        <div className="mx-auto max-w-3xl">
          <ChatInput onSend={handleSend} isStreaming={isStreaming} onStop={stop} maxHeight={160} />
        </div>
      </div>
    </div>
  )
}

// Model choices, grouped by provider — shared by the desktop header dropdown
// and the mobile conversations sheet.
function ModelOptions({ providers, model, onChange }) {
  if (!providers) return <p className="px-3 py-2 text-sm text-muted-foreground">Loading models…</p>
  return Object.entries(providers.providers ?? {}).map(([key, provider]) => (
    <div key={key}>
      <div className="flex items-center gap-2 px-3 py-1.5">
        <span className="text-2xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">
          {provider.name}
        </span>
        {!provider.available && (
          <span className="rounded border border-border px-1 py-0.5 text-2xs text-faint">no key</span>
        )}
      </div>
      {(provider.models ?? []).map((m) => (
        <button
          key={m.id}
          type="button"
          onClick={() => provider.available && onChange(m.id)}
          disabled={!provider.available}
          className={cn(
            'focus-ring flex min-h-11 w-full items-center gap-2 rounded-[9px] px-3 py-2 text-sm transition-colors md:min-h-0',
            !provider.available
              ? 'cursor-not-allowed text-faint'
              : m.id === model
              ? 'bg-accent text-accent-foreground'
              : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
          )}
        >
          <span className="w-3.5 shrink-0">
            {m.id === model && provider.available && <Check className="h-3.5 w-3.5 text-primary" />}
          </span>
          <span className="flex-1 text-left">{m.name}</span>
          <span className="text-xs text-muted-foreground">{m.description}</span>
        </button>
      ))}
    </div>
  ))
}

// Conversation list contents — shared by the desktop aside and the mobile
// sheet so the two can't drift. `showNew` is off in the sheet, which renders
// its own primary New button above the model picker.
function ConversationPanel({
  conversations,
  activeConversationId,
  onNew,
  onSelect,
  onDelete,
  deleteConfirm,
  setDeleteConfirm,
  modelName,
  showNew = true,
}) {
  return (
    <>
      {showNew && (
        <div className="px-3 pt-3 pb-1">
          <button
            type="button"
            onClick={onNew}
            className="focus-ring flex w-full items-center gap-2 rounded-[9px] px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <Plus className="h-4 w-4 shrink-0" />
            New conversation
          </button>
        </div>
      )}

      {/* Conversation list */}
      <div className="flex-1 space-y-px overflow-y-auto overscroll-contain px-2 py-1 md:px-3">
        {conversations.length === 0 ? (
          <p className="px-3 py-3 text-sm text-muted-foreground">No conversations yet</p>
        ) : (
          conversations.map((conv) => {
            const isActive = conv.id === activeConversationId
            const confirming = deleteConfirm === conv.id
            const title = conv.title ?? 'New conversation'
            return (
              <div
                key={conv.id}
                className={cn(
                  'group flex items-center rounded-[10px] transition-colors',
                  isActive ? 'bg-accent' : 'hover:bg-secondary'
                )}
              >
                <button
                  type="button"
                  onClick={() => onSelect(conv.id)}
                  aria-current={isActive ? 'true' : undefined}
                  className="focus-ring flex min-h-14 min-w-0 flex-1 items-center gap-3 rounded-[10px] px-3 py-2 text-left md:min-h-0"
                >
                  <span
                    className={cn(
                      'h-[7px] w-[7px] shrink-0 rotate-45 rounded-[2px]',
                      isActive ? 'bg-primary' : 'bg-nav-inactive'
                    )}
                  />
                  <span className="min-w-0 flex-1">
                    <span
                      className={cn(
                        'block truncate text-md-plus leading-snug md:text-xs',
                        isActive ? 'font-bold text-accent-foreground' : 'font-medium text-foreground md:text-muted-foreground md:group-hover:text-foreground'
                      )}
                    >
                      {title}
                    </span>
                    <span className="mt-0.5 block text-xs text-muted-foreground md:text-2xs">
                      {formatRelativeTime(conv.updatedAt)}
                    </span>
                  </span>
                </button>

                {/* Delete is two-step. Visible on touch (no hover there);
                    desktop keeps it on hover/focus to stay quiet. */}
                {confirming ? (
                  <span className="flex shrink-0 items-center pr-1">
                    <button
                      type="button"
                      onClick={() => onDelete(conv.id)}
                      className="focus-ring h-9 rounded-lg bg-destructive px-3 text-sm font-semibold text-destructive-foreground md:h-7 md:px-2 md:text-xs"
                    >
                      Delete
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleteConfirm(null)}
                      aria-label="Cancel delete"
                      className="focus-ring flex h-11 w-11 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground md:h-7 md:w-7"
                    >
                      <X className="h-4 w-4 md:h-3.5 md:w-3.5" />
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => setDeleteConfirm(conv.id)}
                    aria-label={`Delete ${title}`}
                    className="focus-ring mr-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-opacity hover:text-foreground md:h-7 md:w-7 md:opacity-0 md:focus-visible:opacity-100 md:group-hover:opacity-100"
                  >
                    <Trash2 className="h-4 w-4 md:h-3.5 md:w-3.5" />
                  </button>
                )}
              </div>
            )
          })
        )}
      </div>

      {modelName && (
        <div className="border-t border-border px-4 py-3">
          <p className="truncate text-2xs text-muted-foreground">{modelName}</p>
        </div>
      )}
    </>
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
  // Mobile-only: the conversation list lives in a slide-over rather than a
  // permanent 280px aside, so the thread gets the full 380px width.
  const [showConvList, setShowConvList] = useState(false)
  // id of a conversation that exists only in memory (not yet written to the
  // server) because the user hasn't sent a message in it yet.
  const [unsavedId, setUnsavedId] = useState(null)
  const didAutoSelect = useRef(false)
  // Layout hides its mobile top bar on this route (the chat header replaces
  // it) and hands over its nav toggle so the app menu stays one tap away.
  const { openNav } = useOutletContext() ?? {}

  // Escape closes the mobile sheet (keyboard users / iPad with keyboard).
  // Closing the sheet also abandons a half-finished delete, so it can't be
  // confirmed by accident the next time the sheet opens.
  useEffect(() => {
    if (!showConvList) {
      setDeleteConfirm(null)
      return
    }
    const onKey = (e) => e.key === 'Escape' && setShowConvList(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [showConvList])

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
    fetch('/api/chat/providers', { headers: authHeaders(), credentials: 'include' })
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

  // Selecting/creating from the mobile slide-over should also dismiss it.
  const handleMobileSelect = (id) => {
    handleSelectConversation(id)
    setShowConvList(false)
  }
  const handleMobileNew = () => {
    handleNewConversation()
    setShowConvList(false)
  }

  return (
    // h-full (not h-screen) so ChatPage fills the <main> sized by Layout rather
    // than re-claiming the whole viewport — the double-100vh was half the
    // "can't get back" bug.
    <div className="flex h-full bg-background">
      {/* ── Conversation list panel (desktop) — lives inside the main content
          area, to the right of the app sidebar (rendered by Layout) ── */}
      <aside className="hidden w-[280px] shrink-0 flex-col border-r border-border bg-sidebar md:flex">
        <ConversationPanel
          conversations={conversations}
          activeConversationId={activeConversationId}
          onNew={handleNewConversation}
          onSelect={handleSelectConversation}
          onDelete={handleDeleteConversation}
          deleteConfirm={deleteConfirm}
          setDeleteConfirm={setDeleteConfirm}
          modelName={getModelName(model)}
        />
      </aside>

      {/* ── Conversations sheet (mobile) — a bottom sheet rather than a side
          drawer: it opens from where the thumb is, and also carries the model
          picker that the narrow header has no room for. ── */}
      {showConvList && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div
            className="absolute inset-0 bg-black/55"
            onClick={() => setShowConvList(false)}
          />
          <section
            role="dialog"
            aria-modal="true"
            aria-label="Conversations"
            className="absolute inset-x-0 bottom-0 flex max-h-[85dvh] flex-col rounded-t-[20px] border-t border-border bg-sidebar pb-[env(safe-area-inset-bottom)]"
          >
            <div className="flex justify-center pt-2 pb-1">
              <span className="h-[5px] w-9 rounded-full bg-nav-inactive" />
            </div>
            <div className="flex shrink-0 items-center justify-between pl-5 pr-2">
              <h2 className="font-heading text-[19px] font-extrabold tracking-[-0.025em] text-foreground">
                Conversations
              </h2>
              <button
                type="button"
                onClick={() => setShowConvList(false)}
                className="focus-ring flex h-11 w-11 items-center justify-center rounded-[10px] text-muted-foreground hover:text-foreground"
                aria-label="Close conversations"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="shrink-0 px-4 pt-1 pb-3">
              <button
                type="button"
                onClick={handleMobileNew}
                className="focus-ring flex h-11 w-full items-center justify-center gap-2 rounded-[10px] bg-primary font-heading text-[15px] font-extrabold text-primary-foreground hover:bg-primary/90"
              >
                <Plus className="h-4 w-4" strokeWidth={2.5} />
                New conversation
              </button>
            </div>
            <details className="group/model mx-4 mb-3 shrink-0 rounded-[12px] border border-border bg-card">
              <summary className="focus-ring flex min-h-[52px] cursor-pointer list-none items-center gap-3 rounded-[12px] px-3.5 [&::-webkit-details-marker]:hidden">
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="text-2xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">Model</span>
                  <span className="truncate text-md-plus font-semibold text-foreground">{getModelName(model)}</span>
                </span>
                <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open/model:rotate-180" />
              </summary>
              <div className="max-h-[40dvh] overflow-y-auto px-1 pb-1">
                <ModelOptions providers={providers} model={model} onChange={handleModelChange} />
              </div>
            </details>
            <ConversationPanel
              conversations={conversations}
              activeConversationId={activeConversationId}
              onNew={handleMobileNew}
              onSelect={handleMobileSelect}
              onDelete={handleDeleteConversation}
              deleteConfirm={deleteConfirm}
              setDeleteConfirm={setDeleteConfirm}
              showNew={false}
            />
          </section>
        </div>
      )}

      {/* ── Main area ── */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Header — on mobile this is the only bar on the screen (Layout drops
            its own), so it carries conversations, title, new and app menu. */}
        <header className="flex h-[52px] shrink-0 items-center gap-1 border-b border-divider px-1.5 md:h-auto md:justify-between md:gap-2 md:border-border md:px-6 md:py-3">
          <button
            type="button"
            onClick={() => setShowConvList(true)}
            className="focus-ring flex h-11 w-11 shrink-0 items-center justify-center rounded-[10px] text-secondary-foreground hover:bg-secondary md:hidden"
            aria-label="Show conversations"
          >
            <PanelLeft className="h-5 w-5" />
          </button>
          <div className="flex min-w-0 flex-1 flex-col px-1 md:flex-none md:px-0">
            <span className="truncate text-md-plus font-semibold text-foreground md:text-base">
              <span className="md:hidden">{activeConv?.title ?? 'Son of Anton'}</span>
              <span className="hidden md:inline">Son of Anton</span>
            </span>
            <span className="flex items-center gap-1.5 truncate text-xs text-muted-foreground md:hidden">
              <span className="h-1.5 w-1.5 shrink-0 rotate-45 rounded-[1.5px] bg-primary" />
              <span className="truncate">Son of Anton · {getModelName(model)}</span>
            </span>
          </div>

          {/* Mobile actions */}
          <button
            type="button"
            onClick={handleNewConversation}
            className="focus-ring flex h-11 w-11 shrink-0 items-center justify-center rounded-[10px] text-secondary-foreground hover:bg-secondary md:hidden"
            aria-label="New conversation"
          >
            <SquarePen className="h-5 w-5" />
          </button>
          {openNav && (
            <button
              type="button"
              onClick={openNav}
              className="focus-ring flex h-11 w-11 shrink-0 items-center justify-center rounded-[10px] text-secondary-foreground hover:bg-secondary md:hidden"
              aria-label="Toggle navigation"
            >
              <Menu className="h-5 w-5" />
            </button>
          )}

          {/* Desktop actions */}
          <div className="hidden shrink-0 items-center gap-2 md:flex">
            <div className="relative">
              <button
                type="button"
                onClick={() => setShowModelMenu((v) => !v)}
                className="focus-ring flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                <span>{getModelName(model)}</span>
                <ChevronDown className="h-3 w-3 shrink-0" />
              </button>

              {showModelMenu && (
                <>
                  {/* Click-away overlay */}
                  <div className="fixed inset-0 z-10" onClick={() => setShowModelMenu(false)} />
                  <div className="absolute right-0 top-full z-20 mt-1 w-64 rounded-[10px] border border-border bg-popover p-1">
                    <ModelOptions providers={providers} model={model} onChange={handleModelChange} />
                  </div>
                </>
              )}
            </div>

            <button
              type="button"
              onClick={handleNewConversation}
              className="focus-ring flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
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
