import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RecentTransactionsWidget from './RecentTransactionsWidget'
import type { BankTransaction } from '../../data/mockBankingData'

const transactions: BankTransaction[] = [
  { id: 'tx-1', title: 'Migros', date: 'Bugün', amount: 850.4, type: 'expense', category: 'Market', icon: '🛒' },
  { id: 'tx-2', title: 'Gelen Transfer', date: 'Dün', amount: 2500, type: 'income', category: 'Transfer', icon: '💸' },
]

describe('RecentTransactionsWidget', () => {
  it('gelir ve gider işlemlerini doğru işaret ve renkle gösterir', () => {
    render(<RecentTransactionsWidget transactions={transactions} />)
    expect(screen.getByText('Migros')).toBeInTheDocument()
    expect(screen.getByText(/-₺850,40/)).toBeInTheDocument()
    expect(screen.getByText('Gelen Transfer')).toBeInTheDocument()
    expect(screen.getByText(/\+₺2\.500,00/)).toBeInTheDocument()
  })
})
