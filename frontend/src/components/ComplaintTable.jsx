import { Link } from 'react-router-dom'

import { formatDateTime, formatRemaining } from '../utils/format.js'
import { EscalationBadge, PriorityBadge, StatusBadge, TatBadge } from './Badges.jsx'

export default function ComplaintTable({ complaints, showComplainant = false, empty }) {
  if (complaints.length === 0) {
    return <p className="muted">{empty}</p>
  }
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">Complaints</caption>
        <thead>
          <tr>
            <th scope="col">Complaint ID</th>
            {showComplainant && <th scope="col">Complainant</th>}
            <th scope="col">Category</th>
            <th scope="col">Priority</th>
            <th scope="col">Status</th>
            <th scope="col">Assigned to</th>
            <th scope="col">Deadline</th>
          </tr>
        </thead>
        <tbody>
          {complaints.map((c) => (
            <tr key={c.complaint_id}>
              <td data-label="Complaint ID">
                <Link to={`/concerns/${c.complaint_id}`}>{c.complaint_id}</Link>
              </td>
              {showComplainant && <td data-label="Complainant">{c.complainant.name}</td>}
              <td data-label="Category">{c.category}</td>
              <td data-label="Priority">
                <PriorityBadge priority={c.priority} />
              </td>
              <td data-label="Status">
                <span className="badge-row">
                  <StatusBadge status={c.status} />
                  <EscalationBadge complaint={c} />
                </span>
              </td>
              <td data-label="Assigned to">{c.assigned_to?.name ?? '—'}</td>
              <td data-label="Deadline">
                <span className="badge-row">
                  <TatBadge state={c.tat.state} />
                  <span className="small">
                    {c.tat.state === 'STOPPED' ? formatDateTime(c.resolved_at) : formatRemaining(c.tat.deadline_at)}
                  </span>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
