import { useAuth } from '../auth/AuthContext.jsx'
import AdminDashboard from './dashboards/AdminDashboard.jsx'
import ComplainantDashboard from './dashboards/ComplainantDashboard.jsx'
import ReviewerDashboard from './dashboards/ReviewerDashboard.jsx'

// One dashboard per kind of user; the role always comes from the server account.
export default function RoleHomePage() {
  const { user } = useAuth()
  if (['department_authority', 'higher_authority'].includes(user.role)) return <ReviewerDashboard />
  if (['admin', 'viewer'].includes(user.role)) return <AdminDashboard />
  return <ComplainantDashboard />
}
