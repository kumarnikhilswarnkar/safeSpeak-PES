import { FilePlus2 } from 'lucide-react'
import { useCallback, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { listInScope, listMine, listQueue } from '../../api/concerns.js'
import { useAuth } from '../../auth/AuthContext.jsx'
import AppShell from '../../components/AppShell.jsx'
import ComplaintTable from '../../components/ComplaintTable.jsx'
import { ErrorState, LoadingState, PageHeader, Tabs } from '../../components/ui.jsx'
import useLoader from '../../hooks/useLoader.js'

function ListBody({ loader, render }) {
  const { data, error, loading, reload } = useLoader(loader)
  if (loading && !data) return <LoadingState />
  if (error) return <ErrorState error={error} onRetry={reload} />
  return render(data)
}

export function MyComplaintsPage() {
  const { authRequest } = useAuth()
  const loader = useCallback(() => listMine(authRequest), [authRequest])
  return (
    <AppShell>
      <PageHeader
        eyebrow="Complainant"
        title="My complaints"
        description="Everything you have submitted, with its current stage and deadline."
        actions={
          <Link to="/concerns/new" className="btn-accent">
            <FilePlus2 className="size-4" /> New complaint
          </Link>
        }
      />
      <div className="card overflow-hidden">
        <ListBody
          loader={loader}
          render={(rows) => (
            <ComplaintTable
              complaints={rows}
              columns={['decision', 'assignee']}
              emptyTitle="You have not submitted any complaints"
              emptyDescription="Use “New complaint” to report a concern."
            />
          )}
        />
      </div>
    </AppShell>
  )
}

export const QUEUE_TABS = {
  review: { label: 'Needs human review', test: (c) => c.status === 'PENDING_REVIEW' },
  low: { label: 'Low confidence', test: (c) => c.ai.confidence < c.ai.threshold },
  overdue: { label: 'Overdue', test: (c) => c.tat.state === 'OVERDUE' },
  escalated: { label: 'Escalated to me', test: (c) => c.escalated },
  all: { label: 'All assigned', test: () => true },
}

export function ReviewQueuePage() {
  const { authRequest } = useAuth()
  const [params, setParams] = useSearchParams()
  const tab = QUEUE_TABS[params.get('tab')] ? params.get('tab') : 'review'
  const loader = useCallback(() => listQueue(authRequest), [authRequest])
  return (
    <AppShell>
      <PageHeader
        eyebrow="Authority"
        title="Review queue"
        description="Open complaints assigned to you. “Needs human review” are AI recommendations waiting for your decision; nothing in that tab is final yet."
      />
      <ListBody
        loader={loader}
        render={(rows) => (
          <div className="card overflow-hidden">
            <div className="px-3 pt-2">
              <Tabs
                value={tab}
                onChange={(v) => setParams({ tab: v })}
                tabs={Object.entries(QUEUE_TABS).map(([value, t]) => ({ value, label: t.label, count: rows.filter(t.test).length }))}
              />
            </div>
            <ComplaintTable
              complaints={rows.filter(QUEUE_TABS[tab].test)}
              columns={['confidence', 'complainant']}
              defaultSort="deadline"
              emptyTitle="Nothing here"
              emptyDescription="No complaints in this view need your attention."
            />
          </div>
        )}
      />
    </AppShell>
  )
}

export function AllComplaintsPage() {
  const { authRequest } = useAuth()
  const loader = useCallback(() => listInScope(authRequest), [authRequest])
  const [params] = useSearchParams()
  const preset = params.get('view')
  const views = {
    overdue: (c) => c.tat.state === 'OVERDUE',
    escalated: (c) => c.escalated,
    review: (c) => c.status === 'PENDING_REVIEW',
    attention: (c) => c.breached_at_top && c.status !== 'RESOLVED',
  }
  return (
    <AppShell>
      <PageHeader
        eyebrow="Read-only"
        title="All complaints"
        description="Every complaint in your scope. This view is read-only: only the assigned authority can act on a complaint."
      />
      <div className="card overflow-hidden">
        <ListBody
          loader={loader}
          render={(rows) => (
            <ComplaintTable
              complaints={views[preset] ? rows.filter(views[preset]) : rows}
              columns={['confidence', 'decision', 'assignee']}
              emptyTitle="No complaints in your scope yet"
            />
          )}
        />
      </div>
    </AppShell>
  )
}
