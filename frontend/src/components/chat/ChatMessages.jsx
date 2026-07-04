import { useState } from 'react'
import { MessageCircle, Check, Wrench, ChevronDown, ChevronUp } from 'lucide-react'
import Markdown from 'react-markdown'
import { cn } from '@/lib/utils'

export const SUGGESTED_PROMPTS = [
  'How are my shoes holding up?',
  'Any good deals on Adidas right now?',
  'Which shoe should I retire soon?',
  'Log 10km on my Teal Evo SL from today',
]

export const MARKDOWN_COMPONENTS = {
  p: ({ children }) => <p className="mb-1.5 last:mb-0 leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="list-disc pl-4 mb-1.5 space-y-0.5">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-4 mb-1.5 space-y-0.5">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  a: ({ href, children }) => (
    <a href={href} className="text-primary underline" target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  h1: ({ children }) => <h1 className="text-sm font-bold mb-1 mt-2 first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="text-sm font-semibold mb-1 mt-2 first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-semibold mb-0.5 mt-1.5 first:mt-0">{children}</h3>,
  code: ({ children, className }) =>
    className ? (
      <pre className="bg-background rounded p-2 overflow-x-auto text-xs mb-1.5 border border-border">
        <code>{children}</code>
      </pre>
    ) : (
      <code className="bg-background rounded px-1 py-0.5 text-xs">{children}</code>
    ),
  pre: ({ children }) => <>{children}</>,
}

export function ToolPill({ indicator }) {
  const isDone = indicator.status !== 'calling'
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full transition-all',
        isDone ? 'text-faint' : 'text-muted-foreground bg-secondary animate-pulse'
      )}
    >
      {isDone ? (
        <Check className="h-3 w-3 text-primary/70" />
      ) : (
        <Wrench className="h-3 w-3" />
      )}
      {indicator.tool}
    </span>
  )
}

export function UserMessage({ content, pillPreviews }) {
  const [expanded, setExpanded] = useState(false)
  const hasPills = pillPreviews?.length > 0

  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] space-y-1.5">
        {hasPills && (
          <div className="flex flex-wrap items-center gap-1 justify-end">
            {pillPreviews.map((p) => (
              <span
                key={p.uri}
                className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-2xs text-primary"
              >
                📊 {p.label}
              </span>
            ))}
            <button
              onClick={() => setExpanded((v) => !v)}
              className="inline-flex items-center gap-0.5 text-2xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {expanded ? (
                <><ChevronUp className="h-3 w-3" /> hide context</>
              ) : (
                <><ChevronDown className="h-3 w-3" /> show context</>
              )}
            </button>
          </div>
        )}
        {expanded && hasPills && (
          <div className="rounded-[10px] border border-border bg-secondary/50 p-2 space-y-2 max-h-48 overflow-y-auto">
            {pillPreviews.map((p) => (
              <div key={p.uri}>
                <p className="text-[10px] font-semibold text-muted-foreground mb-0.5">{p.label}</p>
                <pre className="text-[10px] text-muted-foreground/70 whitespace-pre-wrap leading-relaxed line-clamp-6">
                  {p.content?.slice(0, 600)}{p.content?.length > 600 ? '…' : ''}
                </pre>
              </div>
            ))}
          </div>
        )}
        <div className="rounded-[12px] rounded-br-[4px] bg-accent px-3 py-2 text-sm text-accent-foreground">
          <p className="whitespace-pre-wrap leading-relaxed">{content}</p>
        </div>
      </div>
    </div>
  )
}

export function AssistantMessage({ message }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[90%] rounded-[12px] rounded-bl-[4px] bg-secondary px-3 py-2 text-sm text-foreground">
        {message.toolIndicators?.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2 border-b border-border pb-2">
            {message.toolIndicators.map((ind) => (
              <ToolPill key={ind.id} indicator={ind} />
            ))}
          </div>
        )}
        {message.content ? (
          <Markdown components={MARKDOWN_COMPONENTS}>{message.content}</Markdown>
        ) : message.isStreaming ? (
          <span className="inline-flex items-center gap-1 py-1">
            <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:-0.3s]" />
            <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:-0.15s]" />
            <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce" />
          </span>
        ) : null}
      </div>
    </div>
  )
}

export function ModelDivider({ content }) {
  return (
    <div className="flex items-center gap-2 py-1">
      <div className="flex-1 h-px bg-border" />
      <span className="text-[10px] text-muted-foreground/50 px-2 shrink-0">{content}</span>
      <div className="flex-1 h-px bg-border" />
    </div>
  )
}

export function EmptyState({ onPromptClick, isStreaming }) {
  return (
    <div className="flex flex-col items-center gap-4 py-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent">
        <MessageCircle className="h-6 w-6 text-accent-foreground" />
      </div>
      <div>
        <p className="text-sm font-medium text-foreground">Son of Anton</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Ask about your shoes, find deals, or log a run
        </p>
      </div>
      <div className="mt-1 w-full space-y-2">
        {SUGGESTED_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            onClick={() => onPromptClick(prompt)}
            disabled={isStreaming}
            className="w-full rounded-[10px] border border-border px-3 py-2 text-left text-sm text-muted-foreground transition-colors hover:border-primary/30 hover:bg-secondary hover:text-foreground disabled:pointer-events-none disabled:opacity-50"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  )
}
