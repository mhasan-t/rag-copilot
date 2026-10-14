import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'

import { api, ApiError } from '../api/client'
import { Button, Card, ErrorMessage, inputClasses } from '../components/ui'

const EXAMPLES = [
  'Why is the payments service showing a latency spike?',
  'Is the payments service healthy right now?',
  'How do I roll back a deployment?',
]

export function AskPage() {
  const navigate = useNavigate()
  const [question, setQuestion] = useState('')
  const ask = useMutation({
    mutationFn: async (text: string) => (await api.POST('/v1/copilot/runs', { body: { question: text } })).data!,
    onSuccess: (run) => navigate(`/runs/${run.id}`),
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    ask.mutate(question)
  }

  return (
    <Card title="Ask the copilot">
      <form onSubmit={submit} className="space-y-3">
        <label className="block space-y-1 text-sm">
          <span className="sr-only">Question</span>
          <textarea
            className={`${inputClasses} min-h-24`}
            placeholder="What's going on with a service, or how do we do something?"
            required
            minLength={3}
            maxLength={2000}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
        </label>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              className="rounded-full border border-border px-3 py-1 text-xs text-muted hover:text-ink"
              onClick={() => setQuestion(example)}
            >
              {example}
            </button>
          ))}
        </div>
        <ErrorMessage error={ask.error} />
        <FailedRunLink error={ask.error} />
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={ask.isPending}>
            {ask.isPending ? 'Investigating…' : 'Ask'}
          </Button>
          {ask.isPending && (
            <span role="status" className="text-sm text-muted">
              Gathering evidence and asking the model; this can take a minute.
            </span>
          )}
        </div>
      </form>
    </Card>
  )
}

/** A run that failed (e.g. the LLM was unreachable) is still stored, with its steps; link to it. */
function FailedRunLink({ error }: { error: unknown }) {
  const runId = error instanceof ApiError ? error.details?.run_id : undefined
  if (typeof runId !== 'string') return null
  return (
    <Link to={`/runs/${runId}`} className="text-sm text-brand underline">
      See what the failed run did
    </Link>
  )
}
