import { useQuery } from '@tanstack/react-query'
import { NavLink, Outlet } from 'react-router'

import { api } from '../api/client'
import { useAuth } from '../auth/auth'
import { Button } from './ui'

const linkClasses = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm ${isActive ? 'bg-neutral-soft font-medium' : 'text-muted hover:text-ink'}`

export function Layout() {
  const { user, logout } = useAuth()
  // Shown as a count on the Approvals link, so waiting decisions are visible from every page.
  const pending = useQuery({
    queryKey: ['remediations', 'proposed'],
    queryFn: async () => (await api.GET('/v1/remediations', { params: { query: { status: 'proposed' } } })).data!,
    refetchInterval: 15_000,
  })

  return (
    <div className="min-h-screen">
      <header className="border-b border-border bg-surface">
        <nav className="mx-auto flex max-w-5xl items-center gap-1 px-4 py-2" aria-label="Main">
          <span className="mr-4 font-semibold">Ops Copilot</span>
          <NavLink to="/" end className={linkClasses}>
            Ask
          </NavLink>
          <NavLink to="/runs" className={linkClasses}>
            Runs
          </NavLink>
          <NavLink to="/approvals" className={linkClasses}>
            Approvals
            {!!pending.data?.length && (
              <span className="ml-1.5 rounded-full bg-warn-soft px-1.5 text-xs text-warn">{pending.data.length}</span>
            )}
          </NavLink>
          {user?.is_superuser && (
            <NavLink to="/users" className={linkClasses}>
              Users
            </NavLink>
          )}
          <span className="ml-auto text-sm text-muted">{user?.email}</span>
          <Button variant="secondary" onClick={logout} className="ml-2">
            Sign out
          </Button>
        </nav>
      </header>
      <main className="mx-auto max-w-5xl space-y-4 p-4">
        <Outlet />
      </main>
    </div>
  )
}
