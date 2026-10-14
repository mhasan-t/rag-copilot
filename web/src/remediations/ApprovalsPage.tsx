import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'

import { api } from '../api/client'
import { Card, ErrorMessage, Loading } from '../components/ui'
import { RemediationCard } from './RemediationCard'

export function ApprovalsPage() {
  const pending = useQuery({
    queryKey: ['remediations', 'proposed'],
    queryFn: async () => (await api.GET('/v1/remediations', { params: { query: { status: 'proposed' } } })).data!,
    refetchInterval: 15_000,
  })

  if (pending.isPending) return <Loading />
  return (
    <>
      <h1 className="text-lg font-semibold">Waiting for approval</h1>
      <ErrorMessage error={pending.error} />
      {pending.data?.length === 0 && (
        <Card>
          <p className="text-sm text-muted">Nothing is waiting for a decision.</p>
        </Card>
      )}
      {pending.data?.map((remediation) => (
        <div key={remediation.id} className="space-y-1">
          <RemediationCard remediation={remediation} />
          <Link to={`/runs/${remediation.run_id}`} className="text-sm text-brand underline">
            See the investigation
          </Link>
        </div>
      ))}
    </>
  )
}
