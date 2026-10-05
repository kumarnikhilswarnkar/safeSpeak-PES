// SafeSpeak's own mark: a shield with a speech line. Deliberately not the PES University logo.
export default function Wordmark({ size = 'md', inverse = false }) {
  return (
    <span className={`wordmark wordmark--${size}${inverse ? ' wordmark--inverse' : ''}`}>
      <svg className="wordmark__icon" viewBox="0 0 32 32" aria-hidden="true">
        <path
          d="M16 2 4 6.5v8.7C4 22.6 9.1 28.4 16 30c6.9-1.6 12-7.4 12-14.8V6.5L16 2Z"
          fill={inverse ? '#ffffff' : 'var(--color-navy-700)'}
        />
        <path d="M10 12.5h12M10 17h8" stroke="var(--color-orange-500)" strokeWidth="2.4" strokeLinecap="round" />
      </svg>
      <span className="wordmark__text">
        SafeSpeak <span className="wordmark__accent">PES</span>
      </span>
    </span>
  )
}
