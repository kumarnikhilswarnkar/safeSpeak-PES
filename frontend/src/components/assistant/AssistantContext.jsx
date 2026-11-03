import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'

import { askAssistant } from '../../api/assistant.js'
import { useAuth } from '../../auth/AuthContext.jsx'

const AssistantContext = createContext(null)

const greeting = (user) => ({
  id: 'greeting',
  from: 'assistant',
  reply:
    `Hi ${user.name.split(' ')[0]}! I can look up your complaints in SafeSpeak — status, deadline, who is handling it, ` +
    'escalation and the full timeline. I only answer from SafeSpeak records you are allowed to see.',
  cards: [],
  suggestions: ['Show my complaints', 'Any overdue complaints?', 'What can you do?'],
})

/**
 * Conversation state shared by the floating panel and the full Assistant page.
 * Kept in memory only (not in browser storage) and cleared when the account changes.
 */
export function AssistantProvider({ children }) {
  const { user, authRequest } = useAuth()
  const [messages, setMessages] = useState([])
  const [pending, setPending] = useState(false)
  const [open, setOpen] = useState(false)
  // Conversation state sent back with every message (re-authorized by the server each time):
  // the complaint being discussed and the last list shown.
  const context = useRef(null)
  const listContext = useRef(null)
  const seq = useRef(0)
  const userId = user?.id

  useEffect(() => {
    context.current = null
    listContext.current = null
    setOpen(false)
    setMessages(user ? [greeting(user)] : [])
  }, [userId])

  const send = useCallback(
    async (text) => {
      const message = text.trim().slice(0, 500)
      if (!message || pending) return
      const id = ++seq.current
      setMessages((m) => [...m, { id: `u${id}`, from: 'user', reply: message }])
      setPending(true)
      try {
        const r = await askAssistant(authRequest, message, context.current, listContext.current)
        context.current = r.complaint_id ?? (r.intent === 'not_found' ? null : context.current)
        if (r.list_context) listContext.current = r.list_context
        setMessages((m) => [...m, { id: `a${id}`, from: 'assistant', ...r }])
      } catch (err) {
        setMessages((m) => [
          ...m,
          { id: `a${id}`, from: 'assistant', error: true, reply: err.message || 'The assistant is unavailable right now.', cards: [], suggestions: [] },
        ])
      } finally {
        setPending(false)
      }
    },
    [authRequest, pending],
  )

  const reset = useCallback(() => {
    context.current = null
    listContext.current = null
    if (user) setMessages([greeting(user)])
  }, [user])

  const value = useMemo(() => ({ messages, pending, send, reset, open, setOpen }), [messages, pending, send, reset, open])
  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>
}

export function useAssistant() {
  const value = useContext(AssistantContext)
  if (!value) throw new Error('useAssistant must be used inside AssistantProvider')
  return value
}
