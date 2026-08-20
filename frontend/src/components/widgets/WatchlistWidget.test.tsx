import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import WatchlistWidget from './WatchlistWidget'
import { apiClient } from '../../api/client'
import type { WatchlistItem } from '../../api/client'

const response: Record<string, WatchlistItem[]> = {
  bist: [{ symbol: 'THYAO', price: 295.5, change: 3.5, changePercent: 1.2 }],
  us: [{ symbol: 'AAPL', price: 215.3, change: -1.1, changePercent: -0.5 }],
}

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('WatchlistWidget', () => {
  it('yüklenirken dönen animasyonu gösterir', () => {
    vi.spyOn(apiClient, 'getWatchlist').mockReturnValue(new Promise(() => {}))
    render(<WatchlistWidget />)
    expect(document.querySelector('.animate-spin')).not.toBeNull()
  })

  it('varsayılan BIST sekmesinde pozitif değişimi yeşille gösterir', async () => {
    vi.spyOn(apiClient, 'getWatchlist').mockResolvedValue(response)
    render(<WatchlistWidget />)
    await waitFor(() => expect(screen.getByText('THYAO')).toBeInTheDocument())
    expect(screen.getByText('+1.2%')).toBeInTheDocument()
  })

  it('ABD sekmesine geçince negatif değişimi işaretsiz gösterir', async () => {
    vi.spyOn(apiClient, 'getWatchlist').mockResolvedValue(response)
    render(<WatchlistWidget />)
    await waitFor(() => expect(screen.getByText('THYAO')).toBeInTheDocument())
    fireEvent.click(screen.getByText('ABD'))
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('-0.5%')).toBeInTheDocument()
  })

  it('veride bulunmayan Kripto sekmesine geçince boş liste gösterir, BIST\'e dönünce eski hale gelir', async () => {
    vi.spyOn(apiClient, 'getWatchlist').mockResolvedValue(response)
    render(<WatchlistWidget />)
    await waitFor(() => expect(screen.getByText('THYAO')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Kripto'))
    expect(screen.queryByText('THYAO')).not.toBeInTheDocument()
    expect(screen.queryByText('AAPL')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('BIST'))
    expect(screen.getByText('THYAO')).toBeInTheDocument()
  })

  it('istek başarısız olursa hatayı loglar', async () => {
    vi.spyOn(apiClient, 'getWatchlist').mockRejectedValue(new Error('network'))
    render(<WatchlistWidget />)
    await waitFor(() => expect(console.error).toHaveBeenCalled())
  })
})
