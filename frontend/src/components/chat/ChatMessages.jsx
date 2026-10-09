import { useState } from 'react'
import { Sparkles, Check, X, ChevronDown, ChevronUp, BarChart3, Gauge, Tag, RefreshCw } from 'lucide-react'
import Markdown from 'react-markdown'
import { cn } from '@/lib/utils'
import ProposalCard from '@/components/chat/ProposalCard'

// Starter prompts for an empty thread. Each carries an icon so the 2×2 grid
// scans at a glance on a phone; `prompt` is what is actually sent.
export const SUGGESTED_PROMPTS = [
  { icon: Gauge, label: 'Which shoes are near retirement?', prompt: 'Which shoes are close to retiring?' },
  { icon: RefreshCw, label: 'Sync my new COROS runs', prompt: 'Do I have any new COROS runs to log?' },
  { icon: BarChart3, label: "How was this week's training?", prompt: 'How was my training this week?' },
  { icon: Tag, label: 'Best deals on my watchlist', prompt: 'What are the best deals on my watchlist right now?' },
]

export const MARKDOWN_COMPONENTS = {
  p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
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
  // Wide markdown tables scroll inside their own box instead of widening the
  // thread past the phone viewport.
  table: ({ children }) => (
    <div className="mb-2 overflow-x-auto rounded-[10px] border border-border">
      <table className="w-full text-sm tabular-nums">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="whitespace-nowrap border-b border-border bg-secondary px-3 py-2 text-left text-2xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">
      {children}
    </th>
  ),
  td: ({ children }) => <td className="whitespace-nowrap border-b border-divider px-3 py-2">{children}</td>,
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

// Tool calls read as telemetry: a small mono line per call, not a chat bubble.
export function ToolPill({ indicator }) {
  const isCalling = indicator.status === 'calling'
  const isError = indicator.status === 'error'
  return (
    <span
      className={cn(
        'inline-flex h-7 items-center gap-1.5 rounded-lg border px-2.5 font-mono text-xs',
        isCalling ? 'border-edge bg-secondary text-secondary-foreground' : 'border-divider text-muted-foreground'
      )}
    >
      {isCalling ? (
        <span className="h-[7px] w-[7px] shrink-0 rotate-45 animate-pulse rounded-[2px] bg-primary" />
      ) : isError ? (
        <X className="h-3 w-3 text-destructive" strokeWidth={3} />
      ) : (
        <Check className="h-3 w-3 text-primary" strokeWidth={3} />
      )}
      {indicator.tool}
      {isCalling && '…'}
    </span>
  )
}

export function UserMessage({ content, pillPreviews }) {
  const [expanded, setExpanded] = useState(false)
  const hasPills = pillPreviews?.length > 0

  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] space-y-1.5 md:max-w-[75%]">
        {hasPills && (
          <div className="flex flex-wrap items-center gap-1 justify-end">
            {pillPreviews.map((p) => (
              <span
                key={p.uri}
                className="inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-2xs font-semibold text-accent-foreground"
              >
                <BarChart3 className="h-3 w-3" /> {p.label}
              </span>
            ))}
            <button
              onClick={() => setExpanded((v) => !v)}
              className="focus-ring inline-flex min-h-8 items-center gap-0.5 rounded px-1 text-2xs text-muted-foreground hover:text-foreground transition-colors"
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
                <p className="text-2xs font-semibold text-muted-foreground mb-0.5">{p.label}</p>
                <pre className="text-2xs text-muted-foreground whitespace-pre-wrap leading-relaxed line-clamp-6">
                  {p.content?.slice(0, 600)}{p.content?.length > 600 ? '…' : ''}
                </pre>
              </div>
            ))}
          </div>
        )}
        {/* Surface, not the green wash: green is the signal colour, and the
            runner's own words aren't a signal. */}
        <div className="rounded-[16px] rounded-br-[4px] border border-border bg-secondary px-3.5 py-2.5 text-md-plus text-foreground md:text-sm">
          <p className="whitespace-pre-wrap leading-relaxed">{content}</p>
        </div>
      </div>
    </div>
  )
}

// Replies are unbubbled and full width: lists, tables and numbers need the
// whole 380px column far more than they need a container.
export function AssistantMessage({ message, onProposalResolved, busy }) {
  return (
    <div className="min-w-0 text-md-plus text-foreground md:text-sm">
      {message.toolIndicators?.length > 0 && (
        <div className="mb-2.5 flex flex-wrap gap-1.5">
          {message.toolIndicators.map((ind) => (
            <ToolPill key={ind.id} indicator={ind} />
          ))}
        </div>
      )}
      {message.content ? (
        <Markdown components={MARKDOWN_COMPONENTS}>{message.content}</Markdown>
      ) : message.isStreaming ? (
        <span className="inline-flex items-center gap-1 py-1" aria-label="Son of Anton is thinking">
          <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:-0.3s]" />
          <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:-0.15s]" />
          <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce" />
        </span>
      ) : null}
      {message.proposals?.map((p) => (
        <ProposalCard key={p.id} proposal={p} onResolved={onProposalResolved} busy={busy} />
      ))}
    </div>
  )
}

export function ModelDivider({ content }) {
  return (
    <div className="flex items-center gap-2 py-1">
      <div className="flex-1 h-px bg-border" />
      <span className="text-2xs text-faint px-2 shrink-0">{content}</span>
      <div className="flex-1 h-px bg-border" />
    </div>
  )
}

// Empty thread: bottom-weighted so the starters sit in thumb reach above the
// composer on a phone (the parent pins this to the bottom of the scroll area).
export function EmptyState({ onPromptClick, isStreaming }) {
  return (
    <div className="flex flex-col gap-5 py-4">
      <div className="flex flex-col gap-2">
        <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
          <Sparkles className="h-6 w-6" />
        </span>
        <h2 className="mt-1 font-heading text-[28px] font-extrabold leading-[1.05] tracking-[-0.02em] text-foreground">
          Son of Anton
        </h2>
        <p className="text-md-plus leading-normal text-muted-foreground md:text-sm">
          Ask about your shoes, runs and deals. Anything that changes your data, you confirm first.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {SUGGESTED_PROMPTS.map(({ icon: Icon, label, prompt }) => (
          <button
            key={label}
            type="button"
            onClick={() => onPromptClick(prompt)}
            disabled={isStreaming}
            className="focus-ring flex min-h-[92px] flex-col items-start gap-2 rounded-[13px] border border-border bg-secondary p-3.5 text-left text-sm font-semibold leading-snug text-foreground transition-colors hover:border-edge hover:bg-card disabled:pointer-events-none disabled:opacity-50"
          >
            <Icon className="h-5 w-5 text-primary" />
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}
