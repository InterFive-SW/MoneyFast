import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import QuickTradeLauncher from './QuickTradeLauncher'
import { apiClient } from '../../api/client'
import type { Position, WatchlistItem } from '../../api/client'

function makePosition(overrides: Partial<Position> = {}): Position {
  return {
    symbol: 'THYAO', price: 295.5, quantity: 120, avgCost: 280, totalValue: 35_460,
    dailyReturn: 420, dailyReturnPercent: 1.2, totalReturn: 1_860, totalReturnPercent: 5.53,
    ...overrides,
  }
}

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('QuickTradeLauncher', () => {
  it('pozisyon yokken ve watchlist boşken "Al / Sat" butonu devre dışı kalır', async () => {
    vi.spyOn(apiClient, 'getWatchlist').mockResolvedValue({})
    render(<QuickTradeLauncher positions={[]} />)
    await waitFor(() => expect(apiClient.getWatchlist).toHaveBeenCalled())
    expect((screen.getByText('Al / Sat') as HTMLButtonElement).disabled).toBe(true)
  })

  it('pozisyonlardan seçenek üretir, ilkini otomatik seçer, watchlist\'teki mükerrer sembolü ayıklar', async () => {
    const watchlistResponse: Record<string, WatchlistItem[]> = {
      bist: [
        { symbol: 'THYAO', price: 295.5, change: 3.5, changePercent: 1.2 }, // pozisyonlarda zaten var, ayıklanmalı
        { symbol: 'GARAN', price: 128.9, change: -1.1, changePercent: -0.5 },
      ],
    }
    vi.spyOn(apiClient, 'getWatchlist').mockResolvedValue(watchlistResponse)
    render(<QuickTradeLauncher positions={[makePosition({ symbol: 'THYAO' })]} />)

    await waitFor(() => expect(screen.getByText('GARAN')).toBeInTheDocument())
    expect(screen.getAllByText('THYAO').length).toBe(1) // mükerrer eklenmedi
    expect((screen.getByText('Al / Sat') as HTMLButtonElement).disabled).toBe(false)
  })

  it('Al / Sat butonuna basınca işlem modalını açar, kapatınca kapanır', async () => {
    vi.spyOn(apiClient, 'getWatchlist').mockResolvedValue({})
    render(<QuickTradeLauncher positions={[makePosition({ symbol: 'THYAO' })]} />)

    await waitFor(() => expect((screen.getByText('Al / Sat') as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(screen.getByText('Al / Sat'))
    expect(screen.getByText('Varlık')).toBeInTheDocument()

    const closePath = document.querySelector('path[d="M18 6 6 18M6 6l12 12"]')!
    fireEvent.click(closePath.closest('button')!)
    expect(screen.queryByText('Varlık')).not.toBeInTheDocument()
  })

  it('sembol seçim kutusu değiştirilince seçili sembol güncellenir', async () => {
    const watchlistResponse: Record<string, WatchlistItem[]> = {
      bist: [{ symbol: 'GARAN', price: 128.9, change: -1.1, changePercent: -0.5 }],
    }
    vi.spyOn(apiClient, 'getWatchlist').mockResolvedValue(watchlistResponse)
    render(<QuickTradeLauncher positions={[makePosition({ symbol: 'THYAO' })]} />)

    await waitFor(() => expect(screen.getByText('GARAN')).toBeInTheDocument())
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'GARAN' } })
    fireEvent.click(screen.getByText('Al / Sat'))
    expect(screen.getAllByText('GARAN').length).toBeGreaterThan(1) // seçenek + modal içindeki sembol
  })

  it('watchlist isteği başarısız olursa hatayı loglar', async () => {
    vi.spyOn(apiClient, 'getWatchlist').mockRejectedValue(new Error('network'))
    render(<QuickTradeLauncher positions={[]} />)
    await waitFor(() => expect(console.error).toHaveBeenCalled())
  })
})
