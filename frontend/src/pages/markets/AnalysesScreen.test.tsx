import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import AnalysesScreen from './AnalysesScreen'

function renderPage() {
  return render(
    <MemoryRouter>
      <AnalysesScreen />
    </MemoryRouter>
  )
}

describe('AnalysesScreen', () => {
  it('shows the earnings reports (bilancolar) tab by default with positive and negative surprises', () => {
    renderPage()
    expect(screen.getByText('THYAO')).toBeInTheDocument() // linked (found instrument)
    expect(screen.getByText('+7.8%')).toBeInTheDocument()
    expect(screen.getByText('-10.1%')).toBeInTheDocument()
  })

  it('shows a "coming soon" placeholder for an unavailable report type', () => {
    renderPage()
    fireEvent.click(screen.getByText('Geri Alımlar'))
    expect(screen.getByText('"Geri Alımlar" raporu yakında eklenecek.')).toBeInTheDocument()
  })

  it('shows IPO announcements with all three status badges', () => {
    renderPage()
    fireEvent.click(screen.getByText('Halka Arzlar'))
    expect(screen.getAllByText('Yaklaşan').length).toBeGreaterThan(0)
    expect(screen.getByText('Devam Ediyor')).toBeInTheDocument()
    expect(screen.getByText('Tamamlandı')).toBeInTheDocument()
  })

  it('shows dividend announcements, resolving known symbols and falling back to plain text for unknown ones', () => {
    renderPage()
    fireEvent.click(screen.getByText('Temettü'))
    expect(screen.getByRole('link', { name: 'AKBNK' })).toBeInTheDocument() // known instrument -> Link
    const doas = screen.getByText('DOAS') // unknown instrument -> plain span
    expect(doas.closest('a')).toBeNull()
  })

  it('shows analyst recommendations with Al/Tut/Sat colors and a dash for missing previous target', () => {
    renderPage()
    fireEvent.click(screen.getByText('Analist Tavsiyeleri'))
    expect(screen.getAllByText('Al').length).toBeGreaterThan(0)
    expect(screen.getByText('Sat')).toBeInTheDocument()
    expect(screen.getAllByText('Tut').length).toBeGreaterThan(0)
    expect(screen.getByText('—')).toBeInTheDocument() // BIMAS has previousTargetPrice: null
  })

  it('shows capital increases with all three status badges', () => {
    renderPage()
    fireEvent.click(screen.getByText('Sermaye Artırımları'))
    expect(screen.getByText('Onaylandı')).toBeInTheDocument()
    expect(screen.getAllByText('Beklemede').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Tamamlandı').length).toBeGreaterThan(0)
  })
})
