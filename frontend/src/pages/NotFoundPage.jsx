import { Compass } from 'lucide-react'
import { Link } from 'react-router-dom'

import CenteredPage from '../components/CenteredPage.jsx'

export default function NotFoundPage() {
  return (
    <CenteredPage>
      <Compass className="size-8 text-slate-400" aria-hidden="true" />
      <p className="mt-3 text-sm font-semibold text-slate-500">404</p>
      <h1 className="mt-1 text-xl font-semibold text-slate-900">Page not found</h1>
      <p className="mt-2 text-sm text-slate-500">The page you are looking for does not exist.</p>
      <Link className="btn-primary mt-6 w-full" to="/">
        Go to home
      </Link>
    </CenteredPage>
  )
}
