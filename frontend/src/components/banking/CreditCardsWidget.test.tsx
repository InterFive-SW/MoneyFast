import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import CreditCardsWidget from './CreditCardsWidget'
import type { CreditCard } from '../../data/mockBankingData'

const cards: CreditCard[] = [
  {
    id: 'cc-1', name: 'MoneyFast Platinum', brand: 'mastercard', cardNumber: '**** **** **** 4582',
    limit: 100000, currentDebt: 32450.75, availableLimit: 67549.25, dueDate: '2026-08-25', color: 'from-slate-800 to-slate-900',
  },
  {
    id: 'cc-2', name: 'Seyahat Kartı', brand: 'visa', cardNumber: '**** **** **** 9012',
    limit: 50000, currentDebt: 45000, availableLimit: 5000, dueDate: '2026-08-28', color: 'from-blue-900 to-brandBlue',
  },
]

describe('CreditCardsWidget', () => {
  it('mastercard ve visa markalarını, normal ve yüksek kullanım oranını gösterir', () => {
    render(<CreditCardsWidget cards={cards} onPayDebt={vi.fn()} onSettings={vi.fn()} />)
    expect(screen.getByText('mastercard')).toBeInTheDocument()
    expect(screen.getByText('VISA')).toBeInTheDocument()
    expect(screen.getByText('MoneyFast Platinum')).toBeInTheDocument()
    expect(screen.getByText('Seyahat Kartı')).toBeInTheDocument()
  })

  it('Borç Öde tıklanınca onPayDebt, Kart Ayarları tıklanınca onSettings çağrılır', () => {
    const onPayDebt = vi.fn()
    const onSettings = vi.fn()
    render(<CreditCardsWidget cards={cards} onPayDebt={onPayDebt} onSettings={onSettings} />)

    fireEvent.click(screen.getAllByText('Borç Öde')[0])
    expect(onPayDebt).toHaveBeenCalledWith('cc-1')

    fireEvent.click(screen.getAllByText('Kart Ayarları')[0])
    expect(onSettings).toHaveBeenCalledWith('MoneyFast Platinum')
  })
})
