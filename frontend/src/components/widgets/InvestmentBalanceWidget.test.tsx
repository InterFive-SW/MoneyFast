import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import InvestmentBalanceWidget from './InvestmentBalanceWidget'
import type { InvestmentBalance } from '../../data/mockData'

const data: InvestmentBalance = {
  totalTRY: 125_750.4,
  totalUSD: 3_262.85,
  breakdown: { cashTRY: 15_420, stocksBIST: 85_120.4, stocksUS: 25_210 },
}

describe('InvestmentBalanceWidget', () => {
  it('varsayılan olarak TL bakiyeyi ve ₺ sembolünü gösterir', () => {
    render(<InvestmentBalanceWidget data={data} />)
    expect(screen.getByText(/₺.*125\.750,40/)).toBeInTheDocument()
  })

  it('USD butonuna tıklanınca dolar bakiyeye ve $ sembolüne geçer, TL\'ye dönünce eski hale gelir', () => {
    render(<InvestmentBalanceWidget data={data} />)
    fireEvent.click(screen.getByText('USD'))
    expect(screen.getByText(/\$.*3,262\.85/)).toBeInTheDocument()

    fireEvent.click(screen.getByText('TL'))
    expect(screen.getByText(/₺.*125\.750,40/)).toBeInTheDocument()
  })
})
