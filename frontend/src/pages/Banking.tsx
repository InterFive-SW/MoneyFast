import React, { useState, useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { MOCK_BANKING_DATA } from '../data/mockBankingData'
import type { BankingData, BankAccount, BankTransaction } from '../data/mockBankingData'

// Modals
import BillPaymentModal from '../components/banking/BillPaymentModal'
import FeatureNotReadyModal from '../components/banking/FeatureNotReadyModal'
import CloseAccountModal from '../components/banking/CloseAccountModal'

export interface BankingContextType {
  data: BankingData;
  handleAccountCreate: (currency: string, type: 'checking' | 'savings' | 'foreign_currency', accountName: string, iban: string) => void;
  handleAccountClose: (accountId: string) => void;
  handleCardCreate: (type: 'credit' | 'debit', brand: 'mastercard' | 'visa', limit: number, isDigital: boolean, customName: string, linkedAccountId?: string) => void;
  updateCard: (cardId: string, updates: Partial<CreditCard>) => void;
  handleTransfer: (amount: number, fromAccountId: string, toIban: string, description: string) => void;
  handleBillPay: (billId: string) => void;
  openCloseAccountModal: (accountId: string) => void;
  openFeatureNotReadyModal: (featureName: string) => void;
  openBillPaymentModal: () => void;
}

export default function Banking() {
  const [data, setData] = useState<BankingData | null>(null)
  const [loading, setLoading] = useState(true)
  
  // Modal states
  const [closeAccountState, setCloseAccountState] = useState<{ isOpen: boolean, accountId?: string }>({ isOpen: false })
  const [isBillModalOpen, setIsBillModalOpen] = useState(false)
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
  const handleAccountCreate = (currency: string, type: 'checking' | 'savings' | 'foreign_currency', accountName: string, iban: string) => {
    // Bu handler'lar sadece data yüklendikten sonra render edilen Outlet'e context
    // olarak geçiyor, bu yüzden data her zaman dolu — savunma amaçlı koruma.
    /* v8 ignore next */
    if (!data) return
    const newAccount: BankAccount = {
      id: `acc-new-${Date.now()}`,
      name: accountName || `Yeni ${currency} Hesabı`,
      type,
      balance: 0,
      currency,
      accountNumber: iban
    }
    setData({ ...data, accounts: [...data.accounts, newAccount] })
  }

  const handleAccountClose = (accountId: string) => {
    /* v8 ignore next */
    if (!data) return
    const accountToClose = data.accounts.find(a => a.id === accountId)
    // accountId her zaman openCloseAccountModal(selectedAccount.id) ile, yani var olan
    // bir hesaptan geliyor — bulunamama durumu gerçek akışta oluşmuyor.
    /* v8 ignore next */
    if (!accountToClose) return
    
    // Filtreleyerek hesabı sil
    const updatedAccounts = data.accounts.filter(a => a.id !== accountId)
    
    setData({
      ...data,
      accounts: updatedAccounts,
      // Hesaptaki bakiye mock gereği toplam varlıklardan düşülecek
      totalAssets: data.totalAssets - accountToClose.balance
    })
  }

  const handleCardCreate = (type: 'credit' | 'debit', brand: 'mastercard' | 'visa', limit: number, isDigital: boolean, customName: string, linkedAccountId?: string) => {
    /* v8 ignore next */
    if (!data) return
    const newCard = {
      id: `cc-new-${Date.now()}`,
      name: customName || (type === 'credit' ? 'Yeni Kredi Kartı' : 'Yeni Banka Kartı'),
      brand,
      cardNumber: `**** **** **** ${Math.floor(Math.random() * 9000 + 1000)}`,
      limit: type === 'credit' ? limit : 0,
      currentDebt: 0,
      availableLimit: type === 'credit' ? limit : 0,
      dueDate: '2026-09-25',
      color: type === 'credit' ? 'from-purple-900 to-indigo-900' : 'from-slate-700 to-slate-900',
      isDigital,
      settings: {
        onlineShopping: true,
        contactless: !isDigital,
        isFrozen: false
      },
      linkedAccountId
    }
    setData({ ...data, creditCards: [...data.creditCards, newCard] })
  }

  const updateCard = (cardId: string, updates: Partial<CreditCard>) => {
    /* v8 ignore next */
    if (!data) return
    
    // Deep merge for settings
    const updatedCards = data.creditCards.map(c => {
      if (c.id === cardId) {
        return {
          ...c,
          ...updates,
          settings: {
            ...c.settings,
            ...(updates.settings || {})
          }
        }
      }
      return c
    })
    
    setData({ ...data, creditCards: updatedCards })
  }

  const handleTransfer = (amount: number, fromAccountId: string, toIban: string, description: string) => {
    /* v8 ignore next */
    if (!data) return
    
    const updatedAccounts = data.accounts.map(acc => {
      if (acc.id === fromAccountId || acc.name === fromAccountId) {
        return { ...acc, balance: acc.balance - amount }
      }
      return acc
    })

    const newTx: BankTransaction = {
      id: `tx-new-${Date.now()}`,
      title: toIban,
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
    /* v8 ignore next */
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

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center p-6">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-white/10 border-t-brandBlue" />
          <p className="text-sm font-medium text-slate-400">Veriler yükleniyor...</p>
        </div>
      </div>
    )
  }

  // loading ve data aynı setTimeout içinde birlikte set edildiği için loading false
  // olduğunda data her zaman dolu — bu blok gerçek akışta ulaşılamıyor.
  /* v8 ignore next 8 */
  if (!data) {
    return (
      <div className="p-6 sm:p-8 min-h-screen">
        <h1 className="text-2xl font-bold tracking-tight text-white">Banka İşlemleri</h1>
        <p className="mt-4 text-slate-400">Verilere ulaşılamadı.</p>
      </div>
    )
  }

  const contextValue: BankingContextType = {
    data,
    handleAccountCreate,
    handleAccountClose,
    handleCardCreate,
    updateCard,
    handleTransfer,
    handleBillPay,
    openCloseAccountModal: (accountId) => setCloseAccountState({ isOpen: true, accountId }),
    openFeatureNotReadyModal: (featureName) => setNotReadyModalState({ isOpen: true, featureName }),
    openBillPaymentModal: () => setIsBillModalOpen(true)
  }

  return (
    <div className="p-4 sm:p-8 min-h-screen relative pb-20 overflow-x-hidden">
      
      {/* SPA Routing - Child views rendered here via React Router */}
      <div className="relative w-full transition-all duration-500 ease-in-out">
        <Outlet context={contextValue} />
      </div>

      {/* Modals */}
      <BillPaymentModal 
        isOpen={isBillModalOpen}
        onClose={() => setIsBillModalOpen(false)}
        bills={data.bills}
        onPay={handleBillPay}
      />
      <FeatureNotReadyModal 
        isOpen={notReadyModalState.isOpen}
        onClose={() => setNotReadyModalState({ isOpen: false, featureName: '' })}
        featureName={notReadyModalState.featureName}
      />
      <CloseAccountModal
        isOpen={closeAccountState.isOpen}
        onClose={() => setCloseAccountState({ isOpen: false })}
        account={data.accounts.find(a => a.id === closeAccountState.accountId) || null}
        onConfirm={handleAccountClose}
      />
    </div>
  )
}
