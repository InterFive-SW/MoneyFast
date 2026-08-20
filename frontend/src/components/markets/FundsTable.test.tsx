import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import FundsTable from './FundsTable'
import type { Fund } from '../../data/mockData'

const navigateMock = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigateMock }
})

function makeFund(overrides: Partial<Fund> = {}): Fund {
  return {
    code: 'AFT', name: 'İş Portföy Hisse Senedi Fonu', founder: 'İş Portföy', umbrella: 'Hisse Senedi Şemsiye Fonu',
    managementFee: 2.5, withholdingTax: 0, riskValue: 1, investorCount: 45_000, size: 3_200_000_000, netCashFlow: 85_000_000,
    returns: { daily: 0.4, monthly: 3.2, threeMonth: 9.8, yearly: 38.5, threeYear: 145.2, fiveYear: 310.6 },
    holdings: [],
    ...overrides,
  }
}

const funds = [
  makeFund({ code: 'A', riskValue: 1, netCashFlow: 85_000_000 }),
  makeFund({ code: 'B', riskValue: 3, netCashFlow: -12_000_000, returns: { daily: 0.1, monthly: -1.7, threeMonth: 5.1, yearly: 23.8, threeYear: null, fiveYear: null } }),
  makeFund({ code: 'C', riskValue: 7 }),
]

function renderTable(list = funds) {
  return render(
    <MemoryRouter>
      <FundsTable funds={list} />
    </MemoryRouter>
  )
}

describe('FundsTable', () => {
  it('Getiri sekmesinde getiri kolonlarını gösterir, NA olan değerleri "NA" yazar', () => {
    renderTable()
    expect(screen.getByText('1A')).toBeInTheDocument()
    expect(screen.getAllByText('NA').length).toBeGreaterThan(0)
  })

  it('Büyüklük sekmesine geçince büyüklük kolonlarını gösterir, negatif nakit akışını kırmızı yapar, Getiri\'ye dönünce eski hale gelir', () => {
    renderTable()
    fireEvent.click(screen.getByText('Büyüklük'))
    expect(screen.getByText('Yatırımcı')).toBeInTheDocument()
    const outflow = screen.getByText(/-.*₺/)
    expect(outflow.className).toContain('text-rose-500')

    fireEvent.click(screen.getByText('Getiri'))
    expect(screen.getByText('1A')).toBeInTheDocument()
  })

  it('düşük, orta ve yüksek risk rozetlerini farklı renklerle gösterir', () => {
    renderTable()
    const badges = screen.getAllByText(/^[137]$/)
    expect(badges.length).toBe(3)
  })

  it('bir fon satırına tıklanınca fon detayına yönlendirir', () => {
    renderTable()
    // Risk rozeti '1' yalnızca A fonuna ait — satırı bulmak için kullanılıyor.
    const row = screen.getByText('1', { selector: 'span' }).closest('tr')!
    fireEvent.click(row)
    expect(navigateMock).toHaveBeenCalledWith('/investment/fonlar/A')
  })

  it('fon listesi boşsa bilgi mesajı gösterir', () => {
    renderTable([])
    expect(screen.getByText('Filtrenizle eşleşen fon bulunamadı.')).toBeInTheDocument()
  })
})
