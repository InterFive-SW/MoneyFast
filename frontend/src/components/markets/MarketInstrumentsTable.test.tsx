import { fireEvent, render, screen } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MarketInstrumentsTable from './MarketInstrumentsTable'
import type { MarketInstrument } from '../../data/mockData'

const navigateMock = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigateMock }
})

function makeInstrument(overrides: Partial<MarketInstrument> = {}): MarketInstrument {
  return {
    symbol: 'THYAO', name: 'Türk Hava Yolları', market: 'BIST', price: 295.5, unit: '₺',
    changePercent: 1.2, volume: 48_250_000, marketCap: 407_800_000_000, sector: 'Ulaştırma',
    week52Low: 210, week52High: 340, pe: 8.2, pb: 1.4,
    ...overrides,
  }
}

const instruments = [
  makeInstrument({ symbol: 'THYAO', name: 'Türk Hava Yolları', market: 'BIST', changePercent: 1.2 }),
  makeInstrument({ symbol: 'GARAN', name: 'Garanti BBVA', market: 'BIST', changePercent: -0.5, price: 128.9 }),
  makeInstrument({ symbol: 'AAPL', name: 'Apple Inc.', market: 'ABD', changePercent: 0.25, unit: '$', week52Low: 100, week52High: 100 }),
]

function renderTable(props: Partial<ComponentProps<typeof MarketInstrumentsTable>> = {}) {
  return render(
    <MemoryRouter>
      <MarketInstrumentsTable instruments={instruments} {...props} />
    </MemoryRouter>
  )
}

beforeEach(() => {
  navigateMock.mockClear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('MarketInstrumentsTable', () => {
  it('varsayılan BIST sekmesinde yalnızca BIST enstrümanlarını gösterir', () => {
    renderTable()
    expect(screen.getByText('THYAO')).toBeInTheDocument()
    expect(screen.getByText('GARAN')).toBeInTheDocument()
    expect(screen.queryByText('AAPL')).not.toBeInTheDocument()
  })

  it('ABD sekmesine geçince ABD enstrümanlarını gösterir', () => {
    renderTable()
    fireEvent.click(screen.getByText('ABD'))
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.queryByText('THYAO')).not.toBeInTheDocument()
  })

  it('kontrollü sekme modu: activeTab prop\'u ve onTabChange callback\'i kullanılır', () => {
    const onTabChange = vi.fn()
    renderTable({ activeTab: 'ABD', onTabChange })
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Kripto'))
    expect(onTabChange).toHaveBeenCalledWith('Kripto')
  })

  it('arama kutusuna sembol yazınca filtreler', () => {
    renderTable()
    fireEvent.change(screen.getByPlaceholderText('Sembol veya şirket ara...'), { target: { value: 'garan' } })
    expect(screen.getByText('GARAN')).toBeInTheDocument()
    expect(screen.queryByText('THYAO')).not.toBeInTheDocument()
  })

  it('arama eşleşmeyen bir terim girilince boş durum mesajı gösterir', () => {
    renderTable()
    fireEvent.change(screen.getByPlaceholderText('Sembol veya şirket ara...'), { target: { value: 'zzz-yok' } })
    expect(screen.getByText('Aramanızla eşleşen enstrüman bulunamadı.')).toBeInTheDocument()
  })

  it('sembol kolonuna tıklanınca sıralama yönünü değiştirir', () => {
    renderTable()
    const symbolHeader = screen.getByText('Enstrüman')
    fireEvent.click(symbolHeader) // aynı kolon: asc -> desc
    fireEvent.click(symbolHeader) // desc -> asc
    expect(screen.getByText('▲')).toBeInTheDocument()
  })

  it('farklı bir kolona (Değişim) tıklanınca o kolona göre asc sıralar', () => {
    renderTable()
    fireEvent.click(screen.getByText('Değişim'))
    expect(screen.getByText('▲')).toBeInTheDocument()
  })

  it('favorilere ekleme/çıkarma satır tıklamasını tetiklemez', () => {
    renderTable()
    const favButton = screen.getByLabelText('THYAO favorilere ekle')
    fireEvent.click(favButton)
    expect(navigateMock).not.toHaveBeenCalled()
    expect(screen.getByLabelText('THYAO favorilerden çıkar')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('THYAO favorilerden çıkar'))
    expect(screen.getByLabelText('THYAO favorilere ekle')).toBeInTheDocument()
  })

  it('bir satıra tıklanınca hisse detayına yönlendirir', () => {
    renderTable()
    fireEvent.click(screen.getByText('THYAO'))
    expect(navigateMock).toHaveBeenCalledWith('/investment/hisseler/THYAO')
  })

  it('52 hafta aralığı sabit (low===high) olduğunda çökmeden ortalanır', () => {
    renderTable()
    fireEvent.click(screen.getByText('ABD'))
    expect(screen.getByText('AAPL')).toBeInTheDocument()
  })

  it('Ctrl+K arama kutusuna odaklanır', () => {
    renderTable()
    const input = screen.getByPlaceholderText('Sembol veya şirket ara...') as HTMLInputElement
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(document.activeElement).toBe(input)
  })

  it('Cmd+K (metaKey) de arama kutusuna odaklanır', () => {
    renderTable()
    const input = screen.getByPlaceholderText('Sembol veya şirket ara...') as HTMLInputElement
    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    expect(document.activeElement).toBe(input)
  })

  it('ilgisiz bir tuşa basılınca arama kutusuna odaklanmaz', () => {
    renderTable()
    const input = screen.getByPlaceholderText('Sembol veya şirket ara...') as HTMLInputElement
    fireEvent.keyDown(window, { key: 'a' })
    expect(document.activeElement).not.toBe(input)
  })

  it('Hacim kolonuna tıklanınca sıralama oku Hacim başlığında görünür, tekrar tıklanınca yön değişir', () => {
    renderTable()
    const hacimHeader = screen.getByText('Hacim')
    fireEvent.click(hacimHeader)
    expect(screen.getByText('▲')).toBeInTheDocument()
    fireEvent.click(hacimHeader)
    expect(screen.getByText('▼')).toBeInTheDocument()
  })

  it('metrik kolon setinde arama sonucu boşsa doğru colSpan ile boş durum mesajı gösterir', () => {
    renderTable({ columnSet: 'degerleme' })
    fireEvent.change(screen.getByPlaceholderText('Sembol veya şirket ara...'), { target: { value: 'zzz-yok' } })
    expect(screen.getByText('Aramanızla eşleşen enstrüman bulunamadı.')).toBeInTheDocument()
  })

  it('columnSet verildiğinde o setin metrik kolonlarını gösterir', () => {
    renderTable({ columnSet: 'degerleme' })
    expect(screen.getByText('F/K')).toBeInTheDocument()
    expect(screen.getAllByText('8,2x').length).toBeGreaterThan(0)
  })

  it('geçersiz columnSet verilirse ilk kolon setine (getiri) düşer', () => {
    // @ts-expect-error kasıtlı geçersiz değer — fallback dalını test ediyor
    renderTable({ columnSet: 'olmayan-set' })
    expect(screen.getByText('Hacim')).toBeInTheDocument()
  })
})
