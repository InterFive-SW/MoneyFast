import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import StockDetail, { fmt } from './StockDetail'

function renderPage(symbol: string) {
  return render(
    <MemoryRouter initialEntries={[`/investment/hisseler/${symbol}`]}>
      <Routes>
        <Route path="/investment/hisseler/:symbol" element={<StockDetail />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('StockDetail', () => {
  it('shows not-found message and back link for an unknown symbol', () => {
    renderPage('ZZZ')
    expect(screen.getByText(/"ZZZ" için bir enstrüman bulunamadı/)).toBeInTheDocument()
    expect(screen.getByText('← Hisseler listesine dön')).toBeInTheDocument()
  })

  it('THYAO: summary shows index weight and earnings surprise stats (both defined)', () => {
    renderPage('THYAO')
    expect(screen.getByText('BIST 100 Ağırlığı')).toBeInTheDocument()
    expect(screen.getByText(/Son Bilanço/)).toBeInTheDocument()
  })

  it('AAPL: summary hides index weight and earnings stats (both undefined for this instrument)', () => {
    renderPage('AAPL')
    expect(screen.queryByText('BIST 100 Ağırlığı')).not.toBeInTheDocument()
    expect(screen.queryByText(/Son Bilanço/)).not.toBeInTheDocument()
  })

  it('THYAO: financials tab is populated with the earnings box, total assets, and positive (green) revenue growth', () => {
    renderPage('THYAO')
    fireEvent.click(screen.getByText('Finansallar'))
    expect(screen.getByText(/bilançosu/)).toBeInTheDocument() // earnings box only rendered when a report exists
    expect(screen.getByText('Toplam Varlıklar')).toBeInTheDocument()
    const growth = screen.getByText('+22.4%')
    expect(growth.className).toContain('text-emerald-500')
  })

  it('AAPL: financials tab is populated but without an earnings box, and shows "—" for missing balance sheet fields', () => {
    renderPage('AAPL')
    fireEvent.click(screen.getByText('Finansallar'))
    expect(screen.getByText('Tahmini Yıllık Gelir')).toBeInTheDocument()
    expect(screen.queryByText(/bilançosu/)).not.toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('EREGL: financials tab shows negative (red) revenue growth', () => {
    renderPage('EREGL')
    fireEvent.click(screen.getByText('Finansallar'))
    const growth = screen.getByText('-4.2%')
    expect(growth.className).toContain('text-rose-500')
  })

  it('BTC: financials and ratio-analysis tabs show fallback messages (no PE ratio available)', () => {
    renderPage('BTC')
    fireEvent.click(screen.getByText('Finansallar'))
    expect(screen.getByText('Bu enstrüman için finansal tablo verisi bulunmuyor.')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Oran Analizi'))
    expect(screen.getByText('Bu enstrüman için oran analizi verisi bulunmuyor.')).toBeInTheDocument()
  })

  it('THYAO: ratio-analysis tab is populated', () => {
    renderPage('THYAO')
    fireEvent.click(screen.getByText('Oran Analizi'))
    expect(screen.getByText('Özkaynak Kârlılığı (ROE)')).toBeInTheDocument()
  })

  it('TUPRS: dividends tab is populated', () => {
    renderPage('TUPRS')
    fireEvent.click(screen.getByText('Temettü'))
    expect(screen.getByText('2026-09-10')).toBeInTheDocument()
  })

  it('THYAO: dividends tab shows fallback message (no scheduled dividend)', () => {
    renderPage('THYAO')
    fireEvent.click(screen.getByText('Temettü'))
    expect(screen.getByText('Bu hisse için planlanmış bir temettü bulunmuyor.')).toBeInTheDocument()
  })

  it('THYAO: fund holdings tab is populated', () => {
    renderPage('THYAO')
    fireEvent.click(screen.getByText('Fon Pozisyonları'))
    expect(screen.getByText('İş Portföy')).toBeInTheDocument()
  })

  it('TSLA: fund holdings tab shows fallback message (no mock fund holds it)', () => {
    renderPage('TSLA')
    fireEvent.click(screen.getByText('Fon Pozisyonları'))
    expect(screen.getByText('Bu hisseyi portföyünde tutan bir mock fon bulunamadı.')).toBeInTheDocument()
  })

  it('TUPRS: financials tab shows a negative (no +) earnings surprise', () => {
    renderPage('TUPRS')
    fireEvent.click(screen.getByText('Finansallar'))
    expect(screen.getByText(/-10.1%/)).toBeInTheDocument()
  })
})

describe('fmt', () => {
  it('returns "—" for undefined', () => {
    expect(fmt(undefined)).toBe('—')
  })

  it('formats a defined number with the given options', () => {
    expect(fmt(12.345, { minimumFractionDigits: 2, maximumFractionDigits: 2 })).toBe('12,35')
  })
})
