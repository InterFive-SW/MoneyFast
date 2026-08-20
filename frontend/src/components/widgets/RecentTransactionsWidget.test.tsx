import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RecentTransactionsWidget from './RecentTransactionsWidget'
import type { TransactionData } from '../../data/mockData'

const transactions: TransactionData[] = [
  { id: 't1', description: 'Maaş', category: 'Gelir', amount: 45_000, date: '2026-08-14T10:15:00' },
  { id: 't2', description: 'Market Alışverişi', category: 'Market', amount: -650.5, date: '2026-08-13T15:45:00' },
]

describe('RecentTransactionsWidget', () => {
  it('pozitif tutarlı işlemi + işaretiyle ve vurgulu renkle gösterir', () => {
    render(<RecentTransactionsWidget transactions={transactions} />)
    expect(screen.getByText('Maaş')).toBeInTheDocument()
    expect(screen.getByText(/\+.*45\.000,00/)).toBeInTheDocument()
  })

  it('negatif tutarlı işlemi işaretsiz gösterir', () => {
    render(<RecentTransactionsWidget transactions={transactions} />)
    expect(screen.getByText('Market Alışverişi')).toBeInTheDocument()
    expect(screen.getByText(/-.*650,50/)).toBeInTheDocument()
  })
})
