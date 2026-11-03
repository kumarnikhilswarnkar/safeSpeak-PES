// Shared UI primitives. Plain React + Tailwind; no component library needed.
import { AlertTriangle, Inbox, Loader2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

export function cx(...classes) {
  return classes.filter(Boolean).join(' ')
}

const reducedMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/** Heading text that appears word by word. Screen readers get the plain text once. */
export function AnimatedText({ text, as: Tag = 'span', className, delay = 0, step = 45 }) {
  const words = String(text).split(' ')
  return (
    <Tag className={className} aria-label={text}>
      {words.map((w, i) => (
        <span key={`${w}-${i}`}>
          <span aria-hidden="true" className="inline-block animate-word" style={{ animationDelay: `${delay + i * step}ms` }}>
            {w}
          </span>
          {i < words.length - 1 ? ' ' : ''}
        </span>
      ))}
    </Tag>
  )
}

/** Animates a number from 0 to its value once (numbers only; other values render as-is). */
export function CountUp({ value, duration = 650 }) {
  const numeric = typeof value === 'number' && Number.isFinite(value)
  const [shown, setShown] = useState(numeric && !reducedMotion() ? 0 : value)
  useEffect(() => {
    if (!numeric || reducedMotion()) {
      setShown(value)
      return undefined
    }
    let frame
    const start = performance.now()
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      setShown(Math.round(value * (1 - (1 - t) ** 3)))
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    // Browsers pause animation frames in background tabs: always land on the real value.
    const done = setTimeout(() => {
      cancelAnimationFrame(frame)
      setShown(value)
    }, duration + 50)
    return () => {
      cancelAnimationFrame(frame)
      clearTimeout(done)
    }
  }, [value, numeric, duration])
  return numeric ? shown : value
}

export function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <p className="eyebrow mb-1">{eyebrow}</p>}
        {typeof title === 'string' ? (
          <AnimatedText as="h1" text={title} className="text-2xl font-semibold tracking-tight text-balance text-slate-900 sm:text-[1.65rem]" />
        ) : (
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        )}
        {description && <p className="mt-1 max-w-3xl animate-fade text-sm text-slate-500 [animation-delay:150ms]">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Card({ title, subtitle, icon: Icon, actions, children, className, bodyClassName, id }) {
  return (
    <section className={cx('card', className)} aria-labelledby={title ? id : undefined}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
          <div className="flex min-w-0 items-start gap-2.5">
            {Icon && <Icon className="mt-0.5 size-4 shrink-0 text-slate-400" aria-hidden="true" />}
            <div className="min-w-0">
              <h2 id={id} className="text-sm font-semibold text-slate-900">
                {title}
              </h2>
              {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx('p-5', bodyClassName)}>{children}</div>
    </section>
  )
}

const TONES = {
  slate: 'bg-slate-100 text-slate-700 ring-slate-200',
  brand: 'bg-brand-50 text-brand-700 ring-brand-100',
  accent: 'bg-accent-50 text-accent-600 ring-accent-100',
  green: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  amber: 'bg-amber-50 text-amber-800 ring-amber-200',
  red: 'bg-red-50 text-red-700 ring-red-200',
  violet: 'bg-violet-50 text-violet-700 ring-violet-200',
  sky: 'bg-sky-50 text-sky-700 ring-sky-200',
}

export function Badge({ tone = 'slate', icon: Icon, children, className }) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset',
        TONES[tone],
        className,
      )}
    >
      {Icon && <Icon className="size-3.5" aria-hidden="true" />}
      {children}
    </span>
  )
}

export function StatCard({ label, value, icon: Icon, tone = 'brand', hint, onClick, active }) {
  const iconTone = {
    brand: 'bg-brand-50 text-brand-600',
    accent: 'bg-accent-50 text-accent-600',
    green: 'bg-emerald-50 text-emerald-600',
    amber: 'bg-amber-50 text-amber-600',
    red: 'bg-red-50 text-red-600',
    violet: 'bg-violet-50 text-violet-600',
    slate: 'bg-slate-100 text-slate-600',
  }[tone]
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={cx(
        'card flex items-start gap-3 p-4 text-left',
        onClick ? 'card-hover cursor-pointer' : 'transition-shadow hover:shadow-(--shadow-pop)',
        active && 'border-brand-500 ring-2 ring-brand-100',
      )}
    >
      {Icon && (
        <span className={cx('grid size-9 shrink-0 place-items-center rounded-lg', iconTone)}>
          <Icon className="size-4.5" aria-hidden="true" />
        </span>
      )}
      <span className="min-w-0">
        <span className="block text-xs font-medium text-slate-500">{label}</span>
        <span className="mt-0.5 block text-2xl font-semibold tracking-tight text-slate-900 tabular-nums">
          <CountUp value={value} />
        </span>
        {hint && <span className="mt-0.5 block text-xs text-slate-500">{hint}</span>}
      </span>
    </Tag>
  )
}

export function Spinner({ className }) {
  return <Loader2 className={cx('size-4 animate-spin', className)} aria-hidden="true" />
}

