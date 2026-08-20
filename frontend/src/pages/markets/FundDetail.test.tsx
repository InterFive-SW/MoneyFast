import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import FundDetail, { fmtReturn, formatHoldingTooltip } from './FundDetail'

function renderPage(code: string) {
  return render(
    <MemoryRouter initialEntries={[`/investment/fonlar/${code}`]}>
      <Routes>
        <Route path="/investment/fonlar/:code" element={<FundDetail />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('FundDetail', () => {
  it('shows not-found message and back link for an unknown fund code', () => {
    renderPage('ZZZ')
    expect(screen.getByText(/"ZZZ" kodlu bir fon bulunamadı/)).toBeInTheDocument()
    expect(screen.getByText('← Fonlar listesine dön')).toBeInTheDocument()
  })

  it('renders summary (Özet) tab by default for a known fund', () => {
    renderPage('AFT')
    expect(screen.getByText('AFT')).toBeInTheDocument()
    expect(screen.getByText('Fon Büyüklüğü')).toBeInTheDocument()
  })

  it('shows holdings pie legend with resolved stock names when fund has holdings', () => {
    renderPage('AFT')
    fireEvent.click(screen.getByText('Portföy Dağılımı'))
    expect(screen.getByText('THYAO')).toBeInTheDocument()
    expect(screen.getByText('Türk Hava Yolları')).toBeInTheDocument()
  })

  it('shows a fallback message for a fund with no holdings (e.g. debt fund)', () => {
    renderPage('GPB')
    fireEvent.click(screen.getByText('Portföy Dağılımı'))
    expect(screen.getByText(/hisse portföyü verisi bulunmuyor/)).toBeInTheDocument()
  })

  it('shows returns tab with grayed out NA cells for missing 3Y/5Y data', () => {
    renderPage('YKT') // threeYear/fiveYear are null for this fund
    fireEvent.click(screen.getByText('Getiri'))
    expect(screen.getAllByText('NA').length).toBeGreaterThan(0)
  })

  it('shows returns tab with colored values when 3Y/5Y data is present', () => {
    renderPage('AFT')
    fireEvent.click(screen.getByText('Getiri'))
    expect(screen.getByText('Günlük')).toBeInTheDocument()
    expect(screen.queryByText('NA')).not.toBeInTheDocument()
  })
})

describe('formatHoldingTooltip', () => {
  it('formats the weight percentage with the symbol name', () => {
    expect(formatHoldingTooltip(18, 'THYAO')).toEqual(['%18', 'THYAO'])
  })
})

describe('fmtReturn', () => {
  it('returns "NA" for null', () => {
    expect(fmtReturn(null)).toBe('NA')
  })

  it('prefixes positive values with +', () => {
    expect(fmtReturn(5.5)).toBe('+5.5%')
  })

  it('does not prefix negative values (no mock fund has one, but this is real behavior)', () => {
    expect(fmtReturn(-3.2)).toBe('-3.2%')
  })
})
