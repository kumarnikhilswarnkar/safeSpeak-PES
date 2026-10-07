import { Bot, CheckCircle2, Info, ListTree, UserCog } from 'lucide-react'

import { REASON_LABEL, percent } from '../utils/format.js'
import { ConfidenceBar } from './Badges.jsx'
import { Badge, Card, cx } from './ui.jsx'

function SimilarTraining({ items }) {
  return (
    <div>
      <ul className="space-y-1 text-xs text-slate-700">
        {items.map((s, i) => (
          <li key={i} className="flex justify-between gap-2 rounded-md bg-slate-50 px-2 py-1 ring-1 ring-slate-200 ring-inset">
            <span>{s.label}</span>
            <span className="tabular-nums text-slate-500">similarity {s.similarity.toFixed(2)}</span>
          </li>
        ))}
      </ul>
      <p className="mt-1 text-xs text-slate-500">
        Embedding model: labels of the most similar training complaints. It has no word-level explanation.
      </p>
    </div>
  )
}

function Evidence({ terms, similar, keywordLabel }) {
  if (similar?.length) return <SimilarTraining items={similar} />
  if (!terms?.length) return <p className="text-xs text-slate-500">No word-level evidence for this prediction.</p>
  return (
    <div className="flex flex-wrap gap-1.5">
      {terms.map((t) => {
        const keyword = t.term.startsWith('kw:')
        return (
          <span
            key={t.term}
            title={`Contribution to the model score: ${t.weight}`}
            className={cx(
              'rounded-md px-2 py-0.5 text-xs ring-1 ring-inset',
              keyword ? 'bg-accent-50 text-accent-600 ring-accent-100' : 'bg-slate-50 text-slate-700 ring-slate-200',
            )}
          >
            {keyword ? `${keywordLabel}: ${t.term.slice(3)}` : t.term}
          </span>
        )
      })}
    </div>
  )
}

function Prediction({ label, value, confidence, threshold }) {
  const low = confidence < threshold
  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="eyebrow">{label}</p>
          <p className="mt-1 truncate text-base font-semibold text-slate-900">{value}</p>
        </div>
        <Badge tone={low ? 'violet' : 'green'}>{low ? 'Below threshold' : 'Confident'}</Badge>
      </div>
      <div className="mt-3">
        <ConfidenceBar value={confidence} threshold={threshold} />
        <p className="mt-1 text-xs text-slate-500">
          Confidence {percent(confidence)} · threshold {percent(threshold)}
        </p>
      </div>
    </div>
  )
}

/** AI recommendation, confidence vs threshold, the resulting decision and the model's evidence. */
export default function AiAnalysisCard({ ai, decisionSource, compact = false }) {
  const review = ai.flagged_for_review
  const e = ai.explanation
  const kw = e?.keyword_baseline
  // Category and priority have separate thresholds (v3); older predictions stored one.
  const priorityThreshold = ai.priority_threshold ?? ai.threshold
  const separate = priorityThreshold !== ai.threshold
  const linear = e?.category_model?.kind !== 'embedding-lr'
  return (
    <Card
      title="AI analysis"
      subtitle={`Local model ${ai.model} · runs inside the SafeSpeak backend, no external AI service`}
      icon={Bot}
      actions={<Badge tone="slate">Recommendation only</Badge>}
    >
      <div className="grid gap-3 md:grid-cols-2">
        <Prediction label="AI category" value={ai.category} confidence={ai.category_confidence} threshold={ai.threshold} />
        <Prediction label="AI priority" value={ai.priority} confidence={ai.priority_confidence} threshold={priorityThreshold} />
      </div>

      <div
        className={cx(
          'mt-4 flex items-start gap-3 rounded-lg border px-4 py-3',
          review ? 'border-violet-200 bg-violet-50' : 'border-emerald-200 bg-emerald-50',
        )}
      >
        {review ? (
          <UserCog className="mt-0.5 size-5 shrink-0 text-violet-600" aria-hidden="true" />
        ) : (
          <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-emerald-600" aria-hidden="true" />
        )}
        <div className="min-w-0 text-sm">
          <p className={cx('font-semibold', review ? 'text-violet-900' : 'text-emerald-900')}>
            Decision: {review ? 'Human review required' : 'Continue automatically'}
          </p>
          <p className={review ? 'text-violet-800' : 'text-emerald-800'}>
            {review
              ? `Reason: ${ai.flag_reasons.map((r) => REASON_LABEL[r] ?? r).join('; ')}. The complaint waits in the L1 reviewer's queue; nothing is final until a person decides.`
              : `${separate ? `Category confidence is at or above its ${percent(ai.threshold)} threshold and priority confidence at or above its ${percent(priorityThreshold)} threshold` : `Both confidences are at or above the ${percent(ai.threshold)} threshold`}, and the priority is not High/Critical, so the AI recommendation was routed automatically. A reviewer can still override it.`}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Overall confidence {percent(ai.confidence)} (the lower of the two) ·{' '}
            {ai.threshold_source === 'CONFIG' ? 'category threshold set in configuration' : 'category threshold chosen on cross-validation data'}
            {separate &&
              (ai.priority_threshold_source === 'CONFIG'
                ? ' · priority threshold set in configuration'
                : ' · priority threshold chosen separately on cross-validation data')}
          </p>
        </div>
      </div>

      {!compact && e && (
        <div className="mt-4 grid gap-4 border-t border-slate-100 pt-4 md:grid-cols-2">
          <div>
            <p className="eyebrow mb-2 flex items-center gap-1.5">
              <ListTree className="size-3.5" /> Why this category
            </p>
            <Evidence terms={e.category_terms} similar={e.category_model?.similar_training} keywordLabel="Keyword list" />
          </div>
          <div>
            <p className="eyebrow mb-2 flex items-center gap-1.5">
              <ListTree className="size-3.5" /> Why this priority
            </p>
            <Evidence terms={e.priority_terms} similar={e.priority_model?.similar_training} keywordLabel="Keyword list" />
          </div>
          {kw && (
            <div className="md:col-span-2">
              <p className="text-xs text-slate-500">
                <Info className="mr-1 inline size-3.5 align-[-2px]" aria-hidden="true" />
                Keyword baseline would say <strong className="text-slate-700">{kw.category}</strong> /{' '}
                <strong className="text-slate-700">{kw.priority}</strong>
                {kw.category === ai.category ? ' — agrees with the model on category.' : ' — disagrees with the model on category.'}{' '}
                {linear
                  ? 'Evidence = words with the largest positive contribution to the linear model score (exact for this model; character n-grams not shown).'
                  : 'Evidence = most similar training complaints (embedding models give no word-level explanation).'}
              </p>
            </div>
          )}
        </div>
      )}
      {decisionSource && decisionSource.startsWith('HUMAN') && (
        <p className="mt-3 text-xs text-slate-500">
          This is the original AI output and is stored unchanged. The human decision is shown separately.
        </p>
      )}
    </Card>
  )
}
