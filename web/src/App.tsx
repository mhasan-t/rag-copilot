import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'

import { ApiError } from './api/client'
import { AuthProvider, useAuth } from './auth/auth'
import { LoginPage } from './auth/LoginPage'
import { Layout } from './components/Layout'
import { Loading } from './components/ui'
import { ApprovalsPage } from './remediations/ApprovalsPage'
import { AskPage } from './runs/AskPage'
import { RunPage } from './runs/RunPage'
import { RunsPage } from './runs/RunsPage'
import { UsersPage } from './users/UsersPage'

const queryClient = new QueryClient({
  defaultOptions: {
    // Retrying a 4xx (forbidden, not found, invalid) can't succeed; retry only server and network errors.
    queries: { retry: (count, error) => count < 2 && !(error instanceof ApiError && error.status < 500) },
  },
})

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}

function AppRoutes() {
  const { user, loading } = useAuth()
  if (loading) return <Loading />
  if (!user) return <LoginPage />
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<AskPage />} />
        <Route path="runs" element={<RunsPage />} />
        <Route path="runs/:runId" element={<RunPage />} />
        <Route path="approvals" element={<ApprovalsPage />} />
        {user.is_superuser && <Route path="users" element={<UsersPage />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
