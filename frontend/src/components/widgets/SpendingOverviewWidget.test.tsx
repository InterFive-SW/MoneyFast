import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import SpendingOverviewWidget from './SpendingOverviewWidget'
import type { SpendingOverviewData } from '../../data/mockData'

function makeData(overrides: Partial<SpendingOverviewData> = {}): SpendingOverviewData {
  return {
    month: 'Ağustos',
    totalExpense: 12_450,
    changePercent: 8.2,
    categories: [
      { label: 'Market', icon: '🛒', amount: 4_200, color: '#10b981' },
      { label: 'Ulaşım', icon: '🚌', amount: 1_100, color: '#3b82f6' },
    ],
    ...overrides,
  }
}

describe('SpendingOverviewWidget', () => {
  it('artan harcamada kırmızı, artı işaretli yüzde gösterir', () => {
    render(<SpendingOverviewWidget data={makeData()} />)
    expect(screen.getByText('Aylık Harcama (Ağustos)')).toBeInTheDocument()
    expect(screen.getByText('+8.2%')).toBeInTheDocument()
    expect(screen.getByText('Market')).toBeInTheDocument()
  })

  it('azalan harcamada yeşil, işaretsiz yüzde gösterir', () => {
    render(<SpendingOverviewWidget data={makeData({ changePercent: -5.4 })} />)
    expect(screen.getByText('-5.4%')).toBeInTheDocument()
  })
})
