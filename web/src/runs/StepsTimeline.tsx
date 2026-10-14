import { useQuery } from '@tanstack/react-query'

import { api, type Run, type RunStep } from '../api/client'
import { Card, ErrorMessage, Loading } from '../components/ui'

/** The run's audit trail: every node, evidence query and LLM call, with what went in and came out. */
export function StepsTimeline({ run }: { run: Run }) {
  const steps = useQuery({
    queryKey: ['runs', run.id, 'steps', run.status, run.remediation?.status],
    queryFn: async () =>
      (await api.GET('/v1/copilot/runs/{run_id}/steps', { params: { path: { run_id: run.id } } })).data!,
  })

  return (
    <Card title="What the copilot did">
      {steps.isPending && <Loading />}
      <ErrorMessage error={steps.error} />
      <ol className="space-y-1">
        {groupByNode(steps.data ?? []).map((group) => (
          <li key={group.node}>
            {group.step ? (
              <StepDetails step={group.step} />
            ) : (
              <p className="px-3 py-2 text-sm font-medium">{group.node} …</p>
            )}
            {group.tools.length > 0 && (
              <ol className="mt-1 ml-6 space-y-1">
                {group.tools.map((step) => (
                  <li key={step.id}>
                    <StepDetails step={step} />
                  </li>
                ))}
              </ol>
            )}
          </li>
        ))}
      </ol>
    </Card>
  )
}

function StepDetails({ step }: { step: RunStep }) {
  return (
    // Native <details>: keyboard and screen-reader support for expanding a step comes for free.
    <details className="rounded-md border border-border">
      <summary className="flex cursor-pointer items-center gap-3 px-3 py-2 text-sm">
        <span className={step.tool_name ? 'text-muted' : 'font-medium'}>{step.tool_name ?? step.node}</span>
        {step.error && <span className="text-danger">failed</span>}
        <span className="ml-auto font-mono text-xs text-muted">{step.duration_ms} ms</span>
      </summary>
      <div className="space-y-2 border-t border-border p-3 text-xs">
        {step.error && <p className="text-danger">{step.error}</p>}
        {step.input != null && <JsonBlock label="Input" value={step.input} />}
        {step.output != null && <JsonBlock label="Output" value={step.output} />}
        {step.trace_id && <p className="text-muted">Trace {step.trace_id} (open in Grafana → Explore → Tempo)</p>}
      </div>
    </details>
  )
}

interface NodeGroup {
  node: string
  /** The node's own step; missing while the node is still running (its tool calls are saved as they finish). */
  step?: RunStep
  tools: RunStep[]
  startedAt: number
}

/**
 * Steps are saved when they finish, so a node is saved after the tool and LLM calls inside it. Group the calls
 * under their node and order everything by when it started.
 */
function groupByNode(steps: RunStep[]): NodeGroup[] {
  const startedAt = (step: RunStep) => Date.parse(step.created_at) - step.duration_ms
  const groups = new Map<string, NodeGroup>()
  for (const step of [...steps].sort((a, b) => startedAt(a) - startedAt(b))) {
    const group = groups.get(step.node) ?? { node: step.node, tools: [], startedAt: startedAt(step) }
    if (step.tool_name) group.tools.push(step)
    else group.step = step
    group.startedAt = Math.min(group.startedAt, startedAt(step))
    groups.set(step.node, group)
  }
  return [...groups.values()].sort((a, b) => a.startedAt - b.startedAt)
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <p className="mb-1 font-medium">{label}</p>
      <pre className="max-h-80 overflow-auto rounded bg-canvas p-2 font-mono whitespace-pre-wrap">
        {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
      </pre>
    </div>
  )
}
