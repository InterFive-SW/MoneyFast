import React, { useState, useEffect } from 'react'
import { MOCK_BANKING_DATA } from '../data/mockBankingData'
import type { BankingData, BankAccount, Bill, Loan, BankTransaction } from '../data/mockBankingData'

import AccountsSummaryWidget from '../components/banking/AccountsSummaryWidget'
import CreditCardsWidget from '../components/banking/CreditCardsWidget'
import QuickTransferWidget from '../components/banking/QuickTransferWidget'
import RecentTransactionsWidget from '../components/banking/RecentTransactionsWidget'
import BillsWidget from '../components/banking/BillsWidget'
import LoansWidget from '../components/banking/LoansWidget'

import NewAccountModal from '../components/banking/NewAccountModal'
import MoneyTransferModal from '../components/banking/MoneyTransferModal'
import BillPaymentModal from '../components/banking/BillPaymentModal'
import CardSettingsModal from '../components/banking/CardSettingsModal'
import LoanApplicationModal from '../components/banking/LoanApplicationModal'
import FeatureNotReadyModal from '../components/banking/FeatureNotReadyModal'

export default function Banking() {
  const [data, setData] = useState<BankingData | null>(null)
  const [loading, setLoading] = useState(true)
  
  // Modal states
  const [isNewAccountModalOpen, setIsNewAccountModalOpen] = useState(false)
  const [transferModalState, setTransferModalState] = useState<{ isOpen: boolean, accountId?: string }>({ isOpen: false })
  const [isBillModalOpen, setIsBillModalOpen] = useState(false)
  const [cardSettingsModalState, setCardSettingsModalState] = useState<{ isOpen: boolean, cardName?: string }>({ isOpen: false })
  const [isLoanModalOpen, setIsLoanModalOpen] = useState(false)
  const [notReadyModalState, setNotReadyModalState] = useState<{ isOpen: boolean, featureName: string }>({ isOpen: false, featureName: '' })

  useEffect(() => {
    // Simulating API fetch
    const timer = setTimeout(() => {
      setData(MOCK_BANKING_DATA)
      setLoading(false)
    }, 800)

    return () => clearTimeout(timer)
  }, [])

  // Action Handlers
  const handleAccountCreate = (currency: string, type: 'checking' | 'savings' | 'foreign_currency') => {
    if (!data) return
    const newAccount: BankAccount = {
      id: `acc-new-${Date.now()}`,
      name: `Yeni ${currency} Hesabı`,
      type,
      balance: 0,
      currency,
      accountNumber: `TR12 0006 2000 0001 2345 ${Math.floor(10 + Math.random() * 90)}`
    }
    setData({ ...data, accounts: [...data.accounts, newAccount] })
  }

  const handleTransfer = (amount: number, fromAccountId: string, toIban: string, description: string) => {
    if (!data) return
    
    // Yapan hesaptan düş
    const updatedAccounts = data.accounts.map(acc => {
      if (acc.id === fromAccountId || acc.name === fromAccountId) {
        return { ...acc, balance: acc.balance - amount }
      }
      return acc
    })

    // İşlem geçmişine ekle
    const newTx: BankTransaction = {
      id: `tx-new-${Date.now()}`,
      title: toIban, // IBAN veya İsim
      date: 'Bugün',
      amount,
      type: 'expense',
      category: 'Transfer',
      icon: '💸'
    }

    setData({
      ...data,
      accounts: updatedAccounts,
      recentTransactions: [newTx, ...data.recentTransactions],
      totalAssets: data.totalAssets - amount
    })
  }

  const handleBillPay = (billId: string) => {
    if (!data) return
    
    const updatedBills = data.bills.map(b => 
      b.id === billId ? { ...b, status: 'paid' as const } : b
    )
    
    const paidBill = data.bills.find(b => b.id === billId)
    const newTx: BankTransaction = {
      id: `tx-new-${Date.now()}`,
      title: paidBill?.institution || 'Fatura Ödemesi',
      date: 'Bugün',
      amount: paidBill?.amount || 0,
      type: 'expense',
      category: 'Fatura',
      icon: '📄'
    }

    setData({
      ...data,
      bills: updatedBills,
      recentTransactions: [newTx, ...data.recentTransactions],
      totalAssets: data.totalAssets - (paidBill?.amount || 0)
    })
  }

  const handleLoanApply = (amount: number) => {
    if (!data) return
    
    const newLoan: Loan = {
      id: `l-new-${Date.now()}`,
      title: 'Yeni İhtiyaç Kredisi',
      remainingAmount: amount,
      totalAmount: amount,
      nextInstallmentAmount: amount / 12, // örnek 12 ay
      nextInstallmentDate: '2026-09-19',
      remainingMonths: 12,
      progressPercentage: 0
    }

    setData({
      ...data,
      loans: [...data.loans, newLoan],
      totalAssets: data.totalAssets + amount // Hesaba para yattı
    })
  }

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center p-6">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-white/10 border-t-brandBlue" />
          <p className="text-sm font-medium text-slate-400">Hesap bilgileriniz yükleniyor...</p>
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="p-6 sm:p-8 min-h-screen">
        <h1 className="text-2xl font-bold tracking-tight text-white">Banka İşlemleri</h1>
        <p className="mt-4 text-slate-400">Verilere ulaşılamadı. Lütfen daha sonra tekrar deneyin.</p>
      </div>
    )
  }

  return (
    <div className="p-6 sm:p-8 min-h-screen relative pb-20">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Banka İşlemleri</h1>
          <p className="text-sm text-slate-400 mt-1">
            Tüm bankacılık ve finansal işlemlerinizi tek bir noktadan yönetin.
          </p>
        </div>
        <button 
          onClick={() => setIsNewAccountModalOpen(true)}
          className="bg-brandBlue hover:bg-blue-600 text-white font-medium px-4 py-2 rounded-xl transition-colors shadow-lg shadow-brandBlue/20 flex items-center justify-center gap-2 text-sm sm:w-auto"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Hesap Aç
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Sol Kolon (Hesaplar, Transfer, Faturalar) - Genişlik: 7/12 */}
        <div className="lg:col-span-7 flex flex-col gap-6">
          <AccountsSummaryWidget 
            accounts={data.accounts} 
            totalAssets={data.totalAssets} 
            onOpenTransfer={(accountId) => setTransferModalState({ isOpen: true, accountId })}
            onActionClick={(featureName) => setNotReadyModalState({ isOpen: true, featureName })}
          />
          <QuickTransferWidget contacts={data.savedContacts} />
          <BillsWidget 
            bills={data.bills} 
            onPayBill={(billId) => setIsBillModalOpen(true)}
          />
        </div>

        {/* Sağ Kolon (Kredi Kartları, Krediler, Son İşlemler) - Genişlik: 5/12 */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          <CreditCardsWidget 
            cards={data.creditCards} 
            onPayDebt={(cardId) => {
              setNotReadyModalState({ isOpen: true, featureName: 'Kredi Kartı Borç Ödeme' })
            }}
            onSettings={(cardName) => setCardSettingsModalState({ isOpen: true, cardName })}
          />
          <LoansWidget 
            loans={data.loans} 
            onApplyLoan={() => setIsLoanModalOpen(true)}
          />
          <RecentTransactionsWidget transactions={data.recentTransactions} />
        </div>
      </div>

      {/* Modals */}
      <NewAccountModal 
        isOpen={isNewAccountModalOpen} 
        onClose={() => setIsNewAccountModalOpen(false)} 
        onSuccess={handleAccountCreate}
      />
      <MoneyTransferModal 
        isOpen={transferModalState.isOpen}
        onClose={() => setTransferModalState({ isOpen: false })}
        defaultSenderAccountId={transferModalState.accountId}
        onTransfer={handleTransfer}
      />
      <BillPaymentModal 
        isOpen={isBillModalOpen}
        onClose={() => setIsBillModalOpen(false)}
        bills={data.bills}
        onPay={handleBillPay}
      />
      <CardSettingsModal 
        isOpen={cardSettingsModalState.isOpen}
        onClose={() => setCardSettingsModalState({ isOpen: false })}
        cardName={cardSettingsModalState.cardName}
      />
      <LoanApplicationModal 
        isOpen={isLoanModalOpen}
        onClose={() => setIsLoanModalOpen(false)}
        onApply={handleLoanApply}
      />
      <FeatureNotReadyModal 
        isOpen={notReadyModalState.isOpen}
        onClose={() => setNotReadyModalState({ isOpen: false, featureName: '' })}
        featureName={notReadyModalState.featureName}
      />
    </div>
  )
}
