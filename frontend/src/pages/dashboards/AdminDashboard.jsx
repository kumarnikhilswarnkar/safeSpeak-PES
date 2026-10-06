import {
  AlarmClock,
  ArrowUpCircle,
  BarChart3,
  Bot,
  CheckCircle2,
  ClipboardList,
  FolderOpen,
  PieChart,
  ShieldAlert,
  Timer,
  TrendingUp,
  UserCog,
} from 'lucide-react'
import { useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { getOverview } from '../../api/insights.js'
import { useAuth } from '../../auth/AuthContext.jsx'
import { ROLE_LABEL } from '../../auth/roles.js'
import AppShell from '../../components/AppShell.jsx'
import AutomationPanel from '../../components/AutomationPanel.jsx'
import { COLORS, ConfidenceHistogram, DailyArea, Donut, GroupedBars, HorizontalBars, PRIORITY_COLORS } from '../../components/Charts.jsx'
import { Alert, Badge, Card, ErrorState, LoadingState, PageHeader, StatCard } from '../../components/ui.jsx'
import useLoader from '../../hooks/useLoader.js'
import { percent } from '../../utils/format.js'

const DECISION_LABELS = {
  AI_AUTO: 'AI · automatic',
  AI_PENDING_REVIEW: 'Awaiting human',
  HUMAN_ACCEPTED: 'Human accepted AI',
  HUMAN_OVERRIDDEN: 'Human overrode AI',
}
const DECISION_COLORS = {
  'AI · automatic': COLORS.brand,
  'Awaiting human': COLORS.violet,
  'Human accepted AI': COLORS.green,
  'Human overrode AI': COLORS.amber,
}

export default function AdminDashboard() {
  const { authRequest, user } = useAuth()
  const navigate = useNavigate()
  const loader = useCallback(() => getOverview(authRequest), [authRequest])
  const { data: o, error, loading, reload } = useLoader(loader)
  const readOnly = user.role === 'viewer'

  return (
    <AppShell>
      <PageHeader
        eyebrow={ROLE_LABEL[user.role]}
        title={readOnly ? 'Oversight dashboard' : 'Administration dashboard'}
        description="Live state of the grievance workflow: volumes, AI vs human decisions, deadlines, and the automatic TAT monitor."
        actions={
          <Link to="/concerns" className="btn-secondary">
            <ClipboardList className="size-4" /> All complaints
          </Link>
        }
      />
      {loading && !o ? (
        <LoadingState />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <StatCard label="Total complaints" value={o.totals.total} icon={ClipboardList} tone="brand" />
            <StatCard label="Open" value={o.totals.open} icon={FolderOpen} tone="slate" />
            <StatCard label="Resolved" value={o.totals.resolved} icon={CheckCircle2} tone="green" />
            <StatCard label="Overdue" value={o.totals.overdue} icon={AlarmClock} tone="red" onClick={() => navigate('/concerns?view=overdue')} />
            <StatCard label="Escalated" value={o.totals.escalated} icon={ArrowUpCircle} tone="accent" onClick={() => navigate('/concerns?view=escalated')} />
            <StatCard
              label="Human review cases"
              value={o.totals.ai_flagged_for_review}
              icon={UserCog}
              tone="violet"
              hint={`${percent(o.rates.human_review_rate)} of all`}
              onClick={() => navigate('/concerns?view=review')}
            />
          </div>

          {o.attention.length > 0 && (
            <Alert tone="red" icon={ShieldAlert} title={`${o.attention.length} complaint(s) need administrator attention`} className="mt-6">
              The escalation chain is exhausted for:{' '}
              {o.attention.map((a, i) => (
                <span key={a.complaint_id}>
                  {i > 0 && ', '}
                  <Link to={`/concerns/${a.complaint_id}`} className="font-mono font-medium underline">
                    {a.complaint_id}
                  </Link>
                </span>
              ))}
              . They stay with the highest authority.
            </Alert>
          )}

          <div className="mt-6 grid gap-6 xl:grid-cols-3">
            <AutomationPanel overview={o} canRun={!readOnly} onRan={reload} className="xl:col-span-1" />
            <Card title="Complaints submitted (14 days)" icon={TrendingUp} className="xl:col-span-2">
              <DailyArea data={o.per_day} />
            </Card>
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
            <Card title="Category distribution" icon={BarChart3} className="xl:col-span-2">
              <HorizontalBars data={o.by_category} />
            </Card>
            <Card title="Priority distribution" icon={PieChart}>
              <Donut data={o.by_priority} colors={PRIORITY_COLORS} centerValue={o.totals.total} centerLabel="complaints" />
            </Card>
            <Card title="AI vs human decisions" icon={Bot} subtitle="Where each complaint's final category/priority came from">
              <Donut
                data={o.decision_sources.map((d) => ({ label: DECISION_LABELS[d.label], count: d.count }))}
                colors={DECISION_COLORS}
                centerValue={percent(o.rates.override_rate)}
                centerLabel="override rate"
              />
              <p className="mt-2 text-xs text-slate-500">
                Of {o.ai_vs_human.reviewed} human decisions: category changed {o.ai_vs_human.category_changed}×, priority changed{' '}
                {o.ai_vs_human.priority_changed}×.
              </p>
            </Card>
            <Card title="AI confidence distribution" icon={BarChart3} subtitle={`Violet bins are below the ${percent(o.threshold)} review threshold`}>
              <ConfidenceHistogram bins={o.confidence_histogram} threshold={o.threshold} />
            </Card>
            <Card title="Escalations & resolution time" icon={Timer}>
              <GroupedBars
                height={180}
                data={[{ label: 'Escalations', automatic: o.escalations.automatic, manual: o.escalations.manual, exhausted: o.escalations.exhausted }]}
                series={[
                  { key: 'automatic', name: 'Automatic', color: COLORS.brand },
                  { key: 'manual', name: 'Manual', color: COLORS.slate },
                  { key: 'exhausted', name: 'Chain exhausted', color: COLORS.red },
                ]}
              />
              <div className="mt-3 grid grid-cols-2 gap-3 border-t border-slate-100 pt-3 text-sm">
                <div>
                  <p className="text-xs text-slate-500">Mean resolution time</p>
                  <p className="font-semibold tabular-nums">{o.resolution_hours.mean != null ? `${o.resolution_hours.mean} h` : '—'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Median resolution time</p>
                  <p className="font-semibold tabular-nums">{o.resolution_hours.median != null ? `${o.resolution_hours.median} h` : '—'}</p>
                </div>
              </div>
              <p className="mt-2 text-xs text-slate-500">
                <Badge tone="slate">{o.resolution_hours.count}</Badge> resolved complaints in scope.
              </p>
            </Card>
          </div>
        </>
      )}
    </AppShell>
  )
}
