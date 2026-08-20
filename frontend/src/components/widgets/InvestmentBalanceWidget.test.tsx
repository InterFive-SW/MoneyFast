import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import InvestmentBalanceWidget from './InvestmentBalanceWidget'
import type { InvestmentBalance } from '../../data/mockData'

const navigateMock = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigateMock }
})

const data: InvestmentBalance = {
  totalTRY: 125_750.4,
  totalUSD: 3_262.85,
  breakdown: { cashTRY: 15_420, stocksBIST: 85_120.4, stocksUS: 25_210 },
}

beforeEach(() => {
  navigateMock.mockClear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('InvestmentBalanceWidget', () => {
  it('başlığa tıklanınca /portfolio\'ya yönlendirir', () => {
    render(<InvestmentBalanceWidget data={data} />)
    fireEvent.click(screen.getByText('Yatırım Hesabım'))
    expect(navigateMock).toHaveBeenCalledWith('/portfolio')
  })

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
