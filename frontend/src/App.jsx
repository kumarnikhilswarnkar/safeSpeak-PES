import { Route, Routes } from 'react-router-dom'

import NotFoundPage from './pages/NotFoundPage.jsx'
import SystemStatusPage from './pages/SystemStatusPage.jsx'

// Role-based areas (complainant, reviewer, authority, viewer, admin) are added
// from Phase 2 onward, behind authentication.
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<SystemStatusPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
