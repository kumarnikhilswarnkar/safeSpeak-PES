import { useCallback, useEffect, useState } from 'react'

/** Runs an async loader on mount (and on reload()), tracking data, error and loading. */
export default function useLoader(load) {
  const [state, setState] = useState({ data: null, error: null, loading: true })

  const reload = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      setState({ data: await load(), error: null, loading: false })
    } catch (error) {
      setState({ data: null, error, loading: false })
    }
  }, [load])

  useEffect(() => {
    reload()
  }, [reload])

  return { ...state, reload, setData: (data) => setState((s) => ({ ...s, data })) }
}
