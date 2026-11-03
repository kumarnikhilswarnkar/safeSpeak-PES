import { Camera, Lock, Save, ShieldCheck, Trash2, UserRound } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { deletePhoto, getProfile, updateProfile, uploadPhoto } from '../api/profile.js'
import { useAuth } from '../auth/AuthContext.jsx'
import { ROLE_LABEL } from '../auth/roles.js'
import AppShell from '../components/AppShell.jsx'
import Avatar from '../components/Avatar.jsx'
import { useToast } from '../components/Toast.jsx'
import { Alert, Badge, Card, ErrorState, LoadingState, PageHeader, Spinner } from '../components/ui.jsx'
import useLoader from '../hooks/useLoader.js'

const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const PHOTO_MAX_BYTES = 2 * 1024 * 1024 // the server enforces the same limit

function ReadOnly({ label, children, hint }) {
  return (
    <div>
      <p className="label flex items-center gap-1.5">
        {label} <Lock className="size-3.5 text-slate-400" aria-label="read-only" />
      </p>
      <div className="flex min-h-10 items-center rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">{children}</div>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  )
}

function PhotoCard({ profile, onChange }) {
  const { authRequest } = useAuth()
  const toast = useToast()
  const input = useRef(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function choose(e) {
    const file = e.target.files?.[0]
    e.target.value = '' // allow choosing the same file again
    if (!file) return
    setError(null)
    // Quick checks for a friendly message; the server validates the actual content.
    if (!PHOTO_TYPES.includes(file.type)) return setError('Choose a JPEG, PNG or WebP image.')
    if (file.size > PHOTO_MAX_BYTES) return setError('The photo must be 2 MB or smaller.')
    setBusy(true)
    try {
      onChange(await uploadPhoto(authRequest, file))
      toast('Your profile photo was updated.', { title: 'Photo saved' })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    setBusy(true)
    setError(null)
    try {
      onChange(await deletePhoto(authRequest))
      toast('Your profile photo was removed.')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Profile photo" icon={Camera}>
      <div className="flex flex-col items-center text-center">
        <div className="relative">
          <Avatar className="size-28 text-3xl shadow-(--shadow-card)" />
          {busy && (
            <span className="absolute inset-0 grid place-items-center rounded-full bg-white/70">
              <Spinner className="size-6 text-brand-600" />
            </span>
          )}
        </div>
        <p className="mt-3 text-sm font-medium text-slate-900">{profile.name}</p>
        <p className="text-xs text-slate-500">JPEG, PNG or WebP · up to 2 MB</p>
        <input ref={input} type="file" accept={PHOTO_TYPES.join(',')} className="sr-only" onChange={choose} aria-label="Choose a profile photo" tabIndex={-1} />
        <div className="mt-4 flex w-full flex-col gap-2 sm:flex-row sm:justify-center">
          <button type="button" className="btn-primary" onClick={() => input.current?.click()} disabled={busy}>
            <Camera className="size-4" /> {profile.has_photo ? 'Replace photo' : 'Upload photo'}
          </button>
          {profile.has_photo && (
            <button type="button" className="btn-secondary" onClick={remove} disabled={busy}>
              <Trash2 className="size-4" /> Remove
            </button>
          )}
        </div>
        {error && (
          <div className="mt-3 w-full animate-pop text-left">
            <Alert tone="red">{error}</Alert>
          </div>
        )}
        <p className="mt-4 text-xs text-slate-500">
          Your photo is private: it is shown only to you, in your own account.
        </p>
      </div>
    </Card>
  )
}

function DetailsForm({ profile, onChange }) {
  const { authRequest } = useAuth()
  const toast = useToast()
  const [name, setName] = useState(profile.name)
  const [phone, setPhone] = useState(profile.phone ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const dirty = name.trim() !== profile.name || phone.trim() !== (profile.phone ?? '')

  async function submit(e) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      const changes = {}
      if (name.trim() !== profile.name) changes.name = name
      if (phone.trim() !== (profile.phone ?? '')) changes.phone = phone.trim()
      const saved = await updateProfile(authRequest, changes)
      onChange(saved)
      setName(saved.name)
      setPhone(saved.phone ?? '')
      toast('Your profile was saved.', { title: 'Saved' })
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card title="Personal details" icon={UserRound} className="lg:col-span-2">
      <form onSubmit={submit} className="space-y-5" noValidate>
        {error && (
          <div className="animate-pop">
            <Alert tone="red">{error}</Alert>
          </div>
        )}
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label htmlFor="profile-name" className="label">
              Full name
            </label>
            <input id="profile-name" className="input" value={name} maxLength={120} autoComplete="name" onChange={(e) => setName(e.target.value)} required />
          </div>
          <div>
            <label htmlFor="profile-phone" className="label">
              Phone number <span className="font-normal text-slate-400">(optional)</span>
            </label>
            <input
              id="profile-phone"
              className="input"
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              placeholder="+91 98450 12345"
              value={phone}
              maxLength={20}
              onChange={(e) => setPhone(e.target.value)}
            />
          </div>
          <ReadOnly label="Institutional email" hint="Changing your email needs verification by an administrator.">
            <span className="truncate">{profile.email}</span>
          </ReadOnly>
          <ReadOnly label="Department / office" hint="Set by the institution; ask an administrator to change it.">
            {profile.department ? `${profile.department.name} (${profile.department.code})` : '—'}
          </ReadOnly>
          <ReadOnly label="Role">
            {ROLE_LABEL[profile.role] ?? profile.role}
            {profile.authority_level ? ` · L${profile.authority_level}` : ''}
          </ReadOnly>
          <ReadOnly label="Account status">
            <Badge tone={profile.is_active ? 'green' : 'red'}>{profile.is_active ? 'Active' : 'Disabled'}</Badge>
          </ReadOnly>
        </div>
        <div className="flex flex-col-reverse gap-3 border-t border-slate-100 pt-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="flex items-center gap-1.5 text-xs text-slate-500">
            <ShieldCheck className="size-4 shrink-0 text-slate-400" aria-hidden="true" />
            Role, department and access permissions can only be changed by an administrator.
          </p>
          <button type="submit" className="btn-primary" disabled={!dirty || saving || name.trim().length < 2}>
            {saving ? <Spinner /> : <Save className="size-4" />} Save changes
          </button>
        </div>
      </form>
    </Card>
  )
}

export default function ProfilePage() {
  const { authRequest, updateUser } = useAuth()
  const loader = useCallback(() => getProfile(authRequest), [authRequest])
  const { data, error, loading, reload } = useLoader(loader)
  const [profile, setProfile] = useState(null)

  useEffect(() => {
    if (data) setProfile(data)
  }, [data])

  const change = useCallback(
    (saved) => {
      setProfile(saved)
      updateUser(saved) // header and sidebar show the new name/photo immediately
    },
    [updateUser],
  )

  return (
    <AppShell>
      <PageHeader eyebrow="Account" title="Your profile" description="Your details as stored in SafeSpeak. You can change your name, phone number and photo." />
      {loading && !profile ? (
        <LoadingState variant="inline" label="Loading your profile…" />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : (
        profile && (
          <div className="stagger grid gap-6 lg:grid-cols-3">
            <PhotoCard profile={profile} onChange={change} />
            <DetailsForm key={profile.id} profile={profile} onChange={change} />
          </div>
        )
      )}
    </AppShell>
  )
}
