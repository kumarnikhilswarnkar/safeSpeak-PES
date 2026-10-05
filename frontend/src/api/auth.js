import { apiRequest } from './client.js'

export function login(email, password) {
  return apiRequest('/auth/login', { method: 'POST', body: { email, password } })
}

export function fetchCurrentUser(token, signal) {
  return apiRequest('/auth/me', { token, signal })
}
