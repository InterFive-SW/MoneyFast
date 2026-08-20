import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import BillsWidget from './BillsWidget'
import type { Bill } from '../../data/mockBankingData'

const bills: Bill[] = [
  { id: 'b-1', institution: 'İSKİ Su', type: 'water', amount: 245.5, dueDate: '2026-08-20', status: 'pending' },
  { id: 'b-2', institution: 'EnerjiSA', type: 'electricity', amount: 840, dueDate: '2026-08-22', status: 'pending' },
  { id: 'b-3', institution: 'Superonline', type: 'internet', amount: 350, dueDate: '2026-08-25', status: 'pending' },
  { id: 'b-4', institution: 'Türk Telekom', type: 'phone', amount: 120, dueDate: '2026-08-26', status: 'pending' },
  { id: 'b-5', institution: 'Ödenmiş Fatura', type: 'water', amount: 100, dueDate: '2026-07-01', status: 'paid' },
]

describe('BillsWidget', () => {
  it('bekleyen fatura yoksa boş durum mesajını gösterir', () => {
    render(<BillsWidget bills={[]} onPayBill={vi.fn()} />)
    expect(screen.getByText('Ödenecek fatura bulunmuyor.')).toBeInTheDocument()
  })

  it('tüm fatura tiplerini gösterir ve Öde tıklanınca onPayBill çağrılır', () => {
    const onPayBill = vi.fn()
    render(<BillsWidget bills={bills} onPayBill={onPayBill} />)

    expect(screen.getByText('İSKİ Su')).toBeInTheDocument()
    expect(screen.getByText('EnerjiSA')).toBeInTheDocument()
    expect(screen.getByText('Superonline')).toBeInTheDocument()
    expect(screen.getByText('Türk Telekom')).toBeInTheDocument()
    expect(screen.queryByText('Ödenmiş Fatura')).not.toBeInTheDocument()
    expect(screen.getByText('4 Adet')).toBeInTheDocument()

    fireEvent.click(screen.getAllByText('Öde')[0])
    expect(onPayBill).toHaveBeenCalledWith('b-1')
  })
})
