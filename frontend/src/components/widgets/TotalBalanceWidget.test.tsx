import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import TotalBalanceWidget from './TotalBalanceWidget'
import type { BalanceData } from '../../data/mockData'

function makeData(overrides: Partial<BalanceData> = {}): BalanceData {
  return {
    period: 'Bugün',
    total: 125_750.4,
    changePercent: 1.2,
    changeAmount: 1_490.5,
    sparklinePoints: [0.2, 0.4, 0.3, 0.6, 0.5, 0.8],
    ...overrides,
  }
}

describe('TotalBalanceWidget', () => {
  it('pozitif değişimde toplam bakiyeyi ve yeşil rozeti render eder', () => {
    render(<TotalBalanceWidget data={makeData()} />)
    expect(screen.getByText('Bugün Toplam Varlık')).toBeInTheDocument()
    expect(screen.getByText('▲ 1.20%')).toBeInTheDocument()
    expect(screen.getByText(/\+.*1\.490,50/)).toBeInTheDocument()
  })

  it('negatif değişimde kırmızı rozet ve ters işaret gösterir', () => {
    render(<TotalBalanceWidget data={makeData({ changePercent: -2.5, changeAmount: -800 })} />)
    expect(screen.getByText('▼ 2.50%')).toBeInTheDocument()
  })
})
