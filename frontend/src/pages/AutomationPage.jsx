import { ArrowRight, Clock, GitBranch, Settings2 } from 'lucide-react'
import { useCallback } from 'react'

import { useAuth } from '../auth/AuthContext.jsx'
import AppShell from '../components/AppShell.jsx'
import AutomationPanel from '../components/AutomationPanel.jsx'
import { Badge, Card, ErrorState, LoadingState, PageHeader } from '../components/ui.jsx'
import useLoader from '../hooks/useLoader.js'
import { SCOPE_LABEL } from '../utils/format.js'

const getRules = (authRequest) => authRequest('/system/rules')
const getOverviewSafe = (authRequest) => authRequest('/analytics/overview')

export default function AutomationPage() {
  const { authRequest, user } = useAuth()
  const loader = useCallback(
    () => Promise.all([getRules(authRequest), getOverviewSafe(authRequest)]).then(([rules, overview]) => ({ rules, overview })),
    [authRequest],
  )
  const { data, error, loading, reload } = useLoader(loader)
  const canRun = user.permissions.includes('manage_rules_and_settings')

  return (
    <AppShell>
      <PageHeader
        eyebrow="Automation"
        title="TAT monitoring & escalation"
        description="Deadlines are watched by a background job, not by a person. When an open complaint passes its deadline, the job escalates it to the next level of its chain, assigns the new authority, sets a new deadline and writes the audit trail."
      />
      {loading && !data ? (
        <LoadingState />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : (
        <div className="grid gap-6 xl:grid-cols-3">
          <div className="min-w-0 space-y-6">
            <AutomationPanel overview={data.overview} canRun={canRun} onRan={reload} showRuns />
            <Card title="What one check does" icon={Settings2}>
              <ol className="space-y-2 text-sm text-slate-600">
                {[
                  'Find open complaints whose deadline has passed (not already exhausted).',
                  'Record “TAT breached” in the audit trail.',
                  'Route to the next level of the complaint’s chain (skipping levels with no active authority).',
                  'Assign the new authority and compute a new deadline from the TAT rules.',
                  'Record “Escalated” with old → new level, assignee and deadline.',
                  'At the top of the chain: mark “exhausted”, keep it with the highest authority, flag for the administrator.',
                ].map((t, i) => (
                  <li key={t} className="flex gap-2.5">
                    <span className="grid size-5 shrink-0 place-items-center rounded-full bg-brand-50 text-[11px] font-semibold text-brand-700">{i + 1}</span>
                    {t}
                  </li>
                ))}
              </ol>
            </Card>
          </div>
          <div className="min-w-0 space-y-6 xl:col-span-2">
            <Card title="Escalation chains (configuration)" icon={GitBranch} subtitle="Database rows (sample values for the prototype, not the real PES hierarchy)">
              <Chains rules={data.rules.escalation_rules} />
            </Card>
            <Card title="TAT rules (configuration)" icon={Clock} subtitle="Most specific matching rule wins; a missing rule is an explicit error, never a hidden default" bodyClassName="p-0">
              <TatRules rules={data.rules.tat_rules} />
            </Card>
          </div>
        </div>
      )}
    </AppShell>
  )
}

function Chains({ rules }) {
  const groups = {}
  for (const r of rules) (groups[r.category ?? 'Default (all other categories)'] ??= []).push(r)
  return (
    <div className="space-y-4">
      {Object.entries(groups).map(([name, steps]) => (
        <div key={name}>
          <p className="mb-2 text-sm font-medium text-slate-800">{name}</p>
          <div className="flex flex-wrap items-center gap-2">
            {steps.map((s, i) => (
              <span key={s.id} className="flex items-center gap-2">
                {i > 0 && <ArrowRight className="size-4 text-slate-300" />}
                <span className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs">
                  <span className="font-semibold text-brand-700">Level {s.level}</span> · {s.label}
                  <span className="block text-slate-500">
                    {SCOPE_LABEL[s.target_scope]}
                    {s.target_department ? ` (${s.target_department})` : ''}
                  </span>
                </span>
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function TatRules({ rules }) {
  return (
    <div className="max-h-[28rem] overflow-y-auto">
      <table className="min-w-full divide-y divide-slate-100 text-sm">
        <thead className="sticky top-0 bg-slate-50">
          <tr>
            <th className="table-head">Stage</th>
            <th className="table-head">Category</th>
            <th className="table-head">Priority</th>
            <th className="table-head">Level</th>
            <th className="table-head text-right">Hours</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rules.map((r) => (
            <tr key={r.id}>
              <td className="table-cell">
                <Badge tone={r.stage === 'REVIEW' ? 'violet' : 'brand'}>{r.stage === 'REVIEW' ? 'Human review' : 'Resolution'}</Badge>
              </td>
              <td className="table-cell text-slate-600">{r.category ?? 'any'}</td>
              <td className="table-cell text-slate-600">{r.priority ?? 'any'}</td>
              <td className="table-cell text-slate-600">{r.escalation_level ? `L${r.escalation_level}` : 'any'}</td>
              <td className="table-cell text-right font-medium tabular-nums">{r.tat_hours}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
