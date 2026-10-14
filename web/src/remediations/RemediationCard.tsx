import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, type Remediation } from '../api/client'
import { Badge, Button, Card, ErrorMessage, Time, inputClasses } from '../components/ui'

const ACTION_LABELS: Record<string, string> = {
  rollback_deployment: 'Roll back',
  restart_deployment: 'Restart',
  scale_deployment: 'Scale',
}

/** A proposed action, its decision, and what happened when it ran. */
export function RemediationCard({ remediation }: { remediation: Remediation }) {
  const { action, service, params, risk_level: risk, status } = remediation
  const what = `${ACTION_LABELS[action] ?? action} ${service}${params.replicas ? ` to ${params.replicas} replicas` : ''}`
  return (
    <Card
      title={`Proposed action: ${what}`}
      actions={
        <div className="flex gap-2">
          <Badge value={risk} label={`${risk} risk`} />
          <Badge value={status} />
        </div>
      }
    >
      <div className="space-y-3 text-sm">
        <p>{remediation.rationale}</p>
        {status === 'proposed' ? <DecisionForm remediation={remediation} /> : <Outcome remediation={remediation} />}
      </div>
    </Card>
  )
}

function DecisionForm({ remediation }: { remediation: Remediation }) {
  const queryClient = useQueryClient()
  const [comment, setComment] = useState('')
  const decide = useMutation({
    mutationFn: async (decision: 'approve' | 'reject') => {
      const path = `/v1/remediations/{proposal_id}/${decision}` as const
      return (
        await api.POST(path, { params: { path: { proposal_id: remediation.id } }, body: { comment: comment || null } })
      ).data!
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['runs'] })
      queryClient.invalidateQueries({ queryKey: ['remediations'] })
    },
  })

  return (
    <div className="space-y-2">
      <p className="text-muted">
        {remediation.risk_level === 'high'
          ? 'High risk: needs a superuser, and not the one who asked (unless they are the only superuser).'
          : 'Low risk: any user may approve.'}
      </p>
      <label className="block space-y-1">
        <span>Comment (optional)</span>
        <input className={inputClasses} value={comment} onChange={(event) => setComment(event.target.value)} />
      </label>
      <ErrorMessage error={decide.error} />
      <div className="flex gap-2">
        <Button onClick={() => decide.mutate('approve')} disabled={decide.isPending}>
          Approve and run
        </Button>
        <Button variant="secondary" onClick={() => decide.mutate('reject')} disabled={decide.isPending}>
          Reject
        </Button>
      </div>
    </div>
  )
}

function Outcome({ remediation }: { remediation: Remediation }) {
  const { approval, execution, status } = remediation
  return (
    <div className="space-y-2">
      {approval && (
        <p className="text-muted">
          {approval.decision === 'approved' ? 'Approved' : 'Rejected'} <Time value={approval.decided_at} />
          {approval.comment && <>: “{approval.comment}”</>}
        </p>
      )}
      {(status === 'approved' || status === 'executing') && (
        <p role="status" className="text-info">
          Carrying out the action and watching the service recover; this can take a few minutes.
        </p>
      )}
      {execution?.error && <p className="text-danger">{execution.error}</p>}
      {execution?.verification && (
        <div>
          <p className={execution.verification.passed ? 'text-ok' : 'text-warn'}>
            {execution.verification.passed
              ? `The service recovered (checked after ${execution.verification.waited_seconds} s).`
              : `The service had not recovered after ${execution.verification.waited_seconds} s: escalate.`}
          </p>
          <ul className="mt-1 list-inside list-disc text-muted">
            {execution.verification.checks.map((check) => (
              <li key={check.metric}>
                {check.metric}: {check.value ?? 'no data'} (threshold {check.threshold}) {check.passed ? '✓' : '✗'}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
