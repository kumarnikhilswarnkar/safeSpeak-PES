import { ArrowUp, Bot, ChevronRight, Database, RotateCcw, ShieldCheck } from 'lucide-react'
import { Fragment, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { formatDateTime, formatRemaining } from '../../utils/format.js'
import { PriorityBadge, StatusBadge, TatBadge } from '../Badges.jsx'
import { Badge, cx } from '../ui.jsx'

/** Minimal formatting for assistant text: **bold** and line breaks. No HTML is injected. */
function RichText({ text }) {
  return text.split('\n').map((line, i) => (
    <Fragment key={i}>
      {i > 0 && <br />}
      {line.split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
        part.startsWith('**') && part.endsWith('**') ? (
          <strong key={j} className="font-semibold text-slate-900">
            {part.slice(2, -2)}
          </strong>
        ) : (
          <Fragment key={j}>{part}</Fragment>
        ),
      )}
    </Fragment>
  ))
}

function ComplaintSummary({ c, onNavigate, compact }) {
  return (
    <Link
      to={`/concerns/${c.complaint_id}`}
      onClick={onNavigate}
      className="group block rounded-xl border border-slate-200 bg-white p-3 transition hover:-translate-y-px hover:border-brand-200 hover:shadow-(--shadow-card)"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs font-semibold text-brand-700">{c.complaint_id}</span>
        <ChevronRight className="size-4 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-brand-500" aria-hidden="true" />
      </div>
      <p className="mt-0.5 truncate text-sm font-medium text-slate-900">{c.category}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <StatusBadge status={c.status} />
        <PriorityBadge priority={c.priority} />
        <TatBadge state={c.tat_state} />
        {c.breached_at_top ? (
          <Badge tone="red">Chain exhausted</Badge>
        ) : (
          c.escalated && <Badge tone="accent">Escalated · step {c.escalation_level}</Badge>
        )}
      </div>
      {!compact && (
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs text-slate-500">
          <dt>Handled by</dt>
          <dd className="truncate text-slate-700">{c.assigned_to ?? '—'}</dd>
          <dt>Deadline</dt>
          <dd className="text-slate-700">
            {formatDateTime(c.deadline_at)}
            {c.tat_state !== 'STOPPED' && <span className="text-slate-500"> · {formatRemaining(c.deadline_at)}</span>}
          </dd>
        </dl>
      )}
    </Link>
  )
}

function Timeline({ card }) {
  return (
    <ol className="relative ml-1.5 space-y-2.5 border-l border-slate-200 pl-4">
      {card.items.map((item, i) => (
        <li key={i} className="relative animate-message" style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}>
          <span className="absolute top-1.5 -left-[21px] size-2 rounded-full bg-brand-500 ring-4 ring-white" aria-hidden="true" />
          <p className="text-sm font-medium text-slate-800">{item.label}</p>
          <p className="text-xs text-slate-500">
            {formatDateTime(item.at)} · {item.actor}
          </p>
        </li>
      ))}
    </ol>
  )
}

function Cards({ cards, onNavigate, onMore, latest }) {
  if (!cards?.length) return null
  return (
    <div className="mt-2.5 space-y-2.5">
      {cards.map((card, i) => {
        if (card.type === 'complaint') return <ComplaintSummary key={i} c={card} onNavigate={onNavigate} />
        if (card.type === 'timeline') {
          return (
            <div key={i} className="rounded-xl border border-slate-200 bg-white p-3">
              <Timeline card={card} />
            </div>
          )
        }
        if (card.type === 'list') {
          return (
            <div key={i}>
              <p className="mb-1.5 text-xs font-semibold tracking-wide text-slate-500 uppercase">{card.title}</p>
              <div className="space-y-2">
                {card.items.map((c) => (
                  <ComplaintSummary key={c.complaint_id} c={c} onNavigate={onNavigate} compact />
                ))}
              </div>
              {card.pagination && (
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                  <span>
                    Showing {card.pagination.offset + 1}–{card.pagination.offset + card.pagination.shown} of {card.pagination.total}
                  </span>
                  {card.pagination.has_more && latest && (
                    <span className="flex gap-1.5">
                      <button type="button" onClick={() => onMore('Show more')} className="tap-target rounded-full border border-brand-100 bg-brand-50 px-3 py-1.5 font-medium text-brand-700 hover:bg-brand-100">
                        Show more
                      </button>
                      <button type="button" onClick={() => onMore('Show all')} className="tap-target rounded-full border border-slate-200 px-3 py-1.5 font-medium text-slate-600 hover:bg-slate-50">
                        Show all
                      </button>
                    </span>
                  )}
                </div>
              )}
            </div>
          )
        }
        return null
      })}
    </div>
  )
}

