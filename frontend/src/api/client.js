const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

function errorMessage(body, status) {
  // 502/504 come from the dev proxy (or a gateway) when the API is not running.
  if (status === 502 || status === 504) return 'Cannot reach the SafeSpeak server'
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  return `Request failed (${status})`
}

/**
 * Calls the SafeSpeak API and returns parsed JSON (or a Blob with responseType 'blob').
 * body is sent as JSON; rawBody (a File/Blob, e.g. a photo) is sent as-is with its type.
 * Throws ApiError for HTTP errors and for network failures (status 0).
 */
export async function apiRequest(path, { method = 'GET', body, rawBody, token, signal, responseType } = {}) {
  const headers = { Accept: responseType === 'blob' ? '*/*' : 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (rawBody !== undefined) headers['Content-Type'] = rawBody.type || 'application/octet-stream'
  if (token) headers.Authorization = `Bearer ${token}`

  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: rawBody !== undefined ? rawBody : body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new ApiError('Cannot reach the SafeSpeak server', 0, null)
  }

  if (responseType === 'blob' && response.ok) return response.blob()

  const text = await response.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }

  if (!response.ok) {
    throw new ApiError(errorMessage(data, response.status), response.status, data)
  }
  return data
}
