import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MarketComparisonChart, { formatMarketComparisonTooltip } from './MarketComparisonChart'
import type { MarketInstrument } from '../../data/mockData'

function makeInstrument(overrides: Partial<MarketInstrument> = {}): MarketInstrument {
  return {
    symbol: 'THYAO', name: 'Türk Hava Yolları', market: 'BIST', price: 295.5, unit: '₺',
    changePercent: 1.2, volume: 1000, marketCap: 1000, sector: 'Ulaştırma', week52Low: 200, week52High: 300,
    ...overrides,
  }
}

const instruments = [
  makeInstrument({ symbol: 'THYAO' }),
  makeInstrument({ symbol: 'GARAN' }),
  makeInstrument({ symbol: 'ASELS' }),
  makeInstrument({ symbol: 'SISE' }),
  makeInstrument({ symbol: 'TUPRS' }),
]

// Seçim butonlarındaki sembol metni, grafik render edildiğinde recharts'ın
// legend'ındaki metinle çakışabiliyor — role: 'button' ile ayırt ediliyor.
function btn(name: string) {
  return screen.getByRole('button', { name })
}

describe('MarketComparisonChart', () => {
  it('varsayılan olarak ilk 2 enstrüman seçili ve grafik render edilir', () => {
    render(<MarketComparisonChart instruments={instruments} />)
    expect(btn('THYAO').className).toContain('bg-slate-800')
  })

  it('seçili bir enstrümana tekrar tıklanınca seçim kaldırılır', () => {
    render(<MarketComparisonChart instruments={instruments} />)
    fireEvent.click(btn('THYAO'))
    fireEvent.click(btn('GARAN'))
    expect(screen.getByText(/Karşılaştırmak için en fazla 4 enstrüman seçin/)).toBeInTheDocument()
  })

  it('4 seçim limitine ulaşınca kalan butonlar disabled olur', () => {
    render(<MarketComparisonChart instruments={instruments} />)
    fireEvent.click(btn('ASELS'))
    fireEvent.click(btn('SISE'))
    expect((btn('TUPRS') as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('formatMarketComparisonTooltip', () => {
  it('pozitif değeri + işaretiyle biçimlendirir', () => {
    expect(formatMarketComparisonTooltip(5, 'THYAO')).toEqual(['+5%', 'THYAO'])
  })

  it('negatif değeri işaretsiz biçimlendirir', () => {
    expect(formatMarketComparisonTooltip(-3, 'GARAN')).toEqual(['-3%', 'GARAN'])
  })
})
