import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { useAuth } from './auth'

const RealtimeContext = createContext({ status: 'offline', revision: 0 })
const POLL_MS = Number(import.meta.env.VITE_POLL_INTERVAL_MS || 30000)

function wsBase() {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL
  const apiUrl = new URL(api.defaults.baseURL)
  apiUrl.protocol = apiUrl.protocol === 'https:' ? 'wss:' : 'ws:'
  apiUrl.pathname = '/ws/events/'
  return apiUrl.toString()
}

export function RealtimeProvider({ children }) {
  const { user } = useAuth()
  const sequenceKey = `realtime_sequence_${user?.customer || 'global'}`
  const [status, setStatus] = useState(navigator.onLine ? 'connecting' : 'offline')
  const [revision, setRevision] = useState(0)
  const lastSequence = useRef(Number(sessionStorage.getItem(sequenceKey) || 0))
  const reconnect = useRef(1000)
  const socket = useRef(null)
  const timer = useRef(null)
  const mounted = useRef(true)
  const connect = useCallback(async () => {
    if (!mounted.current || socket.current?.readyState === WebSocket.CONNECTING || socket.current?.readyState === WebSocket.OPEN) return
    if (!navigator.onLine || !localStorage.getItem('access_token')) return setStatus('offline')
    try {
      setStatus('connecting')
      const { data } = await api.post('/realtime/ticket/')
      const url = new URL(wsBase())
      url.searchParams.set('ticket', data.ticket)
      url.searchParams.set('since', lastSequence.current)
      const ws = new WebSocket(url)
      socket.current = ws
      ws.onopen = () => { if (mounted.current) { reconnect.current = 1000; setStatus('live') } }
      ws.onmessage = ({ data: payload }) => { const event = JSON.parse(payload); if (event.sequence) { lastSequence.current = event.sequence; sessionStorage.setItem(sequenceKey, event.sequence) } setRevision((value) => value + 1) }
      ws.onclose = () => { if (socket.current !== ws) return; socket.current = null; if (mounted.current) { setStatus(navigator.onLine ? 'polling' : 'offline'); timer.current = setTimeout(connect, reconnect.current); reconnect.current = Math.min(30000, reconnect.current * 2) } }
      ws.onerror = () => ws.close()
    } catch { if (mounted.current) { setStatus('polling'); timer.current = setTimeout(connect, reconnect.current); reconnect.current = Math.min(30000, reconnect.current * 2) } }
  }, [sequenceKey])
  useEffect(() => {
    mounted.current = true
    lastSequence.current = Number(sessionStorage.getItem(sequenceKey) || 0)
    connect()
    const poll = setInterval(() => { if (socket.current?.readyState !== WebSocket.OPEN && navigator.onLine) setRevision((value) => value + 1) }, POLL_MS)
    const online = () => connect()
    const offline = () => setStatus('offline')
    addEventListener('online', online); addEventListener('offline', offline)
    return () => { mounted.current = false; clearInterval(poll); clearTimeout(timer.current); const current = socket.current; socket.current = null; if (current) { current.onopen = null; current.onmessage = null; current.onclose = null; current.onerror = null; current.close() } removeEventListener('online', online); removeEventListener('offline', offline) }
  }, [connect, sequenceKey])
  const value = useMemo(() => ({ status, revision }), [status, revision])
  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>
}

export const useRealtime = () => useContext(RealtimeContext)
