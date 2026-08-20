import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DividendCalendarWidget from './DividendCalendarWidget'
import { apiClient } from '../../api/client'
import type { DividendItem } from '../../api/client'

const dividends: DividendItem[] = [
  { symbol: 'TUPRS', exDate: '2026-09-10', paymentDate: '2026-09-17', amount: 8.4, yieldPercent: 4.8 },
]

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('DividendCalendarWidget', () => {
  it('yüklenirken dönen animasyonu gösterir', () => {
    vi.spyOn(apiClient, 'getDividends').mockReturnValue(new Promise(() => {}))
    render(<DividendCalendarWidget />)
    expect(document.querySelector('.animate-spin')).not.toBeNull()
  })

  it('veri geldiğinde temettü listesini render eder', async () => {
    vi.spyOn(apiClient, 'getDividends').mockResolvedValue(dividends)
    render(<DividendCalendarWidget />)
    await waitFor(() => expect(screen.getByText('TUPRS')).toBeInTheDocument())
    expect(screen.getByText(/Verim: 4\.8%/)).toBeInTheDocument()
  })

  it('istek başarısız olursa hatayı loglar ve boş liste gösterir', async () => {
    vi.spyOn(apiClient, 'getDividends').mockRejectedValue(new Error('network'))
    render(<DividendCalendarWidget />)
    await waitFor(() => expect(console.error).toHaveBeenCalled())
  })
})
