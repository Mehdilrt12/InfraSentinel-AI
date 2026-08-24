import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'

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
  const [status, setStatus] = useState(navigator.onLine ? 'connecting' : 'offline')
  const [revision, setRevision] = useState(0)
  const lastSequence = useRef(Number(sessionStorage.getItem('realtime_sequence') || 0))
  const reconnect = useRef(1000)
  const socket = useRef(null)
  const timer = useRef(null)
  const connect = useCallback(async () => {
    if (!navigator.onLine || !localStorage.getItem('access_token')) return setStatus('offline')
    try {
      setStatus('connecting')
      const { data } = await api.post('/realtime/ticket/')
      const url = new URL(wsBase())
      url.searchParams.set('ticket', data.ticket)
      url.searchParams.set('since', lastSequence.current)
      const ws = new WebSocket(url)
      socket.current = ws
      ws.onopen = () => { reconnect.current = 1000; setStatus('live') }
      ws.onmessage = ({ data: payload }) => { const event = JSON.parse(payload); if (event.sequence) { lastSequence.current = event.sequence; sessionStorage.setItem('realtime_sequence', event.sequence) } setRevision((value) => value + 1) }
      ws.onclose = () => { setStatus(navigator.onLine ? 'polling' : 'offline'); timer.current = setTimeout(connect, reconnect.current); reconnect.current = Math.min(30000, reconnect.current * 2) }
      ws.onerror = () => ws.close()
    } catch { setStatus('polling'); timer.current = setTimeout(connect, reconnect.current); reconnect.current = Math.min(30000, reconnect.current * 2) }
  }, [])
  useEffect(() => { connect(); const poll = setInterval(() => { if (socket.current?.readyState !== WebSocket.OPEN && navigator.onLine) setRevision((value) => value + 1) }, POLL_MS); const online = () => connect(); const offline = () => setStatus('offline'); addEventListener('online', online); addEventListener('offline', offline); return () => { clearInterval(poll); clearTimeout(timer.current); socket.current?.close(); removeEventListener('online', online); removeEventListener('offline', offline) } }, [connect])
  const value = useMemo(() => ({ status, revision }), [status, revision])
  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>
}

export const useRealtime = () => useContext(RealtimeContext)
