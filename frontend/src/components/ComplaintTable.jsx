import { ChevronRight, Search, SlidersHorizontal } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { CATEGORIES, PRIORITIES, STATUS_LABEL, formatRemaining, stageLabel, timeAgo } from '../utils/format.js'
import { ConfidenceBar, DecisionBadge, EscalationBadge, PriorityBadge, StatusBadge, TatBadge } from './Badges.jsx'
import { EmptyState } from './ui.jsx'

const PRIORITY_RANK = { Critical: 0, High: 1, Medium: 2, Low: 3 }

const SORTS = {
  deadline: { label: 'Deadline (soonest)', fn: (a, b) => new Date(a.tat.deadline_at) - new Date(b.tat.deadline_at) },
  updated: { label: 'Last update', fn: (a, b) => new Date(b.updated_at) - new Date(a.updated_at) },
  priority: { label: 'Priority', fn: (a, b) => PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] },
  confidence: { label: 'AI confidence (lowest)', fn: (a, b) => a.ai.confidence - b.ai.confidence },
}

/**
 * Complaint list with client-side search, filters and sorting.
 * columns: subset of ['complainant', 'assignee', 'confidence', 'decision'].
 */
export default function ComplaintTable({ complaints, columns = [], emptyTitle, emptyDescription, defaultSort = 'updated', toolbar = true }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [category, setCategory] = useState('')
  const [sort, setSort] = useState(defaultSort)
  const show = (c) => columns.includes(c)

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return complaints
      .filter(
        (c) =>
          (!q || c.complaint_id.toLowerCase().includes(q) || c.description.toLowerCase().includes(q)) &&
          (!status || c.status === status) &&
          (!priority || c.priority === priority) &&
          (!category || c.category === category),
      )
      .sort(SORTS[sort].fn)
  }, [complaints, query, status, priority, category, sort])

  const filtered = query || status || priority || category

  return (
    <div>
      {toolbar && (
        <div className="flex flex-col gap-2 border-b border-slate-100 p-3 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
            <input
              className="input pl-9"
              placeholder="Search by ID or text…"
              aria-label="Search complaints"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <SlidersHorizontal className="hidden size-4 text-slate-400 lg:block" aria-hidden="true" />
            <select className="input w-auto" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">
              <option value="">All statuses</option>
              {Object.entries(STATUS_LABEL).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
            <select className="input w-auto" value={priority} onChange={(e) => setPriority(e.target.value)} aria-label="Priority filter">
              <option value="">All priorities</option>
              {PRIORITIES.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
            <select className="input w-auto" value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category filter">
              <option value="">All categories</option>
              {CATEGORIES.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
            <select className="input w-auto" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort order">
              {Object.entries(SORTS).map(([v, s]) => (
                <option key={v} value={v}>
                  Sort: {s.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {rows.length === 0 ? (
        <EmptyState
          title={filtered ? 'No complaints match these filters' : emptyTitle ?? 'No complaints yet'}
          description={filtered ? 'Clear the search or filters to see more.' : emptyDescription}
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100">
            <thead className="bg-slate-50/60">
              <tr>
                <th className="table-head">Complaint</th>
                <th className="table-head">Priority</th>
                <th className="table-head">Status</th>
                <th className="table-head">Stage</th>
                <th className="table-head">TAT</th>
                {show('confidence') && <th className="table-head w-40">AI confidence</th>}
                {show('decision') && <th className="table-head">Decision</th>}
                {show('assignee') && <th className="table-head">Assigned to</th>}
                {show('complainant') && <th className="table-head">Submitted by</th>}
                <th className="table-head">Updated</th>
                <th className="w-8" aria-hidden="true" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {rows.map((c) => (
                <tr
                  key={c.complaint_id}
                  className="cursor-pointer hover:bg-slate-50"
                  onClick={() => navigate(`/concerns/${c.complaint_id}`)}
                >
                  <td className="table-cell max-w-xs">
                    <Link
                      to={`/concerns/${c.complaint_id}`}
                      className="font-mono text-xs font-semibold text-brand-700 hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {c.complaint_id}
                    </Link>
                    <p className="truncate text-sm text-slate-900">{c.category}</p>
                    <p className="truncate text-xs text-slate-500">{c.description}</p>
                  </td>
                  <td className="table-cell">
                    <PriorityBadge priority={c.priority} />
                  </td>
                  <td className="table-cell">
                    <div className="flex flex-col items-start gap-1">
                      <StatusBadge status={c.status} />
                      <EscalationBadge complaint={c} />
                    </div>
                  </td>
                  <td className="table-cell text-slate-600">{stageLabel(c)}</td>
                  <td className="table-cell">
                    <TatBadge state={c.tat.state} />
                    {c.tat.state !== 'STOPPED' && (
                      <p className="mt-1 text-xs whitespace-nowrap text-slate-500">{formatRemaining(c.tat.deadline_at)}</p>
                    )}
                  </td>
                  {show('confidence') && (
                    <td className="table-cell">
                      <ConfidenceBar value={c.ai.confidence} threshold={c.ai.threshold} size="sm" />
                    </td>
                  )}
                  {show('decision') && (
                    <td className="table-cell">
                      <DecisionBadge source={c.decision_source} />
                    </td>
                  )}
                  {show('assignee') && (
                    <td className="table-cell text-slate-600">
                      {c.assigned_to ? `${c.assigned_to.name}` : '—'}
                    </td>
                  )}
                  {show('complainant') && <td className="table-cell text-slate-600">{c.complainant.name}</td>}
                  <td className="table-cell text-xs whitespace-nowrap text-slate-500">{timeAgo(c.updated_at)}</td>
                  <td className="table-cell pr-3 text-slate-300">
                    <ChevronRight className="size-4" aria-hidden="true" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
