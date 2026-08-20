import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import LoansWidget from './LoansWidget'
import type { Loan } from '../../data/mockBankingData'

const loans: Loan[] = [
  {
    id: 'l-1', title: 'İhtiyaç Kredisi', remainingAmount: 45000, totalAmount: 100000,
    nextInstallmentAmount: 5200, nextInstallmentDate: '2026-09-05', remainingMonths: 9, progressPercentage: 55,
  },
]

describe('LoansWidget', () => {
  it('aktif kredi yoksa boş durum mesajını gösterir', () => {
    render(<LoansWidget loans={[]} onApplyLoan={vi.fn()} />)
    expect(screen.getByText('Aktif krediniz bulunmuyor.')).toBeInTheDocument()
  })

  it('aktif kredileri listeler', () => {
    render(<LoansWidget loans={loans} onApplyLoan={vi.fn()} />)
    expect(screen.getByText('İhtiyaç Kredisi')).toBeInTheDocument()
    expect(screen.getByText(/₺45\.000,00/)).toBeInTheDocument()
  })

  it('Kredi Başvurusu tıklanınca onApplyLoan çağrılır', () => {
    const onApplyLoan = vi.fn()
    render(<LoansWidget loans={loans} onApplyLoan={onApplyLoan} />)
    fireEvent.click(screen.getByText('Kredi Başvurusu'))
    expect(onApplyLoan).toHaveBeenCalled()
  })
})
