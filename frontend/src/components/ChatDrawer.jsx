import { useState, useRef, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { MessageCircle, X, Maximize2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { UserMessage, AssistantMessage, ModelDivider, EmptyState } from '@/components/chat/ChatMessages'
import ChatInput from '@/components/chat/ChatInput'
import { useChatStream } from '@/hooks/useChatStream'

const DEFAULT_MODEL = 'claude-haiku-4-5-20251001'

export default function ChatDrawer() {
  const [isOpen, setIsOpen] = useState(false)

  const { displayMessages, apiMessages, isStreaming, sendMessage } = useChatStream({
    model: DEFAULT_MODEL,
  })

  const messagesEndRef = useRef(null)
  const location = useLocation()
  const navigate = useNavigate()

  const hidden = location.pathname === '/assistant'

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
        onClick={() => setIsOpen(true)}
        aria-label="Open Son of Anton"
        className={cn(
          'fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-full bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground shadow-lg hover:bg-primary/90 transition-all duration-200',
          isOpen ? 'opacity-0 pointer-events-none translate-y-2' : 'opacity-100 translate-y-0'
        )}
      >
        <MessageCircle className="h-4 w-4" />
        Son of Anton
      </button>

      {/* Backdrop */}
      <div
        className={cn(
          'fixed inset-0 z-[50] bg-black/40 transition-opacity duration-300',
          isOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        )}
        onClick={() => setIsOpen(false)}
      />

      {/* Drawer */}
      <div
        className={cn(
          'fixed right-0 top-0 z-[51] flex h-full w-[400px] flex-col border-l border-border bg-sidebar transition-transform duration-300',
          'max-[500px]:w-full',
          isOpen ? 'translate-x-0' : 'translate-x-full'
        )}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-3">
          <span className="font-semibold text-foreground">Son of Anton</span>
          <div className="flex items-center gap-1">
            <button
              onClick={handleOpenFullPage}
              className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              aria-label="Open full page"
              title="Open full page"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
            <button
              onClick={() => setIsOpen(false)}
              className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
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
            <div className="space-y-3">
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
        <div className="shrink-0 border-t border-border px-4 py-3">
          <ChatInput onSend={handleSend} isStreaming={isStreaming} maxHeight={120} />
        </div>
      </div>
    </>
  )
}
