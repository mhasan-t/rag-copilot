import { useInfiniteQuery } from '@tanstack/react-query'
import { Link } from 'react-router'

import { api } from '../api/client'
import { Badge, Button, Card, ErrorMessage, Time, Loading } from '../components/ui'

const PAGE_SIZE = 20

export function RunsPage() {
  const runs = useInfiniteQuery({
    queryKey: ['runs'],
    queryFn: async ({ pageParam }) =>
      (await api.GET('/v1/copilot/runs', { params: { query: { limit: PAGE_SIZE, offset: pageParam } } })).data!,
    initialPageParam: 0,
    getNextPageParam: (lastPage, pages) => (lastPage.length === PAGE_SIZE ? pages.length * PAGE_SIZE : undefined),
  })

  if (runs.isPending) return <Loading />
  const all = runs.data?.pages.flat() ?? []
  return (
    <Card title="Runs">
      <ErrorMessage error={runs.error} />
      {all.length === 0 ? (
        <p className="text-sm text-muted">
          No runs yet.{' '}
          <Link to="/" className="text-brand underline">
            Ask a question
          </Link>
          .
        </p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead className="text-muted">
            <tr>
              <th className="py-2 font-medium">Question</th>
              <th className="py-2 font-medium">Status</th>
              <th className="py-2 font-medium">Asked</th>
            </tr>
          </thead>
          <tbody>
            {all.map((run) => (
              <tr key={run.id} className="border-t border-border">
                <td className="py-2 pr-4">
                  <Link to={`/runs/${run.id}`} className="text-brand hover:underline">
                    {run.question}
                  </Link>
                </td>
                <td className="py-2 pr-4">
                  <Badge value={run.status} />
                </td>
                <td className="py-2 whitespace-nowrap text-muted">
                  <Time value={run.created_at} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {runs.hasNextPage && (
        <Button
          variant="secondary"
          className="mt-3"
          onClick={() => runs.fetchNextPage()}
          disabled={runs.isFetchingNextPage}
        >
          Load more
        </Button>
      )}
    </Card>
  )
}
