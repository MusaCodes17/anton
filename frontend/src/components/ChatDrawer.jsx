import { useState, useRef, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { MessageCircle, X, Maximize2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { UserMessage, AssistantMessage, ModelDivider, EmptyState } from '@/components/chat/ChatMessages'
import ChatInput from '@/components/chat/ChatInput'
import { useChatStream } from '@/hooks/useChatStream'
import { useMediaQuery } from '@/hooks/useMediaQuery'

const DEFAULT_MODEL = 'claude-haiku-4-5-20251001'

// The floating trigger sits over page content, so it can cover a control (a
// row's toggle, its action icons). When the mouse comes near the trigger AND
// the thing under the pointer is actionable, the trigger "tucks": it shrinks to
// its icon in the bottom-right corner gutter (page padding, not content) and
// stops catching clicks over the content. The gutter icon still opens the
// drawer; moving off the content untucks it.
const TUCK_ZONE_PX = 16 // how far around the trigger the pointer counts as "near"
const TRIGGER_INSET_PX = 24 // bottom-6 / right-6
const ACTIONABLE =
  'a[href],button,input,select,textarea,label,summary,[role="button"],[role="switch"],' +
  '[role="checkbox"],[role="link"],[role="menuitem"],[role="tab"],[tabindex]:not([tabindex="-1"])'

// Whether the pointer at (x, y) is over something clickable, looking *through*
// the trigger itself (elementsFromPoint returns the whole stack, top first).
function actionableUnder(x, y, trigger) {
  for (const el of document.elementsFromPoint(x, y)) {
    if (trigger.contains(el)) continue
    return Boolean(el.closest(ACTIONABLE))
  }
  return false
}

function useTuckAway(triggerRef, enabled) {
  const [tucked, setTucked] = useState(false)

  useEffect(() => {
    if (!enabled) {
      setTucked(false)
      return
    }
    const trigger = triggerRef.current
    if (!trigger) return
    // Measure the *expanded* size once, untransformed: the tuck zone is where
    // the full pill would sit, not where the shrunken icon currently is.
    const size = { w: trigger.offsetWidth, h: trigger.offsetHeight }
    let frame = 0
    const onMove = (e) => {
      if (frame) return
      const { clientX: x, clientY: y } = e
      frame = requestAnimationFrame(() => {
        frame = 0
        const right = window.innerWidth - TRIGGER_INSET_PX + TUCK_ZONE_PX
        const bottom = window.innerHeight - TRIGGER_INSET_PX + TUCK_ZONE_PX
        const near =
          x >= right - size.w - 2 * TUCK_ZONE_PX && x <= right &&
          y >= bottom - size.h - 2 * TUCK_ZONE_PX && y <= bottom
        // On the tucked icon itself: stay tucked, so it doesn't grow out from
        // under the pointer just as it's being clicked.
        setTucked((was) =>
          was && trigger.contains(document.elementFromPoint(x, y))
            ? true
            : near && actionableUnder(x, y, trigger)
        )
      })
    }
    const onLeave = () => setTucked(false)
    window.addEventListener('pointermove', onMove, { passive: true })
    document.documentElement.addEventListener('pointerleave', onLeave)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('pointermove', onMove)
      document.documentElement.removeEventListener('pointerleave', onLeave)
    }
  }, [enabled, triggerRef])

  return tucked
}

export default function ChatDrawer() {
  const [isOpen, setIsOpen] = useState(false)

  const { displayMessages, apiMessages, isStreaming, sendMessage, resolveProposal, stop } = useChatStream({
    model: DEFAULT_MODEL,
  })

  const messagesEndRef = useRef(null)
  const triggerRef = useRef(null)
  const location = useLocation()
  const navigate = useNavigate()

  const hidden = location.pathname === '/assistant'
  // Desktop mouse only: the trigger is md+ and touch has no hover to react to.
  const finePointer = useMediaQuery('(min-width: 768px) and (hover: hover) and (pointer: fine)')
  const tucked = useTuckAway(triggerRef, finePointer && !hidden && !isOpen)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [displayMessages])

  const handleSend = (displayContent, apiContent, pillPreviews) => {
    const trimmed = typeof displayContent === 'string' ? displayContent.trim() : ''
    if (!trimmed || isStreaming) return
    sendMessage(trimmed, apiContent, pillPreviews)
  }

  const handleOpenFullPage = () => {
    // Hand off the current conversation to the full page via sessionStorage
    if (displayMessages.length > 0) {
      sessionStorage.setItem(
        'son-of-anton:drawer-handoff',
        JSON.stringify({ displayMessages, apiMessages })
      )
    }
    setIsOpen(false)
    navigate('/assistant')
  }

  if (hidden) return null

  return (
    <>
      {/* Floating trigger */}
      <button
        ref={triggerRef}
        onClick={() => setIsOpen(true)}
        aria-label="Open Son of Anton"
        title={tucked ? 'Son of Anton' : undefined}
        className={cn(
          // Desktop only: on phones the tab bar's Anton tab replaces the FAB.
          'fixed bottom-6 right-6 z-40 hidden items-center md:flex btn-lit rounded-full py-3 text-sm font-medium',
          'transition-[transform,opacity,padding,border-color,box-shadow] duration-300 ease-out',
          isOpen
            ? 'opacity-0 pointer-events-none translate-y-2 gap-2 px-4'
            : tucked
              // Icon only, slid into the corner gutter (right of the page padding).
              ? 'translate-x-5 translate-y-4 gap-0 px-3 opacity-80'
              : 'opacity-100 translate-y-0 gap-2 px-4'
        )}
      >
        <MessageCircle className="h-4 w-4 shrink-0" />
        <span
          className={cn(
            'overflow-hidden whitespace-nowrap transition-[max-width,opacity] duration-300 ease-out',
            tucked ? 'max-w-0 opacity-0' : 'max-w-[8rem] opacity-100'
          )}
        >
          Son of Anton
        </span>
      </button>

      {/* Backdrop */}
      <div
        className={cn(
          'fixed inset-0 z-[50] bg-[var(--scrim)] transition-opacity duration-300',
          isOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        )}
        onClick={() => setIsOpen(false)}
      />

      {/* Drawer */}
      <div
        className={cn(
          // pt: fixed to the viewport, so it must inset itself below the iOS notch.
          'fixed right-0 top-0 z-[51] flex h-[var(--app-height,100dvh)] w-[400px] flex-col border-l border-border bg-sidebar pt-[env(safe-area-inset-top)] transition-transform duration-300',
          'max-[500px]:w-full',
          isOpen ? 'translate-x-0' : 'translate-x-full'
        )}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-border py-1 pl-4 pr-1">
          <span className="font-semibold text-foreground">Son of Anton</span>
          <div className="flex items-center gap-1">
            <button
              onClick={handleOpenFullPage}
              className="focus-ring flex h-11 w-11 items-center justify-center rounded-[10px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              aria-label="Open full page"
              title="Open full page"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
            <button
              onClick={() => setIsOpen(false)}
              className="focus-ring flex h-11 w-11 items-center justify-center rounded-[10px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {displayMessages.length === 0 ? (
            <EmptyState onPromptClick={handleSend} isStreaming={isStreaming} />
          ) : (
            <div className="space-y-5">
              {displayMessages.map((msg) => {
                if (msg.role === 'user') return <UserMessage key={msg.id} content={msg.content} pillPreviews={msg.pillPreviews} />
                if (msg.role === 'divider') return <ModelDivider key={msg.id} content={msg.content} />
                return (
                  <AssistantMessage
                    key={msg.id}
                    message={msg}
                    onProposalResolved={resolveProposal}
                    busy={isStreaming}
                  />
                )
              })}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="shrink-0 border-t border-border px-3 pt-2 pb-[calc(0.75rem+env(safe-area-inset-bottom))] [.keyboard-open_&]:pb-2">
          <ChatInput onSend={handleSend} isStreaming={isStreaming} onStop={stop} maxHeight={120} />
        </div>
      </div>
    </>
  )
}
