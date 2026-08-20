import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TopMoversWidget from './TopMoversWidget'
import { apiClient } from '../../api/client'
import type { TopMoverItem } from '../../api/client'

const navigateMock = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigateMock }
})

const response: Record<string, TopMoverItem[]> = {
  gainers: [{ symbol: 'SASA', price: 4.86, changePercent: 3.4 }],
  losers: [{ symbol: 'EREGL', price: 42.8, changePercent: -0.92 }],
}

beforeEach(() => {
  navigateMock.mockClear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('TopMoversWidget', () => {
  it('yüklenirken dönen animasyonu gösterir', () => {
    vi.spyOn(apiClient, 'getTopMovers').mockReturnValue(new Promise(() => {}))
    render(<TopMoversWidget />)
    expect(document.querySelector('.animate-spin')).not.toBeNull()
  })

  it('varsayılan Yükselenler sekmesinde pozitif değişimi gösterir', async () => {
    vi.spyOn(apiClient, 'getTopMovers').mockResolvedValue(response)
    render(<TopMoversWidget />)
    await waitFor(() => expect(screen.getByText('SASA')).toBeInTheDocument())
    expect(screen.getByText('+3.4%')).toBeInTheDocument()
  })

  it('Düşenler sekmesine geçince negatif değişimi gösterir, Yükselenler\'e dönünce eski hale gelir', async () => {
    vi.spyOn(apiClient, 'getTopMovers').mockResolvedValue(response)
    render(<TopMoversWidget />)
    await waitFor(() => expect(screen.getByText('SASA')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Düşenler'))
    expect(screen.getByText('EREGL')).toBeInTheDocument()
    expect(screen.getByText('-0.92%')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Yükselenler'))
    expect(screen.getByText('SASA')).toBeInTheDocument()
  })

  it('başlığa tıklanınca /investment/hisseler\'e yönlendirir', async () => {
    vi.spyOn(apiClient, 'getTopMovers').mockResolvedValue(response)
    render(<TopMoversWidget />)
    await waitFor(() => expect(screen.getByText('SASA')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Hareketliler'))
    expect(navigateMock).toHaveBeenCalledWith('/investment/hisseler')
  })

  it('istek başarısız olursa hatayı loglar', async () => {
    vi.spyOn(apiClient, 'getTopMovers').mockRejectedValue(new Error('network'))
    render(<TopMoversWidget />)
    await waitFor(() => expect(console.error).toHaveBeenCalled())
  })
})
