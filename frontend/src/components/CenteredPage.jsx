import Wordmark from './Wordmark.jsx'

/** Full-page centred card for status, 403 and 404 screens. */
export default function CenteredPage({ children }) {
  return (
    <div className="grid min-h-screen place-items-center bg-slate-50 px-4">
      <main className="card w-full max-w-md p-8">
        <Wordmark />
        <div className="mt-6">{children}</div>
      </main>
    </div>
  )
}
