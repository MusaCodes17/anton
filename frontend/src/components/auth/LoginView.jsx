import { useState } from 'react'
import { authApi } from '@/services/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import BrandMark from '@/components/layout/BrandMark'

// RA2.1 login view — the password gate that issues the httpOnly session cookie.
// Shown by AuthGate when the load-time probe (or a 401) says there is no valid
// session. On success it calls onAuthenticated() so AuthGate swaps in the app.
export default function LoginView({ onAuthenticated }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (submitting || !password) return
    setSubmitting(true)
    setError('')
    try {
      await authApi.login(password)
      onAuthenticated()
    } catch (err) {
      // The backend returns 401 (wrong password) or 429 (rate limited); the
      // axios interceptor turns both into an Error with a message. Keep it
      // generic — no oracle for which field was wrong (C9).
      setError(
        /429|rate/i.test(err.message)
          ? 'Too many attempts — wait a moment and try again.'
          : 'Incorrect password.'
      )
      setPassword('')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <form
        onSubmit={handleSubmit}
        className="panel w-full max-w-sm rounded-lg border border-border bg-card p-8"
      >
        <div className="mb-6 flex items-center gap-[11px]">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] border border-input text-primary">
            <BrandMark className="h-[19px] w-[19px]" />
          </span>
          <span className="font-heading text-[21px] font-light tracking-display text-foreground">
            Anton
          </span>
        </div>

        <Label htmlFor="password" className="mb-2 block text-muted-foreground">
          Password
        </Label>
        <Input
          id="password"
          type="password"
          autoFocus
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mb-4"
        />

        {error && (
          <p className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={submitting || !password}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
    </div>
  )
}
