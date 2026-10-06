import { AlarmClock, ArrowUpCircle, BarChart3, Gauge, Inbox, PieChart, TriangleAlert, UserCog } from 'lucide-react'
import { useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { listQueue } from '../../api/concerns.js'
import { getOverview } from '../../api/insights.js'
import { useAuth } from '../../auth/AuthContext.jsx'
import { ROLE_LABEL } from '../../auth/roles.js'
import AppShell from '../../components/AppShell.jsx'
import { ConfidenceHistogram, Donut, HorizontalBars, PRIORITY_COLORS } from '../../components/Charts.jsx'
import ComplaintTable from '../../components/ComplaintTable.jsx'
import { Card, ErrorState, LoadingState, PageHeader, StatCard } from '../../components/ui.jsx'
import useLoader from '../../hooks/useLoader.js'
import { percent } from '../../utils/format.js'
import { QUEUE_TABS } from '../complaints/ComplaintListPages.jsx'

export default function ReviewerDashboard() {
  const { authRequest, user } = useAuth()
  const navigate = useNavigate()
  const loader = useCallback(
    () => Promise.all([listQueue(authRequest), getOverview(authRequest)]).then(([queue, overview]) => ({ queue, overview })),
    [authRequest],
  )
  const { data, error, loading, reload } = useLoader(loader)

  return (
    <AppShell>
      <PageHeader
        eyebrow={`${ROLE_LABEL[user.role]}${user.authority_level ? ` · L${user.authority_level}` : ''}`}
        title="Reviewer dashboard"
        description="AI recommendations waiting for your decision, deadlines at risk, and how the AI is performing on complaints assigned to you."
        actions={
          <Link to="/review" className="btn-primary">
            <Inbox className="size-4" /> Open review queue
          </Link>
        }
      />
      {loading && !data ? (
        <LoadingState />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : (
        <Body data={data} go={(tab) => navigate(`/review?tab=${tab}`)} />
      )}
    </AppShell>
  )
}

function Body({ data: { queue, overview }, go }) {
  const count = (tab) => queue.filter(QUEUE_TABS[tab].test).length
  const action = queue
    .filter((c) => c.status === 'PENDING_REVIEW' || c.tat.state === 'OVERDUE' || c.tat.state === 'DUE_SOON')
    .slice(0, 8)
  const t = overview.totals
  return (
    <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <StatCard label="Pending human reviews" value={count('review')} icon={UserCog} tone="violet" onClick={() => go('review')} hint="Your decision needed" />
        <StatCard label="Low-confidence complaints" value={count('low')} icon={Gauge} tone="amber" onClick={() => go('low')} hint={`Below ${percent(overview.threshold)} threshold`} />
        <StatCard label="Assigned to me (open)" value={count('all')} icon={Inbox} tone="brand" onClick={() => go('all')} />
        <StatCard label="Overdue" value={count('overdue')} icon={AlarmClock} tone="red" onClick={() => go('overdue')} hint="Will escalate automatically" />
        <StatCard label="Escalated to me" value={count('escalated')} icon={ArrowUpCircle} tone="accent" onClick={() => go('escalated')} />
      </div>

      <Card
        title="Requires your action"
        subtitle="Pending human reviews and deadlines at risk, soonest first"
        icon={TriangleAlert}
        className="mt-6"
        bodyClassName="p-0"
      >
        <ComplaintTable
          complaints={action}
          toolbar={false}
          defaultSort="deadline"
          columns={['confidence', 'complainant']}
          emptyTitle="You are all caught up"
          emptyDescription="No pending reviews or deadlines at risk."
        />
      </Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-2 xl:grid-cols-4">
        <Card title="Human review rate" icon={UserCog} subtitle="Share of your complaints the AI sent to a person">
          <p className="text-4xl font-semibold tracking-tight text-slate-900 tabular-nums">{percent(overview.rates.human_review_rate)}</p>
          <p className="mt-1 text-sm text-slate-500">
            {t.ai_flagged_for_review} of {t.total} complaints needed review; {t.auto_routed} were routed automatically.
          </p>
          <div className="mt-4 space-y-1 text-sm">
            <p className="flex justify-between">
              <span className="text-slate-500">You accepted the AI</span>
              <span className="font-medium tabular-nums">{overview.ai_vs_human.accepted}</span>
            </p>
            <p className="flex justify-between">
              <span className="text-slate-500">You overrode the AI</span>
              <span className="font-medium tabular-nums">{overview.ai_vs_human.overridden}</span>
            </p>
          </div>
        </Card>
        <Card title="AI confidence distribution" icon={BarChart3} subtitle="Violet = below the review threshold" className="xl:col-span-2">
          <ConfidenceHistogram bins={overview.confidence_histogram} threshold={overview.threshold} />
        </Card>
        <Card title="Priority mix" icon={PieChart}>
          <Donut data={overview.by_priority} colors={PRIORITY_COLORS} centerValue={t.total} centerLabel="complaints" />
        </Card>
        <Card title="Complaints by category" icon={BarChart3} className="lg:col-span-2 xl:col-span-4">
          <HorizontalBars data={overview.by_category} height={240} />
        </Card>
      </div>
    </>
  )
}
