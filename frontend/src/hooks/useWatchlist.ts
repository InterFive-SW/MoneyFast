import { useCallback, useEffect, useState } from 'react'
import { apiClient } from '../api/client'

/**
 * The user's followed instruments, as a set of symbols.
 *
 * The star on the Piyasalar table used to be local component state: it lit up,
 * did nothing, and was gone the moment you navigated away. This backs it with
 * `investment.watchlist_items`, which is also what the İzleme Listesi widget
 * on the dashboard and the portfolio page reads — so starring a row in one
 * place shows up in the other two.
 *
 * The set lives in ONE module-level store rather than per component, the same
 * shape `useMarketStream` uses for its single `EventSource`. Each component
 * used to hold its own copy, so starring a symbol on Piyasalar left the
 * ticker band on the main page showing the old list until a reload — two
 * views of one list, disagreeing.
 *
 * `toggle` updates optimistically and reverts if the request fails: a star is
 * a cheap, reversible action, and waiting a round trip to acknowledge a click
 * feels broken.
 */

type Listener = (symbols: Set<string>) => void

let symbols: Set<string> = new Set()
let ready = false
let listeners: Listener[] = []
let inFlight: Promise<void> | null = null

function publish(next: Set<string>) {
  symbols = next
  listeners.forEach((listener) => listener(next))
}

/**
 * Reads the list into the shared store.
 *
 * Concurrent callers share one request: several components mount together on
 * a page and each would otherwise fire its own identical fetch.
 */
async function load(force = false): Promise<void> {
  if (inFlight) return inFlight
  if (ready && !force) return
  inFlight = (async () => {
    try {
      const groups = await apiClient.getWatchlist()
      publish(new Set((groups.all ?? []).map((item) => item.symbol)))
    } catch (error) {
      // A failed read leaves the stars dark rather than guessing. Guessing
      // would show a filled star for something the server does not have.
      console.error('Failed to load watchlist', error)
    } finally {
      ready = true
      inFlight = null
    }
  })()
  return inFlight
}

/** Test seam: drops the shared state so one test cannot leak into the next. */
export function __resetWatchlistStore() {
  symbols = new Set()
  ready = false
  listeners = []
  inFlight = null
}

export function useWatchlist() {
  const [current, setCurrent] = useState<Set<string>>(symbols)
  const [isReady, setIsReady] = useState(ready)

  useEffect(() => {
    const listener: Listener = (next) => {
      setCurrent(next)
      setIsReady(true)
    }
    listeners.push(listener)
    void load().then(() => setIsReady(true))
    return () => {
      listeners = listeners.filter((candidate) => candidate !== listener)
    }
  }, [])

  const refresh = useCallback(() => load(true), [])

  const toggle = useCallback(async (symbol: string) => {
    const following = symbols.has(symbol)

    const next = new Set(symbols)
    if (following) next.delete(symbol)
    else next.add(symbol)
    publish(next)

    try {
      if (following) await apiClient.removeFromWatchlist(symbol)
      else await apiClient.addToWatchlist(symbol)
    } catch (error) {
      console.error('Failed to update watchlist', error)
      // Put it back. A star that stays lit after a failed save is a lie about
      // what the server stored.
      const reverted = new Set(symbols)
      if (following) reverted.add(symbol)
      else reverted.delete(symbol)
      publish(reverted)
    }
  }, [])

  return { symbols: current, ready: isReady, toggle, refresh }
}
