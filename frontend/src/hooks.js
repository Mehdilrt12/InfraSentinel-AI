import { useEffect, useState } from 'react'
import { api, listData } from './api'
import { useRealtime } from './realtime'

export function useApi(path, { list = false } = {}) {
  const { revision } = useRealtime()
  const [state, setState] = useState({ data: list ? [] : null, loading: true, error: null, partial: false })
  useEffect(() => {
    let active = true
    setState((old) => ({ ...old, loading: old.data == null || (list && !old.data.length), error: null }))
    api.get(path).then(({ data }) => active && setState({ data: list ? listData(data) : data, loading: false, error: null, partial: Boolean(data?.partial) })).catch((error) => active && setState((old) => ({ ...old, loading: false, error: error.response?.data?.detail || (navigator.onLine ? 'Le serveur API est injoignable.' : 'Vous êtes hors ligne.') })))
    return () => { active = false }
  }, [path, list, revision])
  return state
}

