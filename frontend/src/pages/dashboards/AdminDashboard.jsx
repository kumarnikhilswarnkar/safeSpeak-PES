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
import { Alert, Badge, Card, EmptyState, ErrorState, LoadingState, PageHeader, StatCard } from '../../components/ui.jsx'
import useLoader from '../../hooks/useLoader.js'
import { formatDateTime, percent } from '../../utils/format.js'

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
          <div className="stagger grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {/* Definitions match analytics_service (tested in test_analytics_definitions.py). */}
            <StatCard label="Total complaints" value={o.totals.total} icon={ClipboardList} tone="brand" hint="In your scope" />
            <StatCard label="Open" value={o.totals.open} icon={FolderOpen} tone="slate" hint="Not yet resolved" />
            <StatCard label="Resolved" value={o.totals.resolved} icon={CheckCircle2} tone="green" hint="Closed with a note" />
            <StatCard
              label="Overdue"
              value={o.totals.overdue}
              icon={AlarmClock}
              tone="red"
              hint={o.totals.needs_admin_attention ? `Open, past deadline · ${o.totals.needs_admin_attention} at end of chain` : 'Open, past deadline'}
              onClick={() => navigate('/concerns?view=overdue')}
            />
            <StatCard
              label="Escalated"
              value={o.totals.escalated}
              icon={ArrowUpCircle}
              tone="accent"
              hint={`Complaints escalated at least once · ${o.escalations.total} escalation events`}
              onClick={() => navigate('/concerns?view=escalated')}
            />
            <StatCard
              label="AI-flagged for review"
              value={o.totals.ai_flagged_for_review}
              icon={UserCog}
              tone="violet"
              hint={`${percent(o.rates.human_review_rate)} of all · ${o.totals.pending_review} awaiting review now`}
              onClick={() => navigate('/concerns?view=review')}
            />
          </div>

          {o.attention.length > 0 && (
            <Alert tone="red" icon={ShieldAlert} title={`${o.attention.length} complaint(s) need administrator attention`} className="mt-6">
              The escalation chain is exhausted for the complaints below. Open each one and use the Administrator intervention
              section to reassign it with a reason and a new deadline.
              <ul className="mt-2 flex flex-wrap gap-2">
                {o.attention.map((a) => (
                  <li key={a.complaint_id}>
                    <Link
                      to={`/concerns/${a.complaint_id}`}
                      className="inline-flex min-h-11 items-center rounded-md bg-white/70 px-3 font-mono text-xs font-medium text-red-800 ring-1 ring-red-200 transition hover:bg-white sm:min-h-8"
                    >
                      {a.complaint_id}
                    </Link>
                  </li>
                ))}
              </ul>
            </Alert>
          )}

          <div className="stagger mt-6 grid gap-6 xl:grid-cols-3">
            <AutomationPanel overview={o} canRun={!readOnly} onRan={reload} className="xl:col-span-1" />
            <Card title="Complaints submitted (last 14 days)" subtitle="Per calendar day, Indian Standard Time" icon={TrendingUp} className="xl:col-span-2">
              {o.per_day.some((d) => d.count > 0) ? (
                <DailyArea data={o.per_day} />
              ) : (
                <EmptyState
                  icon={TrendingUp}
                  title="No complaints were submitted in the last 14 days"
                  description={
                    o.latest_submission_at
                      ? `The most recent complaint in your scope was submitted on ${formatDateTime(o.latest_submission_at)}.`
                      : 'No complaints have been submitted yet.'
                  }
                />
              )}
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
            <Card
              title="AI confidence distribution"
              icon={BarChart3}
              subtitle={`Overall confidence = the lower of category and priority confidence. Violet bins are below the ${percent(o.threshold)} category threshold${o.priority_threshold != null ? `; priority uses its own ${percent(o.priority_threshold)} threshold` : ''}.`}
            >
              <ConfidenceHistogram bins={o.confidence_histogram} threshold={o.threshold} />
            </Card>
            <Card title="Escalations & resolution time" subtitle="Escalation events, all time: one complaint can be escalated more than once" icon={Timer}>
              <GroupedBars
                height={180}
                data={[{ label: 'Escalations', automatic: o.escalations.automatic, manual: o.escalations.manual, exhausted: o.escalations.exhausted }]}
                series={[
                  { key: 'automatic', name: 'Automatic', color: COLORS.brand },
                  { key: 'manual', name: 'Manual', color: COLORS.slate },
                  { key: 'exhausted', name: 'Chain exhausted', color: COLORS.red },
                ]}
              />
              <p className="mt-2 text-xs text-slate-500">
                Administrator interventions (reassignments after an exhausted chain): <strong>{o.escalations.admin_interventions ?? 0}</strong>
              </p>
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
