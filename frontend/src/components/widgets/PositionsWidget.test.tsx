import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PositionsWidget from './PositionsWidget'
import { apiClient } from '../../api/client'
import type { Position } from '../../api/client'

const navigateMock = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigateMock }
})

const positions: Position[] = [
  { symbol: 'THYAO', price: 295.5, quantity: 120, avgCost: 280, totalValue: 35_460, dailyReturn: 420, dailyReturnPercent: 1.2, totalReturn: 1_860, totalReturnPercent: 5.53 },
  { symbol: 'SISE', price: 54.2, quantity: 500, avgCost: 56.1, totalValue: 27_100, dailyReturn: -250, dailyReturnPercent: -0.91, totalReturn: -950, totalReturnPercent: -3.38 },
]

beforeEach(() => {
  navigateMock.mockClear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('PositionsWidget', () => {
  it('yüklenirken dönen animasyonu gösterir', () => {
    vi.spyOn(apiClient, 'getPositions').mockReturnValue(new Promise(() => {}))
    render(<PositionsWidget />)
    expect(document.querySelector('.animate-spin')).not.toBeNull()
  })

  it('pozitif ve negatif getirili pozisyonları doğru işaret ve renkle gösterir', async () => {
    vi.spyOn(apiClient, 'getPositions').mockResolvedValue(positions)
    render(<PositionsWidget />)
    await waitFor(() => expect(screen.getByText('THYAO')).toBeInTheDocument())
    expect(screen.getByText('SISE')).toBeInTheDocument()
    expect(screen.getByText(/\+420,00 \(\+1\.2%\)/)).toBeInTheDocument()
    expect(screen.getByText(/-250,00 \(-0\.91%\)/)).toBeInTheDocument()

    fireEvent.click(screen.getByText('Pozisyonlar'))
    expect(navigateMock).toHaveBeenCalledWith('/portfolio')
  })

  it('istek başarısız olursa hatayı loglar', async () => {
    vi.spyOn(apiClient, 'getPositions').mockRejectedValue(new Error('network'))
    render(<PositionsWidget />)
    await waitFor(() => expect(console.error).toHaveBeenCalled())
  })
})
