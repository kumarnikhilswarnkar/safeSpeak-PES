import { BarChart3, Database, FlaskConical, Gauge, Grid3x3, SlidersHorizontal, TriangleAlert } from 'lucide-react'
import { useCallback, useState } from 'react'

import { getEvaluation } from '../api/insights.js'
import { useAuth } from '../auth/AuthContext.jsx'
import AppShell from '../components/AppShell.jsx'
import { COLORS, GroupedBars, SelectiveCurve } from '../components/Charts.jsx'
import { Alert, Badge, Card, ErrorState, LoadingState, PageHeader, Tabs, cx } from '../components/ui.jsx'
import useLoader from '../hooks/useLoader.js'
import { percent } from '../utils/format.js'

const METHOD_LABEL = { raw: 'Raw softmax', temperature: 'Temperature scaling', sigmoid: 'Per-class sigmoid' }

export default function ResearchPage() {
  const { authRequest } = useAuth()
  const loader = useCallback(() => getEvaluation(authRequest), [authRequest])
  const { data, error, loading, reload } = useLoader(loader)
  const [task, setTask] = useState('category')

  return (
    <AppShell>
      <PageHeader
        eyebrow="Research"
        title="AI evaluation"
        description="How the local triage models were chosen: every candidate on the same grouped cross-validation folds, a pre-declared selection rule, calibration and thresholds chosen per task, and one final check on a holdout never used for any decision. All numbers are produced by ml/scripts/run_experiments.py."
      />
      {loading && !data ? (
        <LoadingState label="Loading evaluation report…" />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : (
        <Report r={data} task={task} setTask={setTask} />
      )}
    </AppShell>
  )
}

function titleOf(rows, name) {
  return rows.find((x) => x.model === name)?.title ?? name
}

function Report({ r, task, setTask }) {
  const t = r.tasks[task]
  const rows = t.comparison
  const selected = t.selection.selected
  const d = r.dataset
  const liveThreshold = task === 'category' ? r.live.threshold : r.live.priority_threshold
  const liveSource = task === 'category' ? r.live.threshold_source : r.live.priority_threshold_source
  return (
    <div className="space-y-6">
      <Alert tone="amber" icon={Database} title="Synthetic / controlled dataset">
        {d.records} AI-generated records in {d.groups} paraphrase groups. Development {d.partitions.development.records} records,
        holdout {d.partitions.holdout.records} records ({d.partitions.holdout.groups} whole groups). Results show how the method behaves on
        controlled data, not how it would perform on real campus complaints.
      </Alert>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Fact label="Models in use" value={r.live.model ?? '—'} hint={`Category: ${titleOf(r.tasks.category.comparison, r.tasks.category.selection.selected)}`} />
        <Fact label={`${task === 'category' ? 'Category' : 'Priority'} threshold in use`} value={liveThreshold == null ? '—' : percent(liveThreshold)} hint={liveSource === 'CONFIG' ? 'Set in configuration' : 'Chosen on grouped cross-validation'} />
        <Fact label="Selection protocol" value="5 × 5 grouped CV" hint="25 fits per model; paraphrase groups never split" />
        <Fact label="Final check" value="Holdout, used once" hint={`${d.partitions.holdout.records} records; never used to choose`} />
      </div>

      {r.setfit_pilot && (
        <p className="text-xs text-slate-500">
          SetFit (candidate 9) feasibility gate: <strong>{r.setfit_pilot.status}</strong>
          {r.setfit_pilot.error ? ` — ${r.setfit_pilot.error}.` : '.'}
        </p>
      )}

      <div className="card">
        <div className="px-4 pt-2">
          <Tabs
            value={task}
            onChange={setTask}
            tabs={[
              { value: 'category', label: 'Category model' },
              { value: 'priority', label: 'Priority model' },
            ]}
          />
        </div>
        <div className="space-y-6 p-5">
          <SelectionSummary t={t} rows={rows} />
          <ComparisonTable rows={rows} />
          <div className="grid gap-6 xl:grid-cols-2">
            <Card title="Per-class F1 on the holdout" icon={BarChart3} subtitle="Frozen keyword baseline vs selected model">
              <GroupedBars
                percent
                data={Object.keys(t.selected_holdout.per_class).map((label) => ({
                  label,
                  keyword: t.keyword_holdout?.per_class[label]?.f1 ?? 0,
                  model: t.selected_holdout.per_class[label].f1,
                }))}
                series={[
                  { key: 'keyword', name: 'Keyword baseline', color: COLORS.slate },
                  { key: 'model', name: 'Selected model', color: COLORS.brand },
                ]}
              />
            </Card>
            <Card title="Confusion matrix (selected model, holdout)" icon={Grid3x3} subtitle="Rows = true label, columns = predicted">
              <Confusion cm={t.selected_holdout.confusion_matrix} />
            </Card>
          </div>
          <div className="grid gap-6 xl:grid-cols-3">
            <Card title="Confidence threshold" icon={SlidersHorizontal} subtitle="Development out-of-fold, calibrated; dotted line = 80% target" className="xl:col-span-2">
              <SelectiveCurve data={t.thresholds.curve} threshold={t.thresholds.threshold} />
              <p className="mt-2 text-xs text-slate-500">
                Rule: {t.thresholds.rule}.{' '}
                {t.thresholds.met
                  ? `Chosen ${t.thresholds.threshold}: ${percent(t.thresholds.at_threshold.automatic_rate)} automatic, ${percent(t.thresholds.at_threshold.automatic_accuracy, 1)} of those correct.`
                  : 'No threshold met the rule, so every complaint goes to human review for this task.'}
              </p>
            </Card>
            <Calibration t={t} />
          </div>
        </div>
      </div>

      <Card title="Threshold trade-off on the holdout" icon={SlidersHorizontal} subtitle="Reported only. Automatic = confidence at or above the threshold for this task" bodyClassName="p-0">
        <ThresholdTable rows={t.thresholds.holdout_table} chosen={t.thresholds.threshold} />
      </Card>

      <Card title="Findings (generated from the reports)" icon={FlaskConical}>
        <Findings r={r} />
      </Card>
    </div>
  )
}

function Fact({ label, value, hint }) {
  return (
    <div className="card p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-0.5 truncate text-lg font-semibold text-slate-900" title={value}>
        {value}
      </p>
      <p className="mt-0.5 truncate text-xs text-slate-500">{hint}</p>
    </div>
  )
}

function SelectionSummary({ t, rows }) {
  const s = t.selection
  const sel = rows.find((x) => x.model === s.selected)
  const kw = rows.find((x) => x.model === 'keyword_baseline')
  const items = [
    ['CV macro-F1 (mean ± SD)', kw.cv.macro_f1.mean, sel.cv.macro_f1.mean, `± ${(sel.cv.macro_f1.sd * 100).toFixed(1)}`],
    ['Holdout accuracy', kw.holdout.accuracy, sel.holdout.accuracy, ''],
    ['Holdout macro-F1', kw.holdout.macro_f1, sel.holdout.macro_f1, ''],
  ]
  return (
    <div>
      <p className="mb-3 text-sm text-slate-600">
        Selected by the cross-validation rule: <strong className="text-slate-900">{sel.title}</strong>.{' '}
        {s.beats_keyword_baseline ? 'It beats' : 'It does not beat'} the frozen keyword baseline in cross-validation
        {s.margin_over_keyword_in_sd != null ? ` (margin ${s.margin_over_keyword_in_sd} SD)` : ''}.
      </p>
      {s.deployment_constraint && (
        <p className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          <strong>Deployment constraint (added after the first run, disclosed):</strong> {s.deployment_constraint.rule}.{' '}
          {s.constraint_changed_selection
            ? `Without it, the same rule selects ${titleOf(rows, s.unconstrained.selected)} (CV macro-F1 ${percent(s.unconstrained.winner_cv_macro_f1.mean, 1)} ± ${(s.unconstrained.winner_cv_macro_f1.sd * 100).toFixed(1)}; ${s.unconstrained.beats_keyword_baseline ? 'beats' : 'does not beat'} the keyword baseline). Reason: ${s.deployment_constraint.reason}.`
            : 'It did not change the selection for this task.'}
        </p>
      )}
      <div className="grid gap-3 md:grid-cols-3">
        {items.map(([label, a, b, extra]) => {
          const diff = b - a
          return (
            <div key={label} className="rounded-lg border border-slate-200 p-4">
              <p className="text-xs text-slate-500">{label}</p>
              <div className="mt-2 flex items-end justify-between gap-2">
                <div>
                  <p className="text-xs text-slate-400">Keyword</p>
                  <p className="text-lg font-semibold text-slate-500 tabular-nums">{percent(a, 1)}</p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-slate-400">Selected</p>
                  <p className="text-lg font-semibold text-slate-900 tabular-nums">
                    {percent(b, 1)} <span className="text-xs font-normal text-slate-500">{extra}</span>
                  </p>
                </div>
              </div>
              <p className={cx('mt-1 text-xs font-medium tabular-nums', diff >= 0 ? 'text-emerald-700' : 'text-red-600')}>
                {diff >= 0 ? '+' : ''}
                {(diff * 100).toFixed(1)} points
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ComparisonTable({ rows }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr>
            <th className="table-head">#</th>
            <th className="table-head">Model</th>
            <th className="table-head text-right">CV macro-F1 (mean ± SD)</th>
            <th className="table-head text-right">CV accuracy</th>
            <th className="table-head text-right">Holdout accuracy</th>
            <th className="table-head text-right">Holdout macro-F1</th>
            <th className="table-head text-right">Holdout weighted-F1</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((m) => (
            <tr key={m.model} className={m.selected ? 'bg-brand-50/60' : m.model === 'keyword_baseline' ? 'bg-slate-50/60' : ''}>
              <td className="table-cell text-slate-500 tabular-nums">{m.number}</td>
              <td className="table-cell">
                <span className="font-medium text-slate-900">{m.title}</span>
                {m.selected && <Badge tone="brand" className="ml-2">selected by CV</Badge>}
                {m.status === 'EVALUATED' && !m.selectable && <Badge tone="slate" className="ml-2">baseline</Badge>}
              </td>
              {m.status !== 'EVALUATED' ? (
                <td className="table-cell text-slate-500" colSpan={5}>
                  Not evaluated — {m.reason}
                </td>
              ) : (
                <>
                  <td className="table-cell text-right font-medium tabular-nums">
                    {percent(m.cv.macro_f1.mean, 1)} ± {(m.cv.macro_f1.sd * 100).toFixed(1)}
                  </td>
                  <td className="table-cell text-right tabular-nums">{percent(m.cv.accuracy.mean, 1)}</td>
                  <td className="table-cell text-right tabular-nums">{percent(m.holdout.accuracy, 1)}</td>
                  <td className="table-cell text-right tabular-nums">{percent(m.holdout.macro_f1, 1)}</td>
                  <td className="table-cell text-right tabular-nums">{percent(m.holdout.weighted_f1, 1)}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Calibration({ t }) {
  const c = t.calibration
  const ho = t.holdout_calibration
  const chosen = c.selected_method
  return (
    <Card title="Calibration" icon={Gauge} subtitle="Cross-fitted on development; lower log-loss / ECE is better">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-slate-500">
            <th className="pb-1 text-left font-medium">Method</th>
            <th className="pb-1 text-right font-medium">Log-loss</th>
            <th className="pb-1 text-right font-medium">ECE</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(c.methods).map(([m, q]) => (
            <tr key={m} className={m === chosen ? 'font-semibold' : ''}>
              <td className="py-0.5">
                {METHOD_LABEL[m] ?? m} {m === chosen && <Badge tone="brand" className="ml-1">used</Badge>}
              </td>
              <td className="py-0.5 text-right tabular-nums">{q.nll}</td>
              <td className="py-0.5 text-right tabular-nums">{q.ece}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-xs text-slate-500">
        Holdout ECE: raw {ho.raw.ece}
        {chosen !== 'raw' && ho[chosen] ? ` → ${METHOD_LABEL[chosen].toLowerCase()} ${ho[chosen].ece}` : ' (raw kept: no method improved development log-loss)'}.
      </p>
    </Card>
  )
}

function Confusion({ cm }) {
  const max = Math.max(1, ...cm.matrix.flat())
  const short = (l) => l.split(/[ /]/)[0].slice(0, 8)
  return (
    <div className="overflow-x-auto">
      <table className="text-xs">
        <thead>
          <tr>
            <th />
            {cm.labels.map((l) => (
              <th key={l} className="px-1 pb-1 text-center font-medium text-slate-500" title={l}>
                {short(l)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cm.matrix.map((row, i) => (
            <tr key={cm.labels[i]}>
              <th className="pr-2 text-right font-medium whitespace-nowrap text-slate-600" title={cm.labels[i]}>
                {cm.labels[i]}
              </th>
              {row.map((v, j) => (
                <td
                  key={j}
                  className={cx('size-9 min-w-9 text-center tabular-nums', i === j ? 'font-semibold' : '')}
                  style={{
                    background: v ? (i === j ? `rgba(31,74,168,${0.15 + (0.75 * v) / max})` : `rgba(220,38,38,${0.08 + (0.5 * v) / max})`) : '#f8fafc',
                    color: i === j && v / max > 0.5 ? 'white' : '#0f172a',
                  }}
                >
                  {v || ''}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ThresholdTable({ rows, chosen }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-100 text-sm">
        <thead className="bg-slate-50">
          <tr>
            <th className="table-head">Threshold</th>
            <th className="table-head text-right">Automatic</th>
            <th className="table-head text-right">Human review</th>
            <th className="table-head text-right">Correct among automatic</th>
            <th className="table-head text-right">Wrong among automatic</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => (
            <tr key={row.threshold} className={row.threshold === chosen ? 'bg-accent-50' : ''}>
              <td className="table-cell font-medium tabular-nums">
                {row.threshold.toFixed(2)} {row.threshold === chosen && <Badge tone="accent" className="ml-1">chosen</Badge>}
              </td>
              <td className="table-cell text-right tabular-nums">{row.automatic}</td>
              <td className="table-cell text-right tabular-nums">{row.human_review}</td>
              <td className="table-cell text-right tabular-nums">{row.automatic_accuracy == null ? '—' : percent(row.automatic_accuracy, 1)}</td>
              <td className="table-cell text-right tabular-nums">{row.incorrect_automatic}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Findings({ r }) {
  const items = []
  for (const task of ['category', 'priority']) {
    const t = r.tasks[task]
    const rows = t.comparison.filter((x) => x.status === 'EVALUATED')
    const sel = rows.find((x) => x.selected)
    const kw = rows.find((x) => x.model === 'keyword_baseline')
    const bestHoldout = rows.filter((x) => x.selectable).reduce((a, b) => (b.holdout.macro_f1 > a.holdout.macro_f1 ? b : a))
    items.push(
      `${task[0].toUpperCase() + task.slice(1)}: ${sel.title} was selected (CV macro-F1 ${percent(sel.cv.macro_f1.mean, 1)} ± ${(sel.cv.macro_f1.sd * 100).toFixed(1)}) vs keyword baseline ${percent(kw.cv.macro_f1.mean, 1)}; holdout macro-F1 ${percent(sel.holdout.macro_f1, 1)} vs ${percent(kw.holdout.macro_f1, 1)}.`,
    )
    if (bestHoldout.model !== sel.model) {
      items.push(
        `${task[0].toUpperCase() + task.slice(1)}: on the holdout, ${bestHoldout.title} scored higher (${percent(bestHoldout.holdout.macro_f1, 1)}). The CV-selected model is kept; choosing by holdout score would be tuning on the test set.`,
      )
    }
    items.push(
      t.thresholds.met
        ? `${task[0].toUpperCase() + task.slice(1)} threshold ${t.thresholds.threshold}: on development data ${percent(t.thresholds.at_threshold.automatic_rate)} of complaints are confident enough for automatic handling, ${percent(t.thresholds.at_threshold.automatic_accuracy, 1)} of them correct.`
        : `${task[0].toUpperCase() + task.slice(1)}: no threshold reached 80% correct automatic decisions, so this task always goes to a human.`,
    )
  }
  items.push('High and Critical priorities always go to a human regardless of confidence.')
  items.push('All data is synthetic; real-world performance is unknown until evaluated on real, consented campus complaints.')
  return (
    <ul className="space-y-2.5 text-sm text-slate-700">
      {items.map((text, i) => (
        <li key={text} className="flex gap-2.5">
          {i === items.length - 1 ? (
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-amber-600" />
          ) : (
            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-brand-500" />
          )}
          {text}
        </li>
      ))}
    </ul>
  )
}
