import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import FundFilterPanel, { applyFundFilters, EMPTY_FUND_FILTERS, type FundFilters } from './FundFilterPanel'
import type { Fund } from '../../data/mockData'

function makeFund(overrides: Partial<Fund> = {}): Fund {
  return {
    code: 'AFT', name: 'İş Portföy Hisse Senedi Fonu', founder: 'İş Portföy', umbrella: 'Hisse Senedi Şemsiye Fonu',
    managementFee: 2.5, withholdingTax: 0, riskValue: 6, investorCount: 45_000, size: 3_200_000_000, netCashFlow: 85_000_000,
    returns: { daily: 0.4, monthly: 3.2, threeMonth: 9.8, yearly: 38.5, threeYear: 145.2, fiveYear: 310.6 },
    holdings: [],
    ...overrides,
  }
}

describe('applyFundFilters', () => {
  const funds = [
    makeFund({ code: 'A', managementFee: 1, riskValue: 2, founder: 'X Portföy', umbrella: 'Hisse Senedi Şemsiye Fonu' }),
    makeFund({ code: 'B', managementFee: 3, riskValue: 6, founder: 'Y Portföy', umbrella: 'Borçlanma Araçları Şemsiye Fonu' }),
  ]

  it('filtresiz tüm fonları döner', () => {
    expect(applyFundFilters(funds, EMPTY_FUND_FILTERS)).toHaveLength(2)
  })

  it('feeMax filtresi yüksek ücretli fonu eler', () => {
    const result = applyFundFilters(funds, { ...EMPTY_FUND_FILTERS, feeMax: '2' })
    expect(result.map((f) => f.code)).toEqual(['A'])
  })

  it('riskValue filtresi eşleşmeyen riski eler', () => {
    const result = applyFundFilters(funds, { ...EMPTY_FUND_FILTERS, riskValue: '6' })
    expect(result.map((f) => f.code)).toEqual(['B'])
  })

  it('founder filtresi eşleşmeyeni eler', () => {
    const result = applyFundFilters(funds, { ...EMPTY_FUND_FILTERS, founder: 'X Portföy' })
    expect(result.map((f) => f.code)).toEqual(['A'])
  })

  it('umbrella filtresi eşleşmeyeni eler', () => {
    const result = applyFundFilters(funds, { ...EMPTY_FUND_FILTERS, umbrella: 'Borçlanma Araçları Şemsiye Fonu' })
    expect(result.map((f) => f.code)).toEqual(['B'])
  })
})

describe('FundFilterPanel', () => {
  const filters: FundFilters = { ...EMPTY_FUND_FILTERS, feeMax: '2' }

  it('Temizle butonuna basınca boş filtrelerle onChange çağırır', () => {
    const onChange = vi.fn()
    render(<FundFilterPanel filters={filters} onChange={onChange} founders={['İş Portföy']} umbrellas={['Hisse Senedi Şemsiye Fonu']} />)
    fireEvent.click(screen.getByText('Temizle'))
    expect(onChange).toHaveBeenCalledWith(EMPTY_FUND_FILTERS)
  })

  it('yönetim ücreti girildiğinde onChange doğru alanla çağrılır', () => {
    const onChange = vi.fn()
    render(<FundFilterPanel filters={EMPTY_FUND_FILTERS} onChange={onChange} founders={['İş Portföy']} umbrellas={['Hisse Senedi Şemsiye Fonu']} />)
    fireEvent.change(screen.getByPlaceholderText('Örn. 2.0'), { target: { value: '1.5' } })
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_FUND_FILTERS, feeMax: '1.5' })
  })

  it('kurucu ve şemsiye seçenekleri listelenir', () => {
    render(<FundFilterPanel filters={EMPTY_FUND_FILTERS} onChange={vi.fn()} founders={['İş Portföy']} umbrellas={['Hisse Senedi Şemsiye Fonu']} />)
    expect(screen.getByText('İş Portföy')).toBeInTheDocument()
    expect(screen.getByText('Hisse Senedi Şemsiye Fonu')).toBeInTheDocument()
  })

  it('risk değeri, kurucu ve şemsiye seçim kutuları değiştirilince onChange doğru alanla çağrılır', () => {
    const onChange = vi.fn()
    render(<FundFilterPanel filters={EMPTY_FUND_FILTERS} onChange={onChange} founders={['İş Portföy']} umbrellas={['Hisse Senedi Şemsiye Fonu']} />)

    // Etiketler <select>'lere htmlFor/id ile bağlı değil, sırayla erişiyoruz:
    // Risk Değeri, Kurucu/PYŞ, Şemsiye Türü.
    const [riskSelect, founderSelect, umbrellaSelect] = screen.getAllByRole('combobox')

    fireEvent.change(riskSelect, { target: { value: '3' } })
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_FUND_FILTERS, riskValue: '3' })

    fireEvent.change(founderSelect, { target: { value: 'İş Portföy' } })
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_FUND_FILTERS, founder: 'İş Portföy' })

    fireEvent.change(umbrellaSelect, { target: { value: 'Hisse Senedi Şemsiye Fonu' } })
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_FUND_FILTERS, umbrella: 'Hisse Senedi Şemsiye Fonu' })
  })
})
