import { Maximize2, MessageCircleQuestion, X } from 'lucide-react'
import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'

import AssistantChat, { AssistantIntro } from './AssistantChat.jsx'
import { useAssistant } from './AssistantContext.jsx'

/**
 * Floating "Ask SafeSpeak" button and chat panel, available on every signed-in page.
 * Desktop/tablet: a floating panel. Phones: a full-screen sheet.
 */
export default function AssistantLauncher() {
  const assistant = useAssistant()
  const { open, setOpen } = assistant
  const { pathname } = useLocation()

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    // Phones: the sheet covers the page, so stop the page behind it from scrolling.
    const small = window.matchMedia('(max-width: 639px)').matches
    const previous = document.body.style.overflow
    if (small) document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [open, setOpen])

  if (pathname === '/assistant') return null

  return (
    <>
      {open && (
        <div
          role="dialog"
          aria-modal="false"
          aria-label="SafeSpeak Assistant"
          className="fixed inset-0 z-50 flex animate-sheet flex-col bg-white sm:inset-auto sm:right-5 sm:bottom-24 sm:h-[min(640px,calc(100dvh-8rem))] sm:w-[400px] sm:animate-pop sm:rounded-2xl sm:border sm:border-slate-200 sm:shadow-(--shadow-pop)"
        >
          <header className="flex items-center gap-3 border-b border-slate-100 bg-brand-900 px-4 py-3 text-white sm:rounded-t-2xl">
            <span className="grid size-8 place-items-center rounded-full bg-white/10">
              <MessageCircleQuestion className="size-4.5 text-accent-500" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">SafeSpeak Assistant</p>
              <p className="truncate text-xs text-brand-100/70">Status, deadlines and timelines from live records</p>
            </div>
            <Link to="/assistant" onClick={() => setOpen(false)} className="rounded-md p-1.5 text-brand-100/80 hover:bg-white/10 hover:text-white" aria-label="Open full screen" title="Open full screen">
              <Maximize2 className="size-4" />
            </Link>
            <button type="button" onClick={() => setOpen(false)} className="rounded-md p-1.5 text-brand-100/80 hover:bg-white/10 hover:text-white" aria-label="Close assistant">
              <X className="size-4.5" />
            </button>
          </header>
          <div className="border-b border-slate-100 bg-slate-50 px-4 py-1.5">
            <AssistantIntro />
          </div>
          <AssistantChat assistant={assistant} onNavigate={() => setOpen(false)} autoFocus className="flex-1" />
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-label={open ? 'Close SafeSpeak Assistant' : 'Open SafeSpeak Assistant'}
        className={`fixed right-4 bottom-[max(1rem,env(safe-area-inset-bottom))] z-40 items-center gap-2 rounded-full bg-brand-700 py-3 pr-4 pl-3.5 text-sm font-medium text-white shadow-(--shadow-pop) transition duration-200 hover:-translate-y-0.5 hover:bg-brand-800 sm:right-5 sm:bottom-6 ${open ? 'hidden sm:flex' : 'flex'}`}
      >
        {open ? <X className="size-5" aria-hidden="true" /> : <MessageCircleQuestion className="size-5 text-accent-500" aria-hidden="true" />}
        <span className="hidden sm:inline">{open ? 'Close' : 'Ask SafeSpeak'}</span>
      </button>
    </>
  )
}
