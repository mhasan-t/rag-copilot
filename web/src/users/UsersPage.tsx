import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { api, type User } from '../api/client'
import { useAuth } from '../auth/auth'
import { Badge, Button, Card, ErrorMessage, Time, inputClasses, Loading } from '../components/ui'

const MIN_PASSWORD_LENGTH = 12

export function UsersPage() {
  const users = useQuery({
    queryKey: ['users'],
    queryFn: async () => (await api.GET('/v1/users', { params: { query: { limit: 200 } } })).data!,
  })

  return (
    <>
      <CreateUserForm />
      <Card title="Users">
        {users.isPending && <Loading />}
        <ErrorMessage error={users.error} />
        <ul className="divide-y divide-border">
          {users.data?.map((user) => (
            <UserRow key={user.id} user={user} />
          ))}
        </ul>
      </Card>
    </>
  )
}

function CreateUserForm() {
  const queryClient = useQueryClient()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const create = useMutation({
    mutationFn: async () => (await api.POST('/v1/users', { body: { email, password } })).data!,
    onSuccess: () => {
      setEmail('')
      setPassword('')
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    create.mutate()
  }

  return (
    <Card title="Add a user">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2 text-sm">
        <label className="min-w-56 flex-1 space-y-1">
          <span>Email</span>
          <input
            className={inputClasses}
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="min-w-56 flex-1 space-y-1">
          <span>Initial password ({MIN_PASSWORD_LENGTH}+ characters)</span>
          <input
            className={inputClasses}
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <Button type="submit" disabled={create.isPending}>
          Add user
        </Button>
      </form>
      <div className="mt-2">
        <ErrorMessage error={create.error} />
      </div>
      <p className="mt-2 text-xs text-muted">
        New users can ask questions and approve low-risk actions. Superusers are created with the CLI.
      </p>
    </Card>
  )
}

function UserRow({ user }: { user: User }) {
  const queryClient = useQueryClient()
  const { user: me } = useAuth()
  const [newPassword, setNewPassword] = useState<string | null>(null)
  const update = useMutation({
    mutationFn: async (changes: { is_active?: boolean; password?: string }) =>
      (await api.PATCH('/v1/users/{user_id}', { params: { path: { user_id: user.id } }, body: changes })).data!,
    onSuccess: () => {
      setNewPassword(null)
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })

  function resetPassword(event: FormEvent) {
    event.preventDefault()
    if (newPassword) update.mutate({ password: newPassword })
  }

  return (
    <li className="space-y-2 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{user.email}</span>
        {user.is_superuser && <Badge value="info" label="superuser" />}
        {!user.is_active && <Badge value="failed" label="deactivated" />}
        <span className="text-xs text-muted">
          added <Time value={user.created_at} />
        </span>
        <div className="ml-auto flex gap-2">
          {user.id !== me?.id && (
            <Button
              variant="secondary"
              onClick={() => update.mutate({ is_active: !user.is_active })}
              disabled={update.isPending}
            >
              {user.is_active ? 'Deactivate' : 'Reactivate'}
            </Button>
          )}
          <Button variant="secondary" onClick={() => setNewPassword(newPassword === null ? '' : null)}>
            Reset password
          </Button>
        </div>
      </div>
      {newPassword !== null && (
        <form onSubmit={resetPassword} className="flex items-end gap-2">
          <label className="flex-1 space-y-1">
            <span>New password for {user.email} (signs them out everywhere)</span>
            <input
              className={inputClasses}
              type="password"
              autoComplete="new-password"
              required
              minLength={MIN_PASSWORD_LENGTH}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
          </label>
          <Button type="submit" disabled={update.isPending}>
            Set password
          </Button>
        </form>
      )}
      <ErrorMessage error={update.error} />
    </li>
  )
}
