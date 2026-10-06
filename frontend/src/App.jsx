import { Navigate, Route, Routes } from 'react-router-dom'

import { useAuth } from './auth/AuthContext.jsx'
import RequireAuth from './auth/RequireAuth.jsx'
import { ROLE_HOME, homeFor } from './auth/roles.js'
import LoginPage from './pages/auth/LoginPage.jsx'
import ComplaintDetailPage from './pages/complaints/ComplaintDetailPage.jsx'
import { AllComplaintsPage, MyComplaintsPage, ReviewQueuePage } from './pages/complaints/ComplaintListPages.jsx'
import SubmitComplaintPage from './pages/complaints/SubmitComplaintPage.jsx'
import AutomationPage from './pages/AutomationPage.jsx'
import NotFoundPage from './pages/NotFoundPage.jsx'
import ResearchPage from './pages/ResearchPage.jsx'
import RoleHomePage from './pages/RoleHomePage.jsx'
import SystemStatusPage from './pages/SystemStatusPage.jsx'

function RootRedirect() {
  const { status, user } = useAuth()
  if (status === 'loading') return null
  return <Navigate to={status === 'authenticated' ? homeFor(user.role) : '/login'} replace />
}

const guarded = (element, props) => <RequireAuth {...props}>{element}</RequireAuth>

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/status" element={<SystemStatusPage />} />

      {/* One home per role. */}
      {Object.entries(ROLE_HOME).map(([role, path]) => (
        <Route key={role} path={path} element={guarded(<RoleHomePage />, { roles: [role] })} />
      ))}

      {/* Complaint workflow. Guards only control what is shown; the API authorizes every call. */}
      <Route path="/concerns/new" element={guarded(<SubmitComplaintPage />, { permission: 'submit_complaint' })} />
      <Route path="/concerns/mine" element={guarded(<MyComplaintsPage />, { permission: 'view_own_complaints' })} />
      <Route path="/concerns" element={guarded(<AllComplaintsPage />, { permission: 'view_scoped_complaints' })} />
      <Route path="/concerns/:code" element={guarded(<ComplaintDetailPage />)} />
      <Route path="/review" element={guarded(<ReviewQueuePage />, { permission: 'view_assigned_complaints' })} />

      {/* Insights: aggregate views, available to every signed-in account (the API scopes the data). */}
      <Route path="/automation" element={guarded(<AutomationPage />)} />
      <Route path="/research" element={guarded(<ResearchPage />)} />

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