function Message({ m, onNavigate, onMore, latest }) {
  if (m.from === 'user') {
    return (
      <div className="flex animate-message justify-end">
        <p className="max-w-[85%] rounded-2xl rounded-br-md bg-brand-700 px-3.5 py-2 text-sm break-words whitespace-pre-wrap text-white">
          {m.reply}
        </p>
      </div>
    )
  }
  return (
    <div className="flex animate-message gap-2.5">
      <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-brand-50 text-brand-600 ring-1 ring-brand-100">
        <Bot className="size-4" aria-hidden="true" />
      </span>
      <div className="min-w-0 max-w-[92%] flex-1">
        <div
          className={cx(
            'rounded-2xl rounded-tl-md px-3.5 py-2.5 text-sm leading-relaxed break-words',
            m.error ? 'bg-red-50 text-red-800 ring-1 ring-red-200' : 'bg-slate-100 text-slate-700',
          )}
        >
          <RichText text={m.reply} />
        </div>
        <Cards cards={m.cards} onNavigate={onNavigate} onMore={onMore} latest={latest} />
      </div>
    </div>
  )
}

function Typing() {
  return (
    <div className="flex animate-message items-center gap-2.5" role="status" aria-label="Assistant is looking this up">
      <span className="grid size-7 place-items-center rounded-full bg-brand-50 text-brand-600 ring-1 ring-brand-100">
        <Bot className="size-4" aria-hidden="true" />
      </span>
      <span className="flex items-center gap-1 rounded-2xl rounded-tl-md bg-slate-100 px-3.5 py-3">
        <span className="typing-dot" />
        <span className="typing-dot" />
        <span className="typing-dot" />
      </span>
    </div>
  )
}

/** The conversation: message list, suggestion chips and input. Used by the panel and the page. */
export default function AssistantChat({ assistant, onNavigate, autoFocus = false, className }) {
  const { messages, pending, send, reset } = assistant
  const [draft, setDraft] = useState('')
  const end = useRef(null)
  const input = useRef(null)
  const last = messages[messages.length - 1]
  // "Show more" continues the most recent list only (that is the list the server will page).
  const lastListId = [...messages].reverse().find((m) => m.cards?.some((c) => c.type === 'list'))?.id

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, pending])

  useEffect(() => {
    if (autoFocus) input.current?.focus({ preventScroll: true })
  }, [autoFocus])

  function submit(e) {
    e.preventDefault()
    if (!draft.trim() || pending) return
    send(draft)
    setDraft('')
  }

  return (
    <div className={cx('flex min-h-0 flex-col', className)}>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-4" aria-live="polite">
        {messages.map((m) => (
          <Message key={m.id} m={m} onNavigate={onNavigate} onMore={send} latest={!pending && m.id === lastListId} />
        ))}
        {pending && <Typing />}
        <div ref={end} />
      </div>

      <div className="border-t border-slate-100 bg-white px-3 pt-2.5 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        {!pending && last?.from === 'assistant' && last.suggestions?.length > 0 && (
          <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1 [scrollbar-width:none]">
            {last.suggestions.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => send(s)}
                className="tap-target shrink-0 animate-fade rounded-full border border-brand-100 bg-brand-50 px-3 py-1.5 text-xs font-medium whitespace-nowrap text-brand-700 transition hover:border-brand-200 hover:bg-brand-100"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        <form onSubmit={submit} className="flex items-end gap-2">
          <label htmlFor="assistant-input" className="sr-only">
            Ask about your complaints
          </label>
          <input
            id="assistant-input"
            ref={input}
            className="input flex-1 rounded-full px-4"
            placeholder="Ask about a complaint, e.g. SSP-2026-000123"
            value={draft}
            maxLength={500}
            onChange={(e) => setDraft(e.target.value)}
            autoComplete="off"
          />
          <button
            type="submit"
            className="grid size-10 shrink-0 place-items-center rounded-full bg-brand-700 text-white transition hover:bg-brand-800 disabled:opacity-40"
            disabled={!draft.trim() || pending}
            aria-label="Send"
          >
            <ArrowUp className="size-4.5" />
          </button>
        </form>
        <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-slate-400">
          <span className="flex items-center gap-1">
            <ShieldCheck className="size-3.5" aria-hidden="true" />
            Answers come only from SafeSpeak records you can access
          </span>
          <button type="button" onClick={reset} className="-my-2 flex tap-target items-center gap-1 rounded px-2 hover:text-slate-600">
            <RotateCcw className="size-3" aria-hidden="true" /> Clear
          </button>
        </div>
      </div>
    </div>
  )
}

export function AssistantIntro() {
  return (
    <div className="flex items-center gap-2 text-xs text-slate-500">
      <Database className="size-3.5" aria-hidden="true" /> Database-backed · no external AI · nothing you type is stored
    </div>
  )
}
