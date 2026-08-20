import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import StockFilterPanel, { applyStockFilters, EMPTY_STOCK_FILTERS, type StockFilters } from './StockFilterPanel'
import type { MarketInstrument } from '../../data/mockData'

function makeInstrument(overrides: Partial<MarketInstrument> = {}): MarketInstrument {
  return {
    symbol: 'THYAO', name: 'Türk Hava Yolları', market: 'BIST', price: 295.5, unit: '₺',
    changePercent: 1.2, volume: 1000, marketCap: 400_000_000_000, sector: 'Ulaştırma', week52Low: 200, week52High: 300,
    pe: 8, pb: 1.4,
    ...overrides,
  }
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('applyStockFilters', () => {
  const withPe = makeInstrument({ symbol: 'A', pe: 8, pb: 1.4, marketCap: 400_000_000_000, changePercent: 1.2, sector: 'Ulaştırma' })
  const withoutPe = makeInstrument({ symbol: 'B', pe: undefined, pb: undefined, marketCap: 50_000_000_000, changePercent: -2, sector: 'Kripto Para' })
  const instruments = [withPe, withoutPe]

  it('filtresiz tüm enstrümanları döner', () => {
    expect(applyStockFilters(instruments, EMPTY_STOCK_FILTERS)).toHaveLength(2)
  })

  it('peMin filtresi pe tanımsız olanı ve düşük pe\'liyi eler', () => {
    const result = applyStockFilters(instruments, { ...EMPTY_STOCK_FILTERS, peMin: '5' })
    expect(result.map((i) => i.symbol)).toEqual(['A'])
  })

  it('peMax filtresi yüksek pe\'liyi eler', () => {
    const result = applyStockFilters(instruments, { ...EMPTY_STOCK_FILTERS, peMax: '5' })
    expect(result.map((i) => i.symbol)).toEqual([])
  })

  it('pbMin filtresi pb tanımsız olanı eler', () => {
    const result = applyStockFilters(instruments, { ...EMPTY_STOCK_FILTERS, pbMin: '1' })
    expect(result.map((i) => i.symbol)).toEqual(['A'])
  })

  it('pbMax filtresi yüksek pb\'liyi eler', () => {
    const result = applyStockFilters(instruments, { ...EMPTY_STOCK_FILTERS, pbMax: '1' })
    expect(result.map((i) => i.symbol)).toEqual([])
  })

  it('marketCapMinBn filtresi küçük şirketi eler', () => {
    const result = applyStockFilters(instruments, { ...EMPTY_STOCK_FILTERS, marketCapMinBn: '100' })
    expect(result.map((i) => i.symbol)).toEqual(['A'])
  })

  it('marketCapMaxBn filtresi büyük şirketi eler', () => {
    const result = applyStockFilters(instruments, { ...EMPTY_STOCK_FILTERS, marketCapMaxBn: '100' })
    expect(result.map((i) => i.symbol)).toEqual(['B'])
  })

  it('changeMin filtresi düşük değişimi eler', () => {
    const result = applyStockFilters(instruments, { ...EMPTY_STOCK_FILTERS, changeMin: '0' })
    expect(result.map((i) => i.symbol)).toEqual(['A'])
  })

  it('changeMax filtresi yüksek değişimi eler', () => {
    const result = applyStockFilters(instruments, { ...EMPTY_STOCK_FILTERS, changeMax: '0' })
    expect(result.map((i) => i.symbol)).toEqual(['B'])
  })

  it('sector filtresi eşleşmeyeni eler', () => {
    const result = applyStockFilters(instruments, { ...EMPTY_STOCK_FILTERS, sector: 'Kripto Para' })
    expect(result.map((i) => i.symbol)).toEqual(['B'])
  })
})

describe('StockFilterPanel', () => {
  const filters: StockFilters = EMPTY_STOCK_FILTERS

  it('Temizle butonuna basınca boş filtrelerle onChange çağırır', () => {
    const onChange = vi.fn()
    render(<StockFilterPanel filters={{ ...filters, peMin: '5' }} onChange={onChange} sectors={['Bankacılık']} />)
    fireEvent.click(screen.getByText('Temizle'))
    expect(onChange).toHaveBeenCalledWith(EMPTY_STOCK_FILTERS)
  })

  it('F/K min alanı değiştirilince onChange doğru alanla çağrılır', () => {
    const onChange = vi.fn()
    render(<StockFilterPanel filters={filters} onChange={onChange} sectors={['Bankacılık']} />)
    fireEvent.change(screen.getAllByPlaceholderText('Min')[0], { target: { value: '10' } })
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_STOCK_FILTERS, peMin: '10' })
  })

  it('geri kalan tüm sayısal filtre alanları ve sektör seçimi onChange\'i doğru alanla tetikler', () => {
    const onChange = vi.fn()
    render(<StockFilterPanel filters={filters} onChange={onChange} sectors={['Bankacılık']} />)

    const mins = screen.getAllByPlaceholderText('Min') // peMin, pbMin, marketCapMinBn, changeMin
    const maxs = screen.getAllByPlaceholderText('Max')  // peMax, pbMax, marketCapMaxBn, changeMax

    fireEvent.change(maxs[0], { target: { value: '20' } })
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_STOCK_FILTERS, peMax: '20' })

    fireEvent.change(mins[1], { target: { value: '1' } })
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_STOCK_FILTERS, pbMin: '1' })

    fireEvent.change(maxs[1], { target: { value: '5' } })
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_STOCK_FILTERS, pbMax: '5' })

    fireEvent.change(mins[2], { target: { value: '50' } })
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_STOCK_FILTERS, marketCapMinBn: '50' })

    fireEvent.change(maxs[2], { target: { value: '500' } })
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_STOCK_FILTERS, marketCapMaxBn: '500' })

    fireEvent.change(mins[3], { target: { value: '-5' } })
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_STOCK_FILTERS, changeMin: '-5' })

    fireEvent.change(maxs[3], { target: { value: '5' } })
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_STOCK_FILTERS, changeMax: '5' })

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'Bankacılık' } })
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_STOCK_FILTERS, sector: 'Bankacılık' })
  })

  it('kayıtlı arama yoksa "yok" gösterir', () => {
    render(<StockFilterPanel filters={filters} onChange={vi.fn()} sectors={[]} />)
    expect(screen.getByText('yok')).toBeInTheDocument()
  })

  it('bozuk localStorage verisiyle çökmeden boş liste ile başlar', () => {
    localStorage.setItem('mf_stock_saved_searches', '{ geçersiz json')
    render(<StockFilterPanel filters={filters} onChange={vi.fn()} sectors={[]} />)
    expect(screen.getByText('yok')).toBeInTheDocument()
  })

  it('arama kaydet: boş isimle kaydetmeye çalışınca hiçbir şey olmaz', () => {
    render(<StockFilterPanel filters={filters} onChange={vi.fn()} sectors={[]} />)
    fireEvent.click(screen.getByText('+ Bu Aramayı Kaydet'))
    fireEvent.click(screen.getByText('Kaydet'))
    expect(screen.getByText('yok')).toBeInTheDocument()
  })

  it('arama kaydet, yükle ve sil akışı çalışır', () => {
    const onChange = vi.fn()
    render(<StockFilterPanel filters={{ ...filters, peMin: '10' }} onChange={onChange} sectors={[]} />)

    fireEvent.click(screen.getByText('+ Bu Aramayı Kaydet'))
    fireEvent.change(screen.getByPlaceholderText('Arama adı...'), { target: { value: 'Ucuz Hisseler' } })
    fireEvent.click(screen.getByText('Kaydet'))

    expect(screen.getByText('Ucuz Hisseler')).toBeInTheDocument()
    expect(localStorage.getItem('mf_stock_saved_searches')).toContain('Ucuz Hisseler')

    fireEvent.click(screen.getByText('Ucuz Hisseler'))
    expect(onChange).toHaveBeenCalledWith({ ...filters, peMin: '10' })

    fireEvent.click(screen.getByLabelText('Ucuz Hisseler sil'))
    expect(screen.getByText('yok')).toBeInTheDocument()
  })

  it('kaydet formu iptal edilince gizlenir', () => {
    render(<StockFilterPanel filters={filters} onChange={vi.fn()} sectors={[]} />)
    fireEvent.click(screen.getByText('+ Bu Aramayı Kaydet'))
    fireEvent.click(screen.getByText('İptal'))
    expect(screen.getByText('+ Bu Aramayı Kaydet')).toBeInTheDocument()
  })
})
