import { useState, type FormEvent } from 'react'

import { Button, ErrorMessage, inputClasses } from '../components/ui'
import { useAuth } from './auth'

export function LoginPage() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [pending, setPending] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      await login(email, password)
    } catch (caught) {
      setError(caught)
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm space-y-4 rounded-lg border border-border bg-surface p-6 shadow-sm"
      >
        <h1 className="text-lg font-semibold">Operations Copilot</h1>
        <label className="block space-y-1 text-sm">
          <span>Email</span>
          <input
            className={inputClasses}
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label className="block space-y-1 text-sm">
          <span>Password</span>
          <input
            className={inputClasses}
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <ErrorMessage error={error} />
        <Button type="submit" disabled={pending} className="w-full">
          {pending ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
    </main>
  )
}
