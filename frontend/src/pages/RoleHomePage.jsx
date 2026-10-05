import { useState } from 'react'

import { useAuth } from '../auth/AuthContext.jsx'
import { PERMISSION_LABEL, ROLE_LABEL } from '../auth/roles.js'
import AppShell from '../components/AppShell.jsx'

/**
 * Phase 2 verification page shown for every role: it proves which account the
 * server authenticated and what it may do. Final dashboards replace it later.
 */
export default function RoleHomePage() {
  const { user } = useAuth()

  return (
    <AppShell>
        <div>
          <h1 className="content__title">{ROLE_LABEL[user.role]} home</h1>
          <p className="muted">
            Your role and permissions below come from your account on the server. Use the menu above to work with
            complaints.
          </p>
        </div>

        <div className="grid-2">
          <section className="card stack" aria-labelledby="profile-heading">
            <h2 id="profile-heading" className="card__title">Account</h2>
            <dl className="status-list">
              <Row label="Name" value={user.name} />
              <Row label="Email" value={user.email} />
              <Row label="Role" value={ROLE_LABEL[user.role]} />
              <Row label="Department" value={user.department ? `${user.department.name} (${user.department.code})` : '—'} />
              <Row label="Authority level" value={user.authority_level ? `L${user.authority_level}` : '—'} />
              <Row label="Status" value={user.is_active ? 'Active' : 'Inactive'} />
            </dl>
          </section>

          <section className="card stack" aria-labelledby="permissions-heading">
            <h2 id="permissions-heading" className="card__title">Permissions</h2>
            <ul className="check-list">
              {user.permissions.map((permission) => (
                <li key={permission}>{PERMISSION_LABEL[permission] ?? permission}</li>
              ))}
            </ul>
          </section>
        </div>

        <AdminApiCheck isAdmin={user.permissions.includes('manage_users')} />
    </AppShell>
  )
}

function Row({ label, value }) {
  return (
    <div className="status-row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

/** Calls an admin-only endpoint so the backend's decision can be seen directly. */
function AdminApiCheck({ isAdmin }) {
  const { authRequest } = useAuth()
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  async function run() {
    setLoading(true)
    try {
      const users = await authRequest('/admin/users')
      setResult({ ok: true, users })
    } catch (error) {
      setResult({ ok: false, status: error.status, message: error.message })
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="card stack" aria-labelledby="authz-heading">
      <div>
        <h2 id="authz-heading" className="card__title">Backend authorization check</h2>
        <p className="muted small">
          Requests the admin-only endpoint <code>GET /api/v1/admin/users</code>.{' '}
          {isAdmin ? 'Your account should be allowed.' : 'Your account should be refused with 403.'}
        </p>
      </div>
      <div>
        <button type="button" className="btn btn--secondary" onClick={run} disabled={loading}>
          {loading ? 'Checking…' : 'Run check'}
        </button>
      </div>

      {result && !result.ok && (
        <p className={`alert ${result.status === 403 ? 'alert--info' : 'alert--danger'}`} role="status">
          Server responded {result.status || 'with an error'}: {result.message}
        </p>
      )}

      {result?.ok && (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Accounts</caption>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Email</th>
                <th scope="col">Role</th>
                <th scope="col">Department</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {result.users.map((u) => (
                <tr key={u.id}>
                  <td data-label="Name">{u.name}</td>
                  <td data-label="Email">{u.email}</td>
                  <td data-label="Role">{ROLE_LABEL[u.role] ?? u.role}</td>
                  <td data-label="Department">{u.department?.code ?? '—'}</td>
                  <td data-label="Status">{u.is_active ? 'Active' : 'Inactive'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
