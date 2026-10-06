import { ArrowUpCircle, CheckCircle2, ClipboardList, FilePlus2, Hourglass, ShieldCheck, UserCog } from 'lucide-react'
import { useCallback } from 'react'
import { Link } from 'react-router-dom'

import { listMine } from '../../api/concerns.js'
import { useAuth } from '../../auth/AuthContext.jsx'
import { ROLE_LABEL } from '../../auth/roles.js'
import AppShell from '../../components/AppShell.jsx'
import ComplaintTable from '../../components/ComplaintTable.jsx'
import { Card, ErrorState, LoadingState, PageHeader, StatCard } from '../../components/ui.jsx'
import useLoader from '../../hooks/useLoader.js'
import { OPEN_STATUSES } from '../../utils/format.js'

export default function ComplainantDashboard() {
  const { authRequest, user } = useAuth()
  const loader = useCallback(() => listMine(authRequest), [authRequest])
  const { data, error, loading, reload } = useLoader(loader)

  return (
    <AppShell>
      <PageHeader
        eyebrow={ROLE_LABEL[user.role]}
        title={`Welcome, ${user.name.split(' ')[0] === 'Demo' ? user.name : user.name.split(' ')[0]}`}
        description="Track every concern you have raised, from AI triage to resolution."
        actions={
          <Link to="/concerns/new" className="btn-accent">
            <FilePlus2 className="size-4" /> New complaint
          </Link>
        }
      />
      {loading && !data ? (
        <LoadingState />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
            <StatCard label="Total complaints" value={data.length} icon={ClipboardList} tone="brand" />
            <StatCard label="Pending" value={data.filter((c) => OPEN_STATUSES.includes(c.status)).length} icon={Hourglass} tone="amber" hint="Open, not yet resolved" />
            <StatCard label="Under human review" value={data.filter((c) => c.status === 'PENDING_REVIEW').length} icon={UserCog} tone="violet" />
            <StatCard label="Resolved" value={data.filter((c) => c.status === 'RESOLVED').length} icon={CheckCircle2} tone="green" />
            <StatCard label="Escalated" value={data.filter((c) => c.escalated).length} icon={ArrowUpCircle} tone="accent" hint="Deadline missed → next level" />
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-3">
            <Card
              title="Recent complaints"
              icon={ClipboardList}
              className="xl:col-span-2"
              bodyClassName="p-0"
              actions={
                <Link to="/concerns/mine" className="text-sm font-medium text-brand-600 hover:text-brand-800">
                  View all
                </Link>
              }
            >
              <ComplaintTable
                complaints={data.slice(0, 6)}
                toolbar={false}
                columns={['decision']}
                emptyTitle="No complaints yet"
                emptyDescription="When you submit a concern it appears here with its live status and deadline."
              />
            </Card>
            <Card title="Your complaint is protected" icon={ShieldCheck}>
              <ul className="space-y-3 text-sm text-slate-600">
                <li>• Only you, the assigned authority and authorised viewers can open your complaint.</li>
                <li>• An AI model suggests a category and priority. A person reviews anything uncertain or serious.</li>
                <li>• Each complaint has a deadline. If it is missed, it moves up automatically.</li>
                <li>• Every action is recorded in the case's audit trail, which you can read.</li>
              </ul>
            </Card>
          </div>
        </>
      )}
    </AppShell>
  )
}
