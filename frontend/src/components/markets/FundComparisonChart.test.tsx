import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import FundComparisonChart, { formatFundComparisonTooltip } from './FundComparisonChart'
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

const funds = [
  makeFund({ code: 'AFT', name: 'İş Portföy Hisse Senedi Fonu' }),
  makeFund({ code: 'APT', name: 'Ak Portföy BIST Endeks Fonu' }),
  makeFund({ code: 'GPB', name: 'Garanti Portföy Borçlanma Fonu' }),
  makeFund({ code: 'YKT', name: 'Yapı Kredi Portföy Değişken Fon' }),
  makeFund({ code: 'QPP', name: 'QNB Portföy Para Piyasası Fonu' }),
]

// Seçim butonlarındaki fon kodu, grafik render edildiğinde recharts'ın
// legend'ındaki metinle çakışabiliyor — role: 'button' ile ayırt ediliyor.
function btn(name: string) {
  return screen.getByRole('button', { name })
}

describe('FundComparisonChart', () => {
  it('varsayılan olarak ilk 2 fon seçili ve grafik render edilir', () => {
    render(<FundComparisonChart funds={funds} />)
    expect(btn('AFT').className).toContain('bg-slate-800 text-white')
  })

  it('seçili bir fona tekrar tıklanınca seçim kaldırılır, tümü kaldırılınca uyarı gösterir', () => {
    render(<FundComparisonChart funds={funds} />)
    fireEvent.click(btn('AFT'))
    fireEvent.click(btn('APT'))
    expect(screen.getByText(/Karşılaştırmak için en fazla 4 fon seçin/)).toBeInTheDocument()
  })

  it('4 seçim limitine ulaşınca kalan butonlar disabled olur', () => {
    render(<FundComparisonChart funds={funds} />)
    fireEvent.click(btn('GPB'))
    fireEvent.click(btn('YKT'))
    expect((btn('QPP') as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('formatFundComparisonTooltip', () => {
  const codeToName = new Map([['AFT', 'İş Portföy Hisse Senedi Fonu']])

  it('bilinen kod için fon adını, pozitif işaretli değeri döner', () => {
    expect(formatFundComparisonTooltip(5, 'AFT', codeToName)).toEqual(['+5%', 'İş Portföy Hisse Senedi Fonu'])
  })

  it('bilinmeyen kod için kodu olduğu gibi döner, negatif değeri işaretsiz döner', () => {
    expect(formatFundComparisonTooltip(-3, 'XYZ', codeToName)).toEqual(['-3%', 'XYZ'])
  })
})
