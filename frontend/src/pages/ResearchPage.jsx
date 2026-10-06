import { BarChart3, Beaker, Database, FlaskConical, Gauge, Grid3x3, ShieldCheck, SlidersHorizontal, TriangleAlert } from 'lucide-react'
import { useCallback, useState } from 'react'

import { getEvaluation } from '../api/insights.js'
import { useAuth } from '../auth/AuthContext.jsx'
import AppShell from '../components/AppShell.jsx'
import { COLORS, GroupedBars, ThresholdCurve } from '../components/Charts.jsx'
import { Alert, Badge, Card, ErrorState, LoadingState, PageHeader, Tabs, cx } from '../components/ui.jsx'
import useLoader from '../hooks/useLoader.js'
import { percent } from '../utils/format.js'

const MODEL_LABEL = {
  keyword_baseline: 'Keyword baseline (rules)',
  v1_deployed: 'v1 model (Review-II)',
  word_lr: 'TF-IDF words + LR',
  word_char_lr_C1: 'Words + chars + LR (C=1)',
  word_char_lr_C5: 'Words + chars + LR (C=5)',
  word_char_svm: 'Words + chars + Linear SVM',
  hybrid_kw_lr_C5: 'Hybrid: words + chars + keywords + LR',
}

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
        description="How the local triage model was chosen and how well it works: keyword baseline vs machine learning on the same held-out test set, calibration, the confidence threshold, and robustness checks. All numbers are produced by ml/train_triage_v2.py."
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

function Report({ r, task, setTask }) {
  const selected = r.selected[task].model
  const test = r.test[task]
  const kw = test.keyword_baseline
  const sel = test[selected]
  return (
    <div className="space-y-6">
      <Alert tone="amber" icon={Database} title="Synthetic / controlled dataset">
        {r.dataset.note} {r.dataset.rows} records in {r.dataset.groups} paraphrase groups; held-out test split = {r.dataset.test_rows}{' '}
        records. Results show how the method behaves on controlled data — not how it would perform on real campus complaints.
      </Alert>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Fact label="Model in use" value={r.live.model ?? '—'} hint={`Category: ${MODEL_LABEL[r.selected.category.model]} · Priority: ${MODEL_LABEL[r.selected.priority.model]}`} />
        <Fact label="Review threshold in use" value={percent(r.live.threshold)} hint={r.live.threshold_source?.startsWith('MODEL') ? 'Chosen on cross-validation data' : 'Set in configuration'} />
        <Fact label="Selection protocol" value="5-fold grouped CV" hint="On train+val; paraphrase groups never split" />
        <Fact label="Final check" value="Held-out test" hint="Same 90 records for every model, used once" />
      </div>

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
          <HeadToHead kw={kw} sel={sel} selectedName={MODEL_LABEL[selected]} cvKw={r.cv[task].keyword_baseline} cvSel={r.cv[task][selected]} task={task} />
          <ComparisonTable test={test} cv={r.cv[task]} selected={selected} />
          <div className="grid gap-6 xl:grid-cols-2">
            <Card title="Per-class F1 on the test set" icon={BarChart3} subtitle="Keyword baseline vs selected model">
              <GroupedBars
                percent
                data={Object.keys(sel.per_class).map((label) => ({
                  label,
                  keyword: kw.per_class[label].f1,
                  model: sel.per_class[label].f1,
                }))}
                series={[
                  { key: 'keyword', name: 'Keyword baseline', color: COLORS.slate },
                  { key: 'model', name: 'Selected model', color: COLORS.brand },
                ]}
              />
            </Card>
            <Card title="Confusion matrix (selected model, test)" icon={Grid3x3} subtitle="Rows = true label, columns = predicted">
              <Confusion cm={sel.confusion_matrix} />
            </Card>
          </div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card title="Confidence threshold analysis" icon={SlidersHorizontal} subtitle="Out-of-fold curves used to choose the threshold" className="xl:col-span-2">
          <ThresholdCurve data={r.threshold.oof_curve} threshold={r.threshold.recommended} />
          <p className="mt-2 text-xs text-slate-500">Rule: {r.threshold.rule}.</p>
        </Card>
        <Card title="Calibration" icon={Gauge} subtitle="Temperature scaling; lower ECE = confidence closer to real accuracy">
          <div className="space-y-4">
            {['category', 'priority'].map((t) => {
              const c = r.calibration[t]
              const better = c.test.ece_after < c.test.ece_before
              return (
                <div key={t} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium capitalize">{t}</p>
                    <Badge tone={better ? 'green' : 'amber'}>{better ? 'improved on test' : 'not improved on test'}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">Temperature T = {c.temperature}</p>
                  <p className="mt-2 text-sm tabular-nums">
                    Test ECE {c.test.ece_before} → <strong>{c.test.ece_after}</strong>
                  </p>
                  <p className="text-xs text-slate-500 tabular-nums">
                    Out-of-fold ECE {c.oof.ece_before} → {c.oof.ece_after}
                  </p>
                </div>
              )
            })}
          </div>
        </Card>
      </div>

      <Card title="Threshold trade-off on the held-out test set" icon={SlidersHorizontal} subtitle="Auto-handled = AI recommendation used without review; errors = auto-handled cases where category or priority was wrong" bodyClassName="p-0">
        <ThresholdTable rows={r.threshold.test_table} severity={r.threshold.test_table_with_severity_rule} chosen={r.threshold.recommended} />
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Robustness by writing style" icon={Beaker} subtitle="Out-of-fold category accuracy on the dataset's style tags" bodyClassName="p-0">
          <StyleTable rows={r.robustness.by_style_oof} />
          <div className="border-t border-slate-100 px-5 py-3 text-sm text-slate-600">
            <p className="font-medium text-slate-800">Spelling noise (test set with injected typos)</p>
            <p className="mt-1 tabular-nums">
              ML: {percent(r.robustness.typo_noise_test.ml_category_accuracy_clean, 1)} →{' '}
              {percent(r.robustness.typo_noise_test.ml_category_accuracy_noisy, 1)} · Keyword baseline:{' '}
              {percent(r.robustness.typo_noise_test.keyword_category_accuracy_clean, 1)} →{' '}
              {percent(r.robustness.typo_noise_test.keyword_category_accuracy_noisy, 1)}
            </p>
          </div>
        </Card>
        <Card title="Difficult inputs → human review?" icon={ShieldCheck} subtitle={r.robustness.probes.description} bodyClassName="p-0">
          <Probes probes={r.robustness.probes} />
        </Card>
      </div>

      <Card title="Findings (stated honestly)" icon={FlaskConical}>
        <Findings r={r} />
      </Card>
    </div>
  )
}

