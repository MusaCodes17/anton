import * as React from 'react'
import { CheckCircle2, AlertCircle, X, Info } from 'lucide-react'
import { cn } from '@/lib/utils'

const ToastContext = React.createContext(null)

let idCounter = 0

/** Provides a `toast({ title, description, variant })` function via context. */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = React.useState([])

  const dismiss = React.useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const toast = React.useCallback(
    ({ title, description, variant = 'default', duration = 5000 }) => {
      const id = ++idCounter
      setToasts((prev) => [...prev, { id, title, description, variant }])
      if (duration) setTimeout(() => dismiss(id), duration)
      return id
    },
    [dismiss]
  )

  return (
    <ToastContext.Provider value={{ toast, dismiss }}>
      {children}
      {/* Mobile: lifted above the bottom tab bar (h-14 + home indicator). */}
      <div className="fixed bottom-[calc(3.5rem+env(safe-area-inset-bottom))] right-0 z-[100] flex max-h-screen w-full flex-col gap-2 p-4 sm:max-w-sm md:bottom-0">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

const icons = {
  default: Info,
  success: CheckCircle2,
  destructive: AlertCircle,
}

function ToastItem({ toast, onDismiss }) {
  const Icon = icons[toast.variant] || Info
  return (
    <div
      className={cn(
        'pointer-events-auto flex items-start gap-3 rounded-lg border bg-background p-4 shadow-lg animate-in slide-in-from-right-full',
        toast.variant === 'destructive' && 'border-destructive/50 text-destructive',
        toast.variant === 'success' && 'border-success/50'
      )}
    >
      <Icon
        className={cn(
          'mt-0.5 h-5 w-5 shrink-0',
          toast.variant === 'success' && 'text-success',
          toast.variant === 'default' && 'text-primary'
        )}
      />
      <div className="flex-1 space-y-1">
        {toast.title && <p className="text-sm font-semibold">{toast.title}</p>}
        {toast.description && (
          <p className="text-sm text-muted-foreground">{toast.description}</p>
        )}
      </div>
      <button
        onClick={onDismiss}
        className="text-muted-foreground transition-colors hover:text-foreground"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}

export function useToast() {
  const ctx = React.useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within a ToastProvider')
  return ctx
}
