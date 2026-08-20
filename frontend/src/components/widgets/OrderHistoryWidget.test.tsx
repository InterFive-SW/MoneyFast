import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import OrderHistoryWidget from './OrderHistoryWidget'
import { apiClient } from '../../api/client'
import type { Order } from '../../api/client'

const orders: Order[] = [
  { id: 'ORD-001', symbol: 'TUPRS', status: 'Bekliyor', type: 'Alış', quantity: 50, price: 172.5, total: 8_625, date: '2026-08-14T10:15:00' },
  { id: 'ORD-002', symbol: 'THYAO', status: 'Gerçekleşti', type: 'Satış', quantity: 20, price: 298, total: 5_960, date: '2026-08-13T15:45:00' },
  { id: 'ORD-003', symbol: 'KCHOL', status: 'İptal', type: 'Alış', quantity: 100, price: 210, total: 21_000, date: '2026-08-11T09:20:00' },
]

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('OrderHistoryWidget', () => {
  it('Bekliyor, Gerçekleşti ve İptal statülerini ve Alış/Satış yönlerini render eder', async () => {
    vi.spyOn(apiClient, 'getOrders').mockResolvedValue(orders)
    render(<OrderHistoryWidget />)
    await waitFor(() => expect(screen.getByText('TUPRS')).toBeInTheDocument())
    expect(screen.getByText('Bekliyor')).toBeInTheDocument()
    expect(screen.getByText('Gerçekleşti')).toBeInTheDocument()
    expect(screen.getByText('İptal')).toBeInTheDocument()
    expect(screen.getAllByText('Alış').length).toBeGreaterThan(0)
    expect(screen.getByText('Satış')).toBeInTheDocument()
  })

  it('istek başarısız olursa hatayı loglar', async () => {
    vi.spyOn(apiClient, 'getOrders').mockRejectedValue(new Error('network'))
    render(<OrderHistoryWidget />)
    await waitFor(() => expect(console.error).toHaveBeenCalled())
  })
})
