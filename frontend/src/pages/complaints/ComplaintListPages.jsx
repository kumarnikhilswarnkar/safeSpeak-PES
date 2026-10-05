import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'

import { listInScope, listMine, listPendingReview, listQueue } from '../../api/concerns.js'
import { useAuth } from '../../auth/AuthContext.jsx'
import AppShell from '../../components/AppShell.jsx'
import ComplaintTable from '../../components/ComplaintTable.jsx'
import useLoader from '../../hooks/useLoader.js'

function ListBody({ loader, empty, showComplainant }) {
  const { data, error, loading } = useLoader(loader)
  if (loading) return <p className="muted" role="status">Loading…</p>
  if (error) return <p className="alert alert--danger" role="alert">{error.message}</p>
  return <ComplaintTable complaints={data} empty={empty} showComplainant={showComplainant} />
}

export function MyComplaintsPage() {
  const { authRequest } = useAuth()
  const loader = useCallback(() => listMine(authRequest), [authRequest])
  return (
    <AppShell>
      <div className="page-head">
        <div>
          <h1 className="content__title">My complaints</h1>
          <p className="muted">Complaints you have submitted. Open one to see its full timeline.</p>
        </div>
        <Link className="btn btn--primary" to="/concerns/new">
          Submit complaint
        </Link>
      </div>
      <section className="card">
        <ListBody loader={loader} empty="You have not submitted any complaints yet." />
      </section>
    </AppShell>
  )
}

export function ReviewQueuePage() {
  const { authRequest, user } = useAuth()
  const canReview = user.permissions.includes('review_complaints')
  const [tab, setTab] = useState(canReview ? 'review' : 'all')
  const reviewLoader = useCallback(() => listPendingReview(authRequest), [authRequest])
  const allLoader = useCallback(() => listQueue(authRequest), [authRequest])

  return (
    <AppShell>
      <div>
        <h1 className="content__title">Review queue</h1>
        <p className="muted">Open complaints assigned to you, earliest deadline first.</p>
      </div>
      <div className="tabs" role="tablist">
        {canReview && (
          <button type="button" role="tab" aria-selected={tab === 'review'} className="tabs__tab" onClick={() => setTab('review')}>
            Needs human review
          </button>
        )}
        <button type="button" role="tab" aria-selected={tab === 'all'} className="tabs__tab" onClick={() => setTab('all')}>
          All assigned to me
        </button>
      </div>
      <section className="card">
        {tab === 'review' ? (
          <ListBody key="review" loader={reviewLoader} showComplainant empty="Nothing is waiting for your review." />
        ) : (
          <ListBody key="all" loader={allLoader} showComplainant empty="No open complaints are assigned to you." />
        )}
      </section>
    </AppShell>
  )
}

export function AllComplaintsPage() {
  const { authRequest } = useAuth()
  const loader = useCallback(() => listInScope(authRequest), [authRequest])
  return (
    <AppShell>
      <div>
        <h1 className="content__title">All complaints</h1>
        <p className="muted">Read-only view of complaints within your scope.</p>
      </div>
      <section className="card">
        <ListBody loader={loader} showComplainant empty="No complaints in your scope yet." />
      </section>
    </AppShell>
  )
}
