// SafeSpeak's own mark: a shield with a speech line. The official PES University logo
// is shown separately (PesLogo) on light backgrounds; this is the product identity.
export function ShieldMark({ inverse = false, className = 'size-7' }) {
  return (
    <svg className={className} viewBox="0 0 32 32" aria-hidden="true">
      <path
        d="M16 2 4 6.5v8.7C4 22.6 9.1 28.4 16 30c6.9-1.6 12-7.4 12-14.8V6.5L16 2Z"
        fill={inverse ? '#ffffff' : 'var(--color-brand-700)'}
      />
      <path d="M10 12.5h12M10 17h8" stroke="var(--color-accent-500)" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  )
}

export default function Wordmark({ inverse = false, size = 'md' }) {
  const text = size === 'lg' ? 'text-2xl' : 'text-base'
  return (
    <span className="inline-flex items-center gap-2">
      <ShieldMark inverse={inverse} className={size === 'lg' ? 'size-9' : 'size-7'} />
      <span className={`${text} font-semibold tracking-tight whitespace-nowrap ${inverse ? 'text-white' : 'text-brand-900'}`}>
        SafeSpeak <span className="text-accent-500">PES</span>
      </span>
    </span>
  )
}
