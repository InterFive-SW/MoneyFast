import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import IndicesScreen, { formatIndexComparisonTooltip } from './IndicesScreen'

function renderPage() {
  return render(
    <MemoryRouter>
      <IndicesScreen />
    </MemoryRouter>
  )
}

describe('IndicesScreen', () => {
  it('varsayılan olarak BIST 100 (XU100) genişletilmiş halde render edilir, benchmark XU030 olur', () => {
    renderPage()
    expect(screen.getAllByText('BIST 100').length).toBeGreaterThan(0)
    expect(screen.getByText('Endeks Ağırlıkları')).toBeInTheDocument()
    expect(screen.getByText(/vs BIST 30/)).toBeInTheDocument()
  })

  it('XU100 başlığına tıklanınca daralır', () => {
    renderPage()
    const header = screen.getAllByText('BIST 100').find((el) => el.closest('button'))!
    fireEvent.click(header)
    expect(screen.queryByText('Endeks Ağırlıkları')).not.toBeInTheDocument()
  })

  it('farklı bir endeks genişletilince benchmark XU100 olur', () => {
    renderPage()
    fireEvent.click(screen.getByText('BIST Bankacılık'))
    expect(screen.getByText(/vs BIST 100/)).toBeInTheDocument()
  })

  it('pozitif ve negatif değişimli endeksleri farklı renklerle gösterir', () => {
    renderPage()
    expect(screen.getByText('+0.87%')).toBeInTheDocument() // XU100
    expect(screen.getByText('-0.45%')).toBeInTheDocument() // XBANK
  })
})

describe('formatIndexComparisonTooltip', () => {
  it('formats positive value with + sign', () => {
    expect(formatIndexComparisonTooltip(5, 'XU100')).toEqual(['+5%', 'XU100'])
  })

  it('formats negative value without extra sign', () => {
    expect(formatIndexComparisonTooltip(-3, 'XU030')).toEqual(['-3%', 'XU030'])
  })
})
