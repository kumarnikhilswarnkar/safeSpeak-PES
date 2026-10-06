import { CheckCircle2, Info, TriangleAlert, X } from 'lucide-react'
import { createContext, useCallback, useContext, useMemo, useState } from 'react'

const ToastContext = createContext(null)

const STYLES = {
  success: { icon: CheckCircle2, className: 'text-emerald-600' },
  error: { icon: TriangleAlert, className: 'text-red-600' },
  info: { icon: Info, className: 'text-brand-600' },
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const dismiss = useCallback((id) => setToasts((all) => all.filter((t) => t.id !== id)), [])

  const toast = useCallback(
    (message, { tone = 'success', title, duration = 4500 } = {}) => {
      const id = Math.random().toString(36).slice(2)
      setToasts((all) => [...all.slice(-3), { id, message, tone, title }])
      setTimeout(() => dismiss(id), duration)
    },
    [dismiss],
  )

  const value = useMemo(() => ({ toast }), [toast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed right-4 bottom-4 z-[60] flex w-full max-w-sm flex-col gap-2" aria-live="polite">
        {toasts.map((t) => {
          const { icon: Icon, className } = STYLES[t.tone] ?? STYLES.info
          return (
            <div key={t.id} className="card pointer-events-auto flex items-start gap-3 p-3.5 shadow-(--shadow-pop)">
              <Icon className={`mt-0.5 size-4.5 shrink-0 ${className}`} aria-hidden="true" />
              <div className="min-w-0 flex-1 text-sm">
                {t.title && <p className="font-medium text-slate-900">{t.title}</p>}
                <p className="text-slate-600">{t.message}</p>
              </div>
              <button type="button" onClick={() => dismiss(t.id)} className="text-slate-400 hover:text-slate-600" aria-label="Dismiss">
                <X className="size-4" />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used inside <ToastProvider>')
  return context.toast
}
