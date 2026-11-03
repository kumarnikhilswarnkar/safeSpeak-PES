import { useEffect, useState } from 'react'

import { getPhoto } from '../api/profile.js'
import { useAuth } from '../auth/AuthContext.jsx'
import { cx } from './ui.jsx'

export function initialsOf(name = '') {
  return name
    .split(' ')
    .filter(Boolean)
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
}

/**
 * The signed-in user's avatar. The photo is private: it is fetched with the session
 * token (not a public URL) and shown from a temporary object URL. Without a photo,
 * or if loading fails, the user's initials are shown.
 */
export default function Avatar({ className = 'size-8 text-xs', ring = false }) {
  const { user, authRequest, photoVersion } = useAuth()
  const [url, setUrl] = useState(null)

  useEffect(() => {
    if (!user?.has_photo) {
      setUrl(null)
      return undefined
    }
    let objectUrl
    let cancelled = false
    getPhoto(authRequest)
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => !cancelled && setUrl(null))
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [user?.has_photo, user?.id, photoVersion, authRequest])

  return (
    <span
      className={cx(
        'grid shrink-0 place-items-center overflow-hidden rounded-full bg-gradient-to-br from-brand-100 to-brand-200 font-semibold text-brand-700',
        ring && 'ring-2 ring-white/80',
        className,
      )}
      aria-hidden="true"
    >
      {url ? <img src={url} alt="" className="size-full object-cover" /> : initialsOf(user?.name)}
    </span>
  )
}