function Fact({ label, value, hint }) {
  return (
    <div className="card p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-0.5 truncate text-lg font-semibold text-slate-900">{value}</p>
      <p className="mt-0.5 text-xs text-slate-500">{hint}</p>
    </div>
  )
}

function HeadToHead({ kw, sel, selectedName, cvKw, cvSel, task }) {
  const items = [
    ['Accuracy (test)', kw.accuracy, sel.accuracy],
    ['Macro-F1 (test)', kw.macro_f1, sel.macro_f1],
    ['Macro-F1 (5-fold CV)', cvKw.macro_f1_mean, cvSel.macro_f1_mean],
  ]
  return (
    <div>
      <p className="mb-3 text-sm text-slate-600">
        <strong className="text-slate-900">Keyword baseline vs {selectedName}</strong> for {task}.
      </p>
      <div className="grid gap-3 md:grid-cols-3">
        {items.map(([label, a, b]) => {
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
                  <p className="text-xs text-slate-400">ML</p>
                  <p className="text-lg font-semibold text-slate-900 tabular-nums">{percent(b, 1)}</p>
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

function ComparisonTable({ test, cv, selected }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr>
            <th className="table-head">Model</th>
            <th className="table-head text-right">Accuracy</th>
            <th className="table-head text-right">Macro precision</th>
            <th className="table-head text-right">Macro recall</th>
            <th className="table-head text-right">Macro-F1</th>
            <th className="table-head text-right">CV macro-F1 (mean ± sd)</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {Object.entries(test).map(([name, m]) => (
            <tr key={name} className={name === selected ? 'bg-brand-50/60' : name === 'keyword_baseline' ? 'bg-slate-50/60' : ''}>
              <td className="table-cell">
                <span className="font-medium text-slate-900">{MODEL_LABEL[name] ?? name}</span>
                {name === selected && <Badge tone="brand" className="ml-2">selected by CV</Badge>}
              </td>
              <td className="table-cell text-right tabular-nums">{percent(m.accuracy, 1)}</td>
              <td className="table-cell text-right tabular-nums">{percent(m.macro_precision, 1)}</td>
              <td className="table-cell text-right tabular-nums">{percent(m.macro_recall, 1)}</td>
              <td className="table-cell text-right font-medium tabular-nums">{percent(m.macro_f1, 1)}</td>
              <td className="table-cell text-right text-slate-600 tabular-nums">
                {cv[name] ? `${percent(cv[name].macro_f1_mean, 1)} ± ${(cv[name].macro_f1_sd * 100).toFixed(1)}` : 'trained on train split only'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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

function ThresholdTable({ rows, severity, chosen }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-100 text-sm">
        <thead className="bg-slate-50">
          <tr>
            <th className="table-head">Threshold</th>
            <th className="table-head text-right">Auto-handled</th>
            <th className="table-head text-right">Human review</th>
            <th className="table-head text-right">Errors in auto</th>
            <th className="table-head text-right">Errors caught by review</th>
            <th className="table-head text-right">Auto (with High/Critical rule)</th>
            <th className="table-head text-right">Errors in auto (with rule)</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row, i) => (
            <tr key={row.threshold} className={row.threshold === chosen ? 'bg-accent-50' : ''}>
              <td className="table-cell font-medium tabular-nums">
                {row.threshold.toFixed(2)} {row.threshold === chosen && <Badge tone="accent" className="ml-1">chosen</Badge>}
              </td>
              <td className="table-cell text-right tabular-nums">{row.auto_handled}</td>
              <td className="table-cell text-right tabular-nums">{row.human_review}</td>
              <td className="table-cell text-right tabular-nums">{row.auto_errors}</td>
              <td className="table-cell text-right tabular-nums">{row.errors_caught_by_review}</td>
              <td className="table-cell text-right tabular-nums">{severity[i].auto_handled}</td>
              <td className="table-cell text-right tabular-nums">{severity[i].auto_errors}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function StyleTable({ rows }) {
  return (
    <table className="min-w-full divide-y divide-slate-100 text-sm">
      <thead className="bg-slate-50">
        <tr>
          <th className="table-head">Style</th>
          <th className="table-head text-right">n</th>
          <th className="table-head text-right">ML</th>
          <th className="table-head text-right">Keyword</th>
          <th className="table-head text-right">Sent to review</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {rows.map((s) => (
          <tr key={s.style}>
            <td className="table-cell capitalize">{s.style}</td>
            <td className="table-cell text-right tabular-nums text-slate-500">{s.n}</td>
            <td className="table-cell text-right tabular-nums">{percent(s.ml_category_accuracy, 1)}</td>
            <td className="table-cell text-right tabular-nums text-slate-600">{percent(s.keyword_category_accuracy, 1)}</td>
            <td className="table-cell text-right tabular-nums">{percent(s.review_rate)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Probes({ probes }) {
  return (
    <div>
      <ul className="divide-y divide-slate-100">
        {probes.rows.map((p) => (
          <li key={p.text} className="flex items-start gap-3 px-5 py-2.5 text-sm">
            <Badge tone="slate" className="mt-0.5 w-28 justify-center">
              {p.kind.replace('_', ' ')}
            </Badge>
            <div className="min-w-0 flex-1">
              <p className="truncate text-slate-800">“{p.text}”</p>
              <p className="text-xs text-slate-500">
                {p.category} · {p.priority} · confidence {percent(p.confidence)}
              </p>
            </div>
            <Badge tone={p.sent_to_review ? 'violet' : 'amber'}>{p.sent_to_review ? 'human review' : 'automatic'}</Badge>
          </li>
        ))}
      </ul>
      <p className="border-t border-slate-100 px-5 py-3 text-sm text-slate-600">
        {probes.sent_to_review} of {probes.total} difficult inputs were sent to a human.
      </p>
    </div>
  )
}

function Findings({ r }) {
  const c = r.test.category
  const cvc = r.cv.category
  const sel = r.selected.category.model
  const p = r.test.priority
  const selP = r.selected.priority.model
  const th = r.threshold.test_table.find((x) => x.threshold === r.threshold.recommended)
  const thRule = r.threshold.test_table_with_severity_rule.find((x) => x.threshold === r.threshold.recommended)
  const items = [
    `The Review-II model (TF-IDF words + LR) was weaker than the keyword baseline in cross-validation (macro-F1 ${percent(cvc.word_lr.macro_f1_mean, 1)} vs ${percent(cvc.keyword_baseline.macro_f1_mean, 1)}). The faculty observation was correct.`,
    `Adding character n-grams helped (CV ${percent(cvc.word_char_lr_C5.macro_f1_mean, 1)}), but pure ML still did not beat the keyword lexicon in cross-validation.`,
    `The hybrid model (ML + keyword-count features) had the best CV macro-F1 (${percent(cvc[sel].macro_f1_mean, 1)}) and was selected. On the held-out test set it reaches ${percent(c[sel].accuracy, 1)} accuracy vs ${percent(c.keyword_baseline.accuracy, 1)} for keywords. Its evidence shows the keyword features carry most of the weight.`,
    `On the test set a pure ML variant scored higher than the selected hybrid (${percent(c.word_char_svm.macro_f1, 1)} vs ${percent(c[sel].macro_f1, 1)} macro-F1). We keep the CV-selected model: picking by test score would be test-set tuning.`,
    `Priority: ML is far better than keywords (test macro-F1 ${percent(p[selP].macro_f1, 1)} vs ${percent(p.keyword_baseline.macro_f1, 1)}), but still modest; High/Critical predictions always go to a human.`,
    `At the chosen threshold ${r.threshold.recommended}, the confidence check alone lets ${th.auto_handled} of 90 test complaints through automatically (${th.auto_errors} of them with a category or priority error). With the High/Critical rule as deployed, ${thRule.auto_handled} are automatic (${thRule.auto_errors} with an error) and ${90 - thRule.auto_handled} go to a human. Humans remain essential at this model quality.`,
    `Temperature scaling improved category calibration on test (ECE ${r.calibration.category.test.ece_before} → ${r.calibration.category.test.ece_after}) but not priority (${r.calibration.priority.test.ece_before} → ${r.calibration.priority.test.ece_after}); the test split has a different priority mix.`,
    'All data is synthetic; real-world performance is unknown until the system is evaluated on real, consented campus complaints.',
  ]
  return (
    <ul className="space-y-2.5 text-sm text-slate-700">
      {items.map((t, i) => (
        <li key={t} className="flex gap-2.5">
          {i === items.length - 1 ? (
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-amber-600" />
          ) : (
            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-brand-500" />
          )}
          {t}
        </li>
      ))}
    </ul>
  )
}
