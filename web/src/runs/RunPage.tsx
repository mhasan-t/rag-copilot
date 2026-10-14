import { useQuery } from '@tanstack/react-query'
import Markdown from 'react-markdown'
import { useParams } from 'react-router'

import { api, type Run } from '../api/client'
import { Badge, Card, ErrorMessage, Time, Loading } from '../components/ui'
import { RemediationCard } from '../remediations/RemediationCard'
import { StepsTimeline } from './StepsTimeline'

interface Diagnosis {
  likely_cause: string
  confidence: 'low' | 'medium' | 'high'
  evidence: string[]
  recommended_actions: string[]
}

export function RunPage() {
  const { runId = '' } = useParams()
  const run = useQuery({
    queryKey: ['runs', runId],
    queryFn: async () => (await api.GET('/v1/copilot/runs/{run_id}', { params: { path: { run_id: runId } } })).data!,
    refetchInterval: (query) => pollInterval(query.state.data),
  })

  if (run.isPending) return <Loading />
  if (run.error) return <ErrorMessage error={run.error} />
  const { question, status, answer, error, created_at, remediation } = run.data
  const diagnosis = run.data.diagnosis as Diagnosis | null

  return (
    <>
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <Badge value={status} />
          <span className="text-sm text-muted">
            <Time value={created_at} />
          </span>
        </div>
        <h1 className="text-lg font-semibold">{question}</h1>
      </div>
      {error && <ErrorMessage error={new Error(`The run failed: ${error}`)} />}
      {answer && (
        <Card title="Answer">
          {/* react-markdown never renders raw HTML, so LLM output can't inject markup. */}
          <div className="prose-sm space-y-2 text-sm [&_li]:ml-5 [&_ol]:list-decimal [&_ul]:list-disc">
            <Markdown>{answer}</Markdown>
          </div>
        </Card>
      )}
      {diagnosis && <DiagnosisCard diagnosis={diagnosis} />}
      {remediation && <RemediationCard remediation={remediation} />}
      <StepsTimeline run={run.data} />
    </>
  )
}

function DiagnosisCard({ diagnosis }: { diagnosis: Diagnosis }) {
  return (
    <Card title="Diagnosis" actions={<Badge value="neutral" label={`${diagnosis.confidence} confidence`} />}>
      <dl className="space-y-3 text-sm">
        <div>
          <dt className="font-medium">Likely cause</dt>
          <dd>{diagnosis.likely_cause}</dd>
        </div>
        {diagnosis.evidence.length > 0 && (
          <div>
            <dt className="font-medium">Evidence</dt>
            <dd>
              <ul className="list-inside list-disc">
                {diagnosis.evidence.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </dd>
          </div>
        )}
        {diagnosis.recommended_actions.length > 0 && (
          <div>
            <dt className="font-medium">Recommended</dt>
            <dd>
              <ul className="list-inside list-disc">
                {diagnosis.recommended_actions.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </dd>
          </div>
        )}
      </dl>
    </Card>
  )
}

/** Poll quickly while something is happening, slowly while waiting on a person, not at all once settled. */
function pollInterval(run: Run | undefined): number | false {
  if (!run) return false
  const remediationStatus = run.remediation?.status
  if (run.status === 'running' || remediationStatus === 'approved' || remediationStatus === 'executing') return 3_000
  if (run.status === 'awaiting_approval') return 10_000
  return false
}
