import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import SectorsScreen from './SectorsScreen'

function renderPage() {
  return render(
    <MemoryRouter>
      <SectorsScreen />
    </MemoryRouter>
  )
}

describe('SectorsScreen', () => {
  it('en sektörler, en hisseler ve resmi sektör listesini render eder', () => {
    renderPage()
    expect(screen.getByText('En Sektörler')).toBeInTheDocument()
    expect(screen.getByText('En Hisseler')).toBeInTheDocument()
    expect(screen.getByText('Sektörler')).toBeInTheDocument()
    expect(screen.getByText('Bankacılık')).toBeInTheDocument()
  })

  it('bir sektöre tıklanınca genişler, F/K değerleri tanımlıysa gösterir, tekrar tıklanınca daralır', () => {
    renderPage()
    // "Sanayi" metni hem "En Sektörler" özetinde hem tam listede geçebiliyor —
    // genişletilebilir olan (buton içindeki) örneği seçiyoruz.
    // Sanayi: SISE ve EREGL, ikisi de negatif değişimli — tüm oran alanları dolu.
    const header = screen.getAllByText('Sanayi').find((el) => el.closest('button'))!
    fireEvent.click(header)
    expect(screen.getByText('SISE')).toBeInTheDocument()
    expect(screen.getByText('EREGL')).toBeInTheDocument()

    fireEvent.click(header)
    expect(screen.queryByText('SISE')).not.toBeInTheDocument()
  })

  it('oran verisi tanımsız olan bir sektörde (Kripto Para) "—" gösterir', () => {
    renderPage()
    // "Kripto Para" metni hem "En Sektörler" özetinde hem de tam listede geçiyor —
    // genişletilebilir olan (buton içindeki) örneği seçiyoruz.
    const header = screen.getAllByText('Kripto Para').find((el) => el.closest('button'))!
    fireEvent.click(header)
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('özel bir grup genişletilip daraltılabilir', () => {
    renderPage()
    const groupHeader = screen.getByText('Savunma & Havacılık (Özel Grup)')
    fireEvent.click(groupHeader)
    expect(screen.getByText('ASELS')).toBeInTheDocument()

    fireEvent.click(groupHeader)
    expect(screen.queryByText('ASELS')).not.toBeInTheDocument()
  })
})
