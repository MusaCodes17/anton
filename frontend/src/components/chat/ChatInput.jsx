import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { ArrowUp, Square, X, Loader2, BarChart3, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { authHeaders } from '@/services/api'

// ── Resource picker dropdown ──────────────────────────────────────────────────

function ResourcePicker({ groups, filter, activeIndex, onSelect, onClose, containerRef }) {
  const scrollRef = useRef(null)

  // Flatten all items for keyboard-nav index tracking
  const flatItems = useMemo(() => groups.flatMap((g) => g.items), [groups])

  // Scroll active item into view
  useEffect(() => {
    const el = scrollRef.current?.querySelector('[data-active="true"]')
    el?.scrollIntoView({ block: 'nearest' })
  }, [activeIndex])

  if (groups.length === 0) return null

  return (
    <div
      className={cn(
        'absolute bottom-full left-0 z-50 mb-1 w-80 max-w-full rounded-[10px] border border-border bg-sidebar py-1 shadow-xl',
        'max-h-[280px] overflow-y-auto'
      )}
      ref={scrollRef}
    >
      {groups.map((group) => (
        <div key={group.label}>
          <div className="px-3 py-1.5 text-2xs font-semibold uppercase tracking-wider text-muted-foreground select-none">
            {group.label}
          </div>
          {group.items.map((item) => {
            const idx = flatItems.indexOf(item)
            const isActive = idx === activeIndex
            return (
              <button
                key={item.id}
                data-active={isActive}
                onClick={() => onSelect(item)}
                className={cn(
                  'flex min-h-11 w-full flex-col justify-center px-3 py-2 text-left transition-colors',
                  isActive ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                )}
              >
                <span className="text-sm font-medium leading-snug">{item.label}</span>
                {item.sublabel && (
                  <span className="text-2xs opacity-60 leading-snug">{item.sublabel}</span>
                )}
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}

// ── Pill ──────────────────────────────────────────────────────────────────────

function ResourcePill({ pill, onRemove }) {
  return (
    <span
      className={cn(
        'inline-flex h-[30px] items-center gap-1.5 rounded-full pl-2.5 pr-0.5 text-[13px] font-semibold shrink-0',
        pill.status === 'error'
          ? 'bg-secondary text-destructive'
          : 'bg-accent text-accent-foreground'
      )}
    >
      {pill.status === 'loading' ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
      ) : pill.status === 'error' ? (
        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
      ) : (
        <BarChart3 className="h-3.5 w-3.5 shrink-0" />
      )}
      <span className="max-w-[160px] truncate">{pill.label}</span>
      <button
        type="button"
        onClick={() => onRemove(pill.id)}
        className="focus-ring flex h-[26px] w-[26px] items-center justify-center rounded-full opacity-70 transition-opacity hover:opacity-100"
        aria-label={`Remove ${pill.label}`}
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  )
}

// ── ChatInput ─────────────────────────────────────────────────────────────────

/**
 * Shared chat input for ChatPage and ChatDrawer.
 *
 * Props:
 *   onSend(displayContent, apiContent, pillPreviews) — called when message is submitted
 *   isStreaming — while true, Enter won't send and the send button becomes Stop;
 *                 the textarea stays editable so the next message can be drafted
 *   onStop — aborts the in-flight reply (Stop button); omit to hide Stop
 *   placeholder — textarea placeholder text
 *   maxHeight — max textarea height in px (default 160)
 *   textareaClassName — extra classes for the textarea
 */
export default function ChatInput({
  onSend,
  isStreaming,
  onStop,
  placeholder = 'Message Son of Anton',
  maxHeight = 160,
  textareaClassName,
}) {
  const [input, setInput] = useState('')
  const [pills, setPills] = useState([])

  // @ picker state
  const [atFilter, setAtFilter] = useState(null)     // null = closed, string = open + filter
  const [pickerIndex, setPickerIndex] = useState(0)
  const [resources, setResources] = useState(null)
  const [resourcesLoading, setResourcesLoading] = useState(false)
  const [contentCache, setContentCache] = useState({})

  const textareaRef = useRef(null)
  const wrapperRef = useRef(null)

  // Focus on mount — desktop only. On a phone, focusing raises the keyboard
  // over half the thread before the user has read anything; a coarse pointer
  // is the signal (touch-first device), not viewport width.
  useEffect(() => {
    if (window.matchMedia?.('(pointer: fine)').matches) textareaRef.current?.focus()
  }, [])

  // Load resource list from API (once)
  const loadResources = useCallback(async () => {
    if (resources || resourcesLoading) return
    setResourcesLoading(true)
    try {
      const res = await fetch('/api/chat/resources', {
        headers: authHeaders(),
        credentials: 'include',
      })
      const data = await res.json()
      setResources(data)
    } catch {
      setResources({ groups: [] })
    } finally {
      setResourcesLoading(false)
    }
  }, [resources, resourcesLoading])

  // Filtered groups for the picker dropdown
  const filteredGroups = useMemo(() => {
    if (!resources || atFilter === null) return []
    const q = atFilter.toLowerCase()
    if (!q) return resources.groups
    return resources.groups
      .map((group) => ({
        ...group,
        items: group.items.filter(
          (item) =>
            item.label.toLowerCase().includes(q) ||
            (item.sublabel || '').toLowerCase().includes(q)
        ),
      }))
      .filter((g) => g.items.length > 0)
  }, [resources, atFilter])

  const flatItems = useMemo(() => filteredGroups.flatMap((g) => g.items), [filteredGroups])

  // Reset picker index when filter changes
  useEffect(() => { setPickerIndex(0) }, [atFilter])

  // Fetch content for a pill immediately after selection
  const fetchPillContent = useCallback(async (pillId, uri) => {
    if (contentCache[uri]) {
      setPills((prev) =>
        prev.map((p) => p.id === pillId ? { ...p, content: contentCache[uri], status: 'ready' } : p)
      )
      return
    }
    try {
      const res = await fetch('/api/chat/resource/read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        credentials: 'include',
        body: JSON.stringify({ uri }),
      })
      if (!res.ok) throw new Error('fetch failed')
      const data = await res.json()
      setContentCache((prev) => ({ ...prev, [uri]: data.content }))
      setPills((prev) =>
        prev.map((p) => p.id === pillId ? { ...p, content: data.content, status: 'ready' } : p)
      )
    } catch {
      setPills((prev) =>
        prev.map((p) => p.id === pillId ? { ...p, status: 'error' } : p)
      )
    }
  }, [contentCache])

  const selectPickerItem = useCallback((item) => {
    // Strip the @filter suffix from the input
    const atIdx = input.lastIndexOf('@')
    const trimmedInput = atIdx >= 0 ? input.slice(0, atIdx) : input
    setInput(trimmedInput)
    setAtFilter(null)

    const pillId = `pill-${Date.now()}`
    setPills((prev) => [...prev, { id: pillId, uri: item.uri, label: item.label, status: 'loading', content: null }])
    fetchPillContent(pillId, item.uri)
    textareaRef.current?.focus()
  }, [input, fetchPillContent])

  const removePill = (id) => setPills((prev) => prev.filter((p) => p.id !== id))

  const handleChange = (e) => {
    const val = e.target.value
    setInput(val)

    // Detect @ trigger — only when @ is at the very end or followed by non-space text
    const atIdx = val.lastIndexOf('@')
    if (atIdx >= 0) {
      const afterAt = val.slice(atIdx + 1)
      if (!afterAt.includes(' ')) {
        setAtFilter(afterAt)
        loadResources()
        return
      }
    }
    setAtFilter(null)
  }

  const handleAutoResize = (e) => {
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, maxHeight) + 'px'
  }

  const handleSend = useCallback(() => {
    const trimmed = input.trim()
    if ((!trimmed && pills.length === 0) || isStreaming) return
    if (!trimmed) return // need at least some text
    if (pills.some((p) => p.status === 'loading')) return // wait for fetches

    const readyPills = pills.filter((p) => p.status === 'ready')
    const pillBlock = readyPills
      .map((p) => `[Context: ${p.label}]\n${p.content}`)
      .join('\n\n')
    const apiContent = pillBlock ? `${pillBlock}\n\n---\n${trimmed}` : trimmed
    const pillPreviews = readyPills.map(({ uri, label, content }) => ({ uri, label, content }))

    onSend(trimmed, apiContent, pillPreviews)
    setInput('')
    setPills([])
    setAtFilter(null)
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [input, pills, isStreaming, onSend])

  const handleKeyDown = (e) => {
    if (atFilter !== null && filteredGroups.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setPickerIndex((i) => Math.min(i + 1, flatItems.length - 1))
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setPickerIndex((i) => Math.max(i - 1, 0))
        return
      }
      if (e.key === 'Enter') {
        e.preventDefault()
        if (flatItems[pickerIndex]) selectPickerItem(flatItems[pickerIndex])
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setAtFilter(null)
        return
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const pickerOpen = atFilter !== null && filteredGroups.length > 0
  const showStop = isStreaming && onStop
  const sendDisabled = isStreaming || !input.trim() || pills.some((p) => p.status === 'loading')

  return (
    <div className="flex flex-col gap-2">
      {/* Pills row */}
      {pills.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-1">
          {pills.map((pill) => (
            <ResourcePill key={pill.id} pill={pill} onRemove={removePill} />
          ))}
        </div>
      )}

      {/* Input row with picker anchor. One rounded field holding the textarea
          and the send/stop button, so the whole composer reads as one control. */}
      <div
        className="relative flex items-end gap-1 rounded-[22px] border border-input bg-card p-1 transition-colors focus-within:border-primary"
        ref={wrapperRef}
      >
        {pickerOpen && (
          <ResourcePicker
            groups={filteredGroups}
            filter={atFilter}
            activeIndex={pickerIndex}
            onSelect={selectPickerItem}
            onClose={() => setAtFilter(null)}
            containerRef={wrapperRef}
          />
        )}

        {/* 16px text below md is load-bearing: iOS Safari zooms the page into
            any focused field under 16px, which breaks the fixed PWA shell. */}
        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onInput={handleAutoResize}
          placeholder={placeholder}
          aria-label="Message"
          enterKeyHint="send"
          rows={1}
          className={cn(
            'min-w-0 flex-1 resize-none bg-transparent px-3 py-[9px] text-base leading-[22px] placeholder:text-muted-foreground focus:outline-none md:text-sm',
            textareaClassName
          )}
          style={{ minHeight: '40px', maxHeight: `${maxHeight}px`, overflowY: 'auto' }}
        />
        {showStop ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop generating"
            className="focus-ring flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-foreground text-background transition-opacity hover:opacity-90"
          >
            <Square className="h-3.5 w-3.5 fill-current" />
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSend}
            disabled={sendDisabled}
            aria-label="Send"
            className="focus-ring flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition-colors hover:bg-primary/90 disabled:bg-border disabled:text-faint"
          >
            <ArrowUp className="h-[18px] w-[18px]" strokeWidth={2.5} />
          </button>
        )}
      </div>
      {/* Keyboard hints only mean something with a hardware keyboard. */}
      <p className="hidden px-1 text-xs text-faint md:block">Enter to send · Shift+Enter for newline · @ to mention a resource</p>
    </div>
  )
}
