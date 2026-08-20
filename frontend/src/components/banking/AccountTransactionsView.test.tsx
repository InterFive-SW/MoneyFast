import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import AccountTransactionsView from './AccountTransactionsView'
import type { BankAccount, BankTransaction } from '../../data/mockBankingData'

const account: BankAccount = {
  id: 'acc-1', name: 'Vadesiz Maaş Hesabı', type: 'checking', balance: 12500.5, currency: 'TRY', accountNumber: 'TR120006200000012345',
}
const transactions: BankTransaction[] = [
  { id: 'tx-1', title: 'Migros', date: 'Bugün', amount: 850.4, type: 'expense', category: 'Market', icon: '🛒' },
  { id: 'tx-2', title: 'Gelen Transfer', date: 'Dün', amount: 2500, type: 'income', category: 'Transfer', icon: '💸' },
]

let mockContext: { data: { accounts: BankAccount[]; recentTransactions: BankTransaction[] } }

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useOutletContext: () => mockContext }
})

function renderAt(accountId: string) {
  return render(
    <MemoryRouter initialEntries={[`/banking/accounts/${accountId}/transactions`]}>
      <Routes>
        <Route path="/banking/accounts/:accountId/transactions" element={<AccountTransactionsView />} />
        <Route path="/banking/accounts" element={<div>Hesaplar Sayfası</div>} />
      </Routes>
    </MemoryRouter>
  )
}

describe('AccountTransactionsView', () => {
  it('hesap bulunamazsa /banking/accounts\'a yönlendirir', () => {
    mockContext = { data: { accounts: [], recentTransactions: transactions } }
    renderAt('bilinmeyen-id')
    expect(screen.getByText('Hesaplar Sayfası')).toBeInTheDocument()
  })

  it('işlem yoksa boş durum mesajını gösterir', () => {
    mockContext = { data: { accounts: [account], recentTransactions: [] } }
    renderAt('acc-1')
    expect(screen.getByText('Bu hesaba ait henüz bir işlem bulunmuyor.')).toBeInTheDocument()
  })

  it('gelir ve gider işlemlerini gösterir, Geri butonuna basınca hesaplar sayfasına döner', () => {
    mockContext = { data: { accounts: [account], recentTransactions: transactions } }
    renderAt('acc-1')
    expect(screen.getByText('Migros')).toBeInTheDocument()
    expect(screen.getByText('Gelen Transfer')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Geri'))
    expect(screen.getByText('Hesaplar Sayfası')).toBeInTheDocument()
  })
})
