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
 * `toggle` updates optimistically and reverts if the request fails: a star is
 * a cheap, reversible action, and waiting a round trip to acknowledge a click
 * feels broken.
 */
export function useWatchlist() {
  const [symbols, setSymbols] = useState<Set<string>>(new Set())
  const [ready, setReady] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const groups = await apiClient.getWatchlist()
      setSymbols(new Set((groups.all ?? []).map((item) => item.symbol)))
    } catch (error) {
      // A failed read leaves the stars dark rather than guessing. Guessing
      // would show a filled star for something the server does not have.
      console.error('Failed to load watchlist', error)
    } finally {
      setReady(true)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const toggle = useCallback(async (symbol: string) => {
    const following = symbols.has(symbol)

    setSymbols((prev) => {
      const next = new Set(prev)
      if (following) next.delete(symbol)
      else next.add(symbol)
      return next
    })

    try {
      if (following) await apiClient.removeFromWatchlist(symbol)
      else await apiClient.addToWatchlist(symbol)
    } catch (error) {
      console.error('Failed to update watchlist', error)
      // Put it back. A star that stays lit after a failed save is a lie about
      // what the server stored.
      setSymbols((prev) => {
        const next = new Set(prev)
        if (following) next.add(symbol)
        else next.delete(symbol)
        return next
      })
    }
  }, [symbols])

  return { symbols, ready, toggle, refresh }
}
