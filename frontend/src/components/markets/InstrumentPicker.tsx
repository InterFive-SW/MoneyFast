import { useEffect, useRef, useState } from 'react'

import { apiClient } from '../../api/client'
import type { InstrumentSuggestion } from '../../api/client'

interface InstrumentPickerProps {
  onPick: (symbol: string) => void
  placeholder?: string
  disabled?: boolean
}

/** Kullanıcı yazmayı bırakana kadar beklenen süre. */
const DEBOUNCE_MS = 220

/**
 * Yazdıkça enstrüman arayan seçici.
 *
 * Arama SUNUCUDA (`GET /api/market/search`): Türkçe katlama orada tek bir
 * yerde duruyor (`market_service._fold`), dolayısıyla `sise` yazan `ŞİŞE`yi
 * buluyor ve kural iki ayrı yerde ayrışamıyor.
 */
export default function InstrumentPicker({
  onPick,
  placeholder = 'Sembol ya da şirket adı ara',
  disabled = false,
}: InstrumentPickerProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<InstrumentSuggestion[]>([])
  const [open, setOpen] = useState(false)
  const [highlighted, setHighlighted] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const term = query.trim()
    if (!term) {
      setResults([])
      return
    }
    let cancelled = false
    const timer = setTimeout(() => {
      apiClient
        .searchInstruments(term, 8)
        .then((rows) => {
          if (!cancelled) {
            setResults(rows)
            setHighlighted(0)
          }
        })
        // Arama başarısızsa liste boş kalır; kullanıcı yazmaya devam edebilir.
        .catch(() => undefined)
    }, DEBOUNCE_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query])

  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  function choose(symbol: string) {
    onPick(symbol)
    setQuery('')
    setResults([])
    setOpen(false)
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || results.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlighted((index) => (index + 1) % results.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlighted((index) => (index - 1 + results.length) % results.length)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      choose(results[highlighted].symbol)
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <input
        type="text"
        value={query}
        disabled={disabled}
        onChange={(event) => {
          setQuery(event.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        aria-label="Enstrüman ara"
        aria-autocomplete="list"
        aria-expanded={open}
        role="combobox"
        className="w-full rounded-xl border border-white/10 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 outline-none transition focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400 disabled:opacity-50"
      />

      {open && results.length > 0 && (
        <ul
          role="listbox"
          className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-xl border border-white/10 bg-slate-900 py-1 shadow-2xl"
        >
          {results.map((row, index) => (
            <li key={row.symbol} role="option" aria-selected={index === highlighted}>
              <button
                onMouseEnter={() => setHighlighted(index)}
                onClick={() => choose(row.symbol)}
                className={`flex w-full items-baseline gap-2 px-3 py-2 text-left text-sm transition ${
                  index === highlighted ? 'bg-white/10 text-white' : 'text-slate-300'
                }`}
              >
                <span className="font-semibold">{row.symbol}</span>
                {row.name && row.name !== row.symbol && (
                  <span className="truncate text-xs text-slate-500">{row.name}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
