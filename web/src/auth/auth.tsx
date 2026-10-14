import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, use, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { api, setUnauthorizedHandler, tokenStore, type User } from '../api/client'

interface Auth {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<Auth | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [token, setToken] = useState(tokenStore.get)

  const logout = useCallback(() => {
    tokenStore.clear()
    setToken(null)
    queryClient.clear()
  }, [queryClient])

  useEffect(() => setUnauthorizedHandler(logout), [logout])

  const me = useQuery({
    queryKey: ['me', token],
    queryFn: async () => (await api.GET('/v1/auth/me')).data!,
    enabled: token !== null,
    retry: false,
  })

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await api.POST('/v1/auth/token', { body: { email, password } })
    tokenStore.set(data!.access_token)
    setToken(data!.access_token)
  }, [])

  const value = useMemo(
    () => ({ user: token ? (me.data ?? null) : null, loading: token !== null && me.isPending, login, logout }),
    [token, me.data, me.isPending, login, logout],
  )
  return <AuthContext value={value}>{children}</AuthContext>
}

// Kept beside AuthProvider: both use the private context. (Fast refresh reloads this file fully; that's fine.)
// oxlint-disable-next-line react/only-export-components
export function useAuth(): Auth {
  const auth = use(AuthContext)
  if (!auth) throw new Error('useAuth must be used inside AuthProvider')
  return auth
}
