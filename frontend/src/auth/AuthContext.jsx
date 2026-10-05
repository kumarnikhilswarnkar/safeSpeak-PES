import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'

import { fetchCurrentUser, login as apiLogin } from '../api/auth.js'
import { apiRequest } from '../api/client.js'

// The access token lives in sessionStorage: it survives a page reload but is
// discarded when the tab closes. It holds no secrets beyond the token itself,
// and the server re-checks the account on every request.
const TOKEN_KEY = 'safespeak.accessToken'

const AuthContext = createContext(null)

function readToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function writeToken(token) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token)
    else sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    // Storage unavailable (private mode etc.): the session lasts until reload.
  }
}

// Expiry (ms since epoch) read from the token payload, used only to sign the
// user out on time. The server validates the token independently.
function tokenExpiry(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null
  } catch {
    return null
  }
}

const ANONYMOUS = { status: 'anonymous', user: null, token: null }

export function AuthProvider({ children }) {
  const [state, setState] = useState({ status: 'loading', user: null, token: null })
  const expiryTimer = useRef(null)

  const logout = useCallback(() => {
    clearTimeout(expiryTimer.current)
    writeToken(null)
    setState(ANONYMOUS)
  }, [])

  const startSession = useCallback(
    (token, user) => {
      const expiresAt = tokenExpiry(token)
      clearTimeout(expiryTimer.current)
      if (expiresAt) expiryTimer.current = setTimeout(logout, Math.max(expiresAt - Date.now(), 0))
      writeToken(token)
      setState({ status: 'authenticated', user, token })
    },
    [logout],
  )

  // Restore a session after a reload by asking the server who the token belongs to.
  useEffect(() => {
    const token = readToken()
    const expiresAt = token && tokenExpiry(token)
    if (!token || (expiresAt && expiresAt <= Date.now())) {
      writeToken(null)
      setState(ANONYMOUS)
      return undefined
    }
    const controller = new AbortController()
    fetchCurrentUser(token, controller.signal)
      .then((user) => startSession(token, user))
      .catch((error) => {
        if (error.name === 'AbortError') return
        if (error.status === 401 || error.status === 403) writeToken(null)
        setState(ANONYMOUS)
      })
    return () => controller.abort()
  }, [startSession])

  useEffect(() => () => clearTimeout(expiryTimer.current), [])

  const login = useCallback(
    async (email, password) => {
      const { access_token: token } = await apiLogin(email, password)
      const user = await fetchCurrentUser(token)
      startSession(token, user)
      return user
    },
    [startSession],
  )

  // Authenticated API call; an expired or revoked session signs the user out.
  const authRequest = useCallback(
    async (path, options = {}) => {
      try {
        return await apiRequest(path, { ...options, token: state.token })
      } catch (error) {
        if (error.status === 401) logout()
        throw error
      }
    },
    [state.token, logout],
  )

  const value = useMemo(
    () => ({ ...state, login, logout, authRequest }),
    [state, login, logout, authRequest],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
