import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import BillPaymentModal from './BillPaymentModal'
import type { Bill } from '../../data/mockBankingData'

const bills: Bill[] = [
  { id: 'b-1', institution: 'İSKİ Su', type: 'water', amount: 245.5, dueDate: '2026-08-20', status: 'pending' },
  { id: 'b-2', institution: 'EnerjiSA', type: 'electricity', amount: 840, dueDate: '2026-08-22', status: 'pending' },
]

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('BillPaymentModal', () => {
  it('kapalıyken hiçbir şey render etmez', () => {
    const { container } = render(<BillPaymentModal isOpen={false} onClose={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('bills verilmezse ve bekleyen fatura yoksa uyarı gösterir, Faturayı Getir disabled olur', () => {
    render(<BillPaymentModal isOpen={true} onClose={vi.fn()} />)
    expect(screen.getByText('Ödenecek faturanız bulunmamaktadır.')).toBeInTheDocument()
    expect(screen.getByText('Faturayı Getir')).toBeDisabled()
  })

  it('fatura seçip ödeme akışını tamamlar, onPay ve onClose çağrılır', () => {
    const onPay = vi.fn()
    const onClose = vi.fn()
    render(<BillPaymentModal isOpen={true} onClose={onClose} bills={bills} onPay={onPay} />)

    const select = screen.getByRole('combobox') as HTMLSelectElement
    expect(select.value).toBe('b-1')
    fireEvent.change(select, { target: { value: 'b-2' } })
    expect(select.value).toBe('b-2')

    fireEvent.click(screen.getByText('Faturayı Getir'))
    expect(screen.getByText('EnerjiSA')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Ödemeyi Tamamla'))
    expect(onPay).toHaveBeenCalledWith('b-2')
    expect(onClose).toHaveBeenCalled()

    vi.advanceTimersByTime(300)
  })

  it('Geri Dön butonu 2. adımdan 1. adıma döner', () => {
    render(<BillPaymentModal isOpen={true} onClose={vi.fn()} bills={bills} onPay={vi.fn()} />)
    fireEvent.click(screen.getByText('Faturayı Getir'))
    fireEvent.click(screen.getByText('Geri Dön'))
    expect(screen.getByText('Faturayı Getir')).toBeInTheDocument()
  })

  it('onPay verilmemişse ödeme tamamlama hata vermez', () => {
    render(<BillPaymentModal isOpen={true} onClose={vi.fn()} bills={bills} />)
    fireEvent.click(screen.getByText('Faturayı Getir'))
    fireEvent.click(screen.getByText('Ödemeyi Tamamla'))
    vi.advanceTimersByTime(300)
  })
})