/** Page-shaped placeholder while data loads (stat tiles + content cards). */
export function LoadingState({ label = 'Loading…', variant = 'page' }) {
  if (variant === 'inline') {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500" role="status">
        <Spinner /> {label}
      </div>
    )
  }
  return (
    <div role="status" aria-live="polite" className="animate-fade">
      <span className="sr-only">{label}</span>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="card flex items-start gap-3 p-4">
            <Skeleton className="size-9 rounded-lg" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-3 w-2/3" />
              <Skeleton className="h-6 w-1/3" />
            </div>
          </div>
        ))}
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <div className="card space-y-4 p-5 xl:col-span-2">
          <Skeleton className="h-4 w-40" />
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="flex items-center gap-4">
              <Skeleton className="h-10 flex-1" />
              <Skeleton className="hidden h-6 w-20 sm:block" />
            </div>
          ))}
        </div>
        <div className="card space-y-3 p-5">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-5/6" />
          <Skeleton className="h-3 w-4/6" />
        </div>
      </div>
    </div>
  )
}

export function Skeleton({ className }) {
  return <div className={cx('skeleton', className)} aria-hidden="true" />
}

export function EmptyState({ icon: Icon = Inbox, title, description, action }) {
  return (
    <div className="flex animate-enter flex-col items-center justify-center px-6 py-12 text-center">
      <span className="grid size-11 place-items-center rounded-full bg-slate-100 text-slate-400">
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <p className="mt-3 text-sm font-medium text-slate-800">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-slate-500">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="card flex items-start gap-3 border-red-200 bg-red-50/50 p-4" role="alert">
      <AlertTriangle className="mt-0.5 size-5 shrink-0 text-red-600" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-red-800">Something went wrong</p>
        <p className="mt-0.5 text-sm text-red-700">{error?.message ?? String(error)}</p>
      </div>
      {onRetry && (
        <button type="button" className="btn-secondary" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}

export function Alert({ tone = 'brand', icon: Icon, title, children, className }) {
  const styles = {
    brand: 'border-brand-100 bg-brand-50 text-brand-800',
    amber: 'border-amber-200 bg-amber-50 text-amber-900',
    red: 'border-red-200 bg-red-50 text-red-800',
    green: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    slate: 'border-slate-200 bg-slate-50 text-slate-700',
  }[tone]
  return (
    <div className={cx('flex gap-3 rounded-lg border px-4 py-3 text-sm', styles, className)} role="status">
      {Icon && <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />}
      <div className="min-w-0">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={title ? 'mt-0.5 opacity-90' : ''}>{children}</div>}
      </div>
    </div>
  )
}

/** Accessible modal dialog: focus moves in, Escape closes, backdrop click closes. */
export function Modal({ open, title, description, onClose, children, footer, size = 'md' }) {
  const panel = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const previous = document.activeElement
    panel.current?.focus()
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      previous?.focus?.()
    }
  }, [open, onClose])
  if (!open) return null
  // Portal to <body>: an animated (transformed) page container would otherwise become the
  // containing block for this fixed overlay and squeeze it into the page column.
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4">
      <div className="absolute inset-0 animate-fade bg-slate-900/40 backdrop-blur-[2px]" onClick={onClose} aria-hidden="true" />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={cx(
          // Bottom sheet on phones, centred dialog from 640px; never taller than the screen.
          'relative flex max-h-[calc(100dvh-1rem)] w-full animate-sheet flex-col rounded-t-2xl bg-white shadow-(--shadow-pop) outline-none sm:max-h-[calc(100dvh-4rem)] sm:animate-pop sm:rounded-xl',
          size === 'lg' ? 'max-w-2xl' : 'max-w-md',
        )}
      >
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">{title}</h2>
            {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
          </div>
          <button type="button" className="btn-ghost -mt-1 -mr-2 grid size-10 shrink-0 place-items-center p-0" onClick={onClose} aria-label="Close">
            <X className="size-4.5" />
          </button>
        </div>
        <div className="min-h-0 overflow-y-auto overscroll-contain px-5 py-4">{children}</div>
        {footer && (
          <div className="flex flex-col-reverse gap-2 border-t border-slate-100 px-5 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:flex-row sm:justify-end [&>*]:w-full sm:[&>*]:w-auto">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  )
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-slate-200" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.value}
          type="button"
          role="tab"
          aria-selected={value === t.value}
          onClick={() => onChange(t.value)}
          className={cx(
            '-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors',
            value === t.value
              ? 'border-brand-600 text-brand-700'
              : 'border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-700',
          )}
        >
          {t.label}
          {t.count != null && (
            <span
              className={cx(
                'rounded-full px-1.5 text-xs tabular-nums',
                value === t.value ? 'bg-brand-100 text-brand-700' : 'bg-slate-100 text-slate-600',
              )}
            >
              {t.count}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

export function KeyValue({ label, children }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-4">
      <dt className="w-40 shrink-0 text-sm text-slate-500">{label}</dt>
      <dd className="min-w-0 text-sm text-slate-900">{children}</dd>
    </div>
  )
}
