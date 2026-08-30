import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, listData } from './api'
import { useRealtime } from './realtime'

const EVENT_RULES = [
  [/^\/dashboard\//, ['metric.update', 'machine.online', 'machine.offline', 'alert.created', 'alert.updated', 'anomaly.detected']],
  [/^\/metrics\//, ['metric.update']],
  [/^\/machines\//, ['metric.update', 'machine.online', 'machine.offline']],
  [/^\/alerts\//, ['alert.created', 'alert.updated']],
  [/^\/anomalies\//, ['anomaly.detected']],
  [/^\/ml\//, ['anomaly.detected', 'model.trained']],
  [/^\/(vmware|hyperv)\//, ['metric.update', 'connector.updated']],
  [/^\/assets\//, ['metric.update', 'connector.updated']],
]

function eventsForPath(path) {
  return EVENT_RULES.find(([pattern]) => pattern.test(path || ''))?.[1] || []
}

export function realtimeRevisionFor(eventRevisions = {}, pollRevision = 0, subscribedEvents = []) {
  return pollRevision + subscribedEvents.reduce((total, type) => total + (eventRevisions[type] || 0), 0)
}

export function apiErrorMessage(error, fallback = 'Une erreur inattendue est survenue.') {
  const payload = error?.response?.data
  if (typeof payload?.detail === 'string') return payload.detail
  if (typeof payload === 'string') return payload
  if (payload && typeof payload === 'object') {
    const first = Object.values(payload).flat().find((value) => typeof value === 'string')
    if (first) return first
  }
  if (typeof navigator !== 'undefined' && !navigator.onLine) return 'Vous êtes hors ligne.'
  if (!error?.response) return 'Le serveur API est injoignable.'
  return fallback
}

export function useApi(path, { list = false, enabled = true, realtimeEvents } = {}) {
  const { eventRevisions, pollRevision } = useRealtime()
  const [localRevision, setLocalRevision] = useState(0)
  const [state, setState] = useState({ data: list ? [] : null, loading: true, error: null, partial: false })
  const subscribedEvents = useMemo(() => realtimeEvents || eventsForPath(path), [path, realtimeEvents])
  const realtimeRevision = useMemo(
    () => realtimeRevisionFor(eventRevisions, pollRevision, subscribedEvents),
    [eventRevisions, pollRevision, subscribedEvents],
  )
  const refresh = useCallback(() => setLocalRevision((value) => value + 1), [])

  useEffect(() => {
    if (!enabled || !path) {
      setState({ data: list ? [] : null, loading: false, error: null, partial: false })
      return undefined
    }
    let active = true
    setState((old) => ({ ...old, loading: old.data == null || (list && !old.data.length), error: null }))
    api.get(path)
      .then(({ data }) => {
        if (active) setState({ data: list ? listData(data) : data, loading: false, error: null, partial: Boolean(data?.partial) })
      })
      .catch((error) => {
        if (active) setState((old) => ({ ...old, loading: false, error: apiErrorMessage(error) }))
      })
    return () => { active = false }
  }, [path, list, enabled, realtimeRevision, localRevision])

  return useMemo(() => ({ ...state, refresh }), [refresh, state])
}

export function useActionFeedback() {
  const [feedback, setFeedback] = useState(null)
  const [pending, setPending] = useState(false)
  const clearFeedback = useCallback(() => setFeedback(null), [])
  const runAction = useCallback(async (action, successMessage, fallbackError) => {
    setPending(true)
    setFeedback(null)
    try {
      const result = await action()
      setFeedback({ type: 'success', message: successMessage })
      return result
    } catch (error) {
      setFeedback({ type: 'error', message: apiErrorMessage(error, fallbackError) })
      return null
    } finally {
      setPending(false)
    }
  }, [])
  return { feedback, pending, runAction, clearFeedback }
}
