import { useState, useEffect, useCallback } from 'react'
import { Outlet } from 'react-router-dom'
import { MOCK_BANKING_DATA } from '../data/mockBankingData'
import type {
  BankingData, BankAccount, BankTransaction, CardSettings, CreditCardUpdate,
} from '../data/mockBankingData'
import { apiClient } from '../api/client'
import type { BankAccount as ApiBankAccount, Movement } from '../api/client'

// Modals
import BillPaymentModal from '../components/banking/BillPaymentModal'
import FeatureNotReadyModal from '../components/banking/FeatureNotReadyModal'
import CloseAccountModal from '../components/banking/CloseAccountModal'

/**
 * Hesap türü etiketleri.
 *
 * Backend hesabı `account_type` ile ("vadesiz") tanımlıyor ama ekranda
 * gösterilecek bir ad tutmuyor; ada karar vermek sunumun işi, kaydın değil.
 */
const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  vadesiz: 'Vadesiz Hesap',
  vadeli: 'Vadeli Hesap',
  birikim: 'Birikim Hesabı',
}

/** Bir hesabın hareketlerinden kaç tanesi çekilsin. */
const STATEMENT_LIMIT = 50

/**
 * Backend'in `account_type`'ı arayüzün beklediği üç kategoriye eşlenir.
 *
 * Para birimi türün önüne geçiyor: TRY olmayan bir vadesiz hesap, arayüzde
 * "vadesiz" değil "döviz" olarak gösterilmeli — kullanıcının o hesabı ayırt
 * etmesini sağlayan şey vadesi değil, para birimi.
 */
function toUiAccountType(
  apiType: string,
  currencyCode: string,
): BankAccount['type'] {
  if (currencyCode !== 'TRY') return 'foreign_currency'
  if (apiType === 'vadeli' || apiType === 'birikim') return 'savings'
  return 'checking'
}

/** IBAN'ı dörtlü gruplara ayırır: TR000001212962... -> "TR00 0001 2129 62...". */
function formatIban(iban: string): string {
  return (iban || '').replace(/\s+/g, '').replace(/(.{4})/g, '$1 ').trim()
}

function toUiAccount(account: ApiBankAccount): BankAccount {
  return {
    id: account.id,
    name: ACCOUNT_TYPE_LABELS[account.account_type] ?? 'Hesap',
    type: toUiAccountType(account.account_type, account.currency_code),
    balance: account.balance,
    currency: account.currency_code,
    accountNumber: formatIban(account.iban),
  }
}

/**
 * Hareket tarihini listede okunacak biçime çevirir.
 *
 * Bugün ve dün ad olarak yazılıyor; daha eskisi için gün + kısa ay yetiyor,
 * çünkü liste zaten en yeniden eskiye sıralı ve yıl bilgisi gürültü.
 */
function formatMovementDate(isoDate: string): string {
  const date = new Date(isoDate)
  if (Number.isNaN(date.getTime())) return ''

  const startOfDay = (value: Date) =>
    new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime()
  const dayDiff = Math.round(
    (startOfDay(new Date()) - startOfDay(date)) / 86_400_000,
  )

  if (dayDiff === 0) return 'Bugün'
  if (dayDiff === 1) return 'Dün'
  return date.toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' })
}

/**
 * Defter bacağını arayüzün işlem satırına çevirir.
 *
 * Bir transferin iki bacağı aynı `reference_number`'ı taşır, o yüzden anahtar
 * olarak yön de ekleniyor: kendi hesapları arasında para taşıyan bir kullanıcı
 * listede aynı referansı hem gider hem gelir olarak görür ve React'in bu iki
 * satırı ayırt edebilmesi gerekir.
 */
function toUiTransaction(movement: Movement): BankTransaction {
  const isIncome = movement.direction === 'CREDIT'
  const counterparty = movement.counterparty_iban
    ? formatIban(movement.counterparty_iban)
    : ''

  return {
    id: `${movement.reference_number}-${movement.direction}`,
    title:
      movement.description?.trim() ||
      counterparty ||
      (isIncome ? 'Gelen Transfer' : 'Giden Transfer'),
    date: formatMovementDate(movement.created_at),
    amount: movement.amount,
    type: isIncome ? 'income' : 'expense',
    category: 'Transfer',
    icon: isIncome ? '💰' : '💸',
  }
}

export interface BankingContextType {
  data: BankingData;
  /** Hesap kimliğine göre o hesabın hareketleri. */
  transactionsByAccountId: Record<string, BankTransaction[]>;
  handleAccountCreate: (currency: string, type: 'checking' | 'savings' | 'foreign_currency', accountName: string, iban: string) => void;
  handleAccountClose: (accountId: string) => void;
  handleCardCreate: (type: 'credit' | 'debit', brand: 'mastercard' | 'visa', limit: number, isDigital: boolean, customName: string, linkedAccountId?: string) => void;
  updateCard: (cardId: string, updates: CreditCardUpdate) => void;
  /**
   * Transferi backend'e gönderir.
   *
   * Reddedilirse (yetersiz bakiye, kapalı hesap, aynı hesap) hata fırlatır ve
   * mesajı backend'in Türkçe gerekçesidir. Çağıran başarıyı beklemeden
   * "işleminiz alınmıştır" göstermemeli.
   */
  handleTransfer: (amount: number, fromAccountId: string, toIban: string, description: string) => Promise<void>;
  handleBillPay: (billId: string) => void;
  openCloseAccountModal: (accountId: string) => void;
  openFeatureNotReadyModal: (featureName: string) => void;
  openBillPaymentModal: () => void;
}

export default function Banking() {
  const [data, setData] = useState<BankingData | null>(null)
  const [transactionsByAccountId, setTransactionsByAccountId] = useState<Record<string, BankTransaction[]>>({})
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  // Modal states
  const [closeAccountState, setCloseAccountState] = useState<{ isOpen: boolean, accountId?: string }>({ isOpen: false })
  const [isBillModalOpen, setIsBillModalOpen] = useState(false)
  const [notReadyModalState, setNotReadyModalState] = useState<{ isOpen: boolean, featureName: string }>({ isOpen: false, featureName: '' })

  /**
   * Hesapları ve her hesabın hareketlerini backend'den çeker.
   *
   * Kartlar, faturalar, krediler ve kayıtlı alıcılar hâlâ mock: bu dördünün
   * backend'de karşılığı yok. Gerçek olanla sahte olanı tek nesnede
   * birleştirmek, ekranların hangisini kullandığını bilmek zorunda kalmadan
   * çalışmasını sağlıyor.
   */
  const loadBanking = useCallback(async () => {
    const apiAccounts = await apiClient.getBankAccounts()

    // Hareketler hesap hesap çekiliyor; tek bir "tüm hareketlerim" ucu yok.
    const statements = await Promise.all(
      apiAccounts.map((account) =>
        apiClient.getStatement(account.account_number, STATEMENT_LIMIT),
      ),
    )

    const accounts = apiAccounts.map(toUiAccount)
    const byAccount: Record<string, BankTransaction[]> = {}
    apiAccounts.forEach((account, index) => {
      byAccount[account.id] = (statements[index].movements ?? []).map(toUiTransaction)
    })

    // Birleşik liste en yeniden eskiye. Hesap bazında gelen listeler zaten
    // sıralı ama hesapları uç uca eklemek sırayı bozar, o yüzden ham tarihe
    // göre yeniden sıralanıyor.
    const merged = apiAccounts
      .flatMap((account, index) =>
        (statements[index].movements ?? []).map((movement) => ({
          at: new Date(movement.created_at).getTime(),
          tx: toUiTransaction(movement),
          accountId: account.id,
        })),
      )
      .sort((a, b) => b.at - a.at)
      .map((entry) => entry.tx)

    setTransactionsByAccountId(byAccount)
    setData({
      ...MOCK_BANKING_DATA,
      accounts,
      recentTransactions: merged,
      totalAssets: accounts.reduce((sum, account) => sum + account.balance, 0),
    })
  }, [])

  useEffect(() => {
    let cancelled = false

    loadBanking()
      .catch((error: unknown) => {
        if (cancelled) return
        setLoadError(error instanceof Error ? error.message : 'Bilinmeyen hata')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [loadBanking])

  // Action Handlers

  /**
   * Hesap açma — henüz yalnızca ekranda.
   *
   * Backend'de hesap açma ucu yok; bu yüzden yaratılan hesap sadece bu
   * bileşenin state'inde yaşıyor ve bir sonraki veri tazelemesinde (örneğin
   * transfer sonrası) kaybolur. Uç eklenene kadar bilinen bir eksik.
   */
  const handleAccountCreate = (currency: string, type: 'checking' | 'savings' | 'foreign_currency', accountName: string, iban: string) => {
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

  /** Hesap kapatma — `handleAccountCreate` ile aynı sebeple kalıcı değil. */
  const handleAccountClose = (accountId: string) => {
    if (!data) return
    const accountToClose = data.accounts.find(a => a.id === accountId)
    if (!accountToClose) return

    const updatedAccounts = data.accounts.filter(a => a.id !== accountId)

    setData({
      ...data,
      accounts: updatedAccounts,
      totalAssets: data.totalAssets - accountToClose.balance
    })
  }

  const handleCardCreate = (type: 'credit' | 'debit', brand: 'mastercard' | 'visa', limit: number, isDigital: boolean, customName: string, linkedAccountId?: string) => {
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

  // A card created before settings existed has none, so the merge needs a
  // floor -- otherwise toggling one flag yields an object missing the other
  // two, which is not a valid CardSettings.
  const DEFAULT_CARD_SETTINGS: CardSettings = {
    onlineShopping: true,
    contactless: true,
    isFrozen: false,
  }

  const updateCard = (cardId: string, updates: CreditCardUpdate) => {
    if (!data) return

    // Deep merge for settings
    const updatedCards = data.creditCards.map(c => {
      if (c.id === cardId) {
        return {
          ...c,
          ...updates,
          settings: {
            ...DEFAULT_CARD_SETTINGS,
            ...c.settings,
            ...(updates.settings ?? {}),
          }
        }
      }
      return c
    })

    setData({ ...data, creditCards: updatedCards })
  }

  /**
   * Transferi backend'e yaptırır, sonra veriyi yeniden çeker.
   *
   * Bakiyeyi burada elle düşmüyoruz: ücret backend'de hesaplanıyor (kendi
   * hesapları arasında sıfır, dışarıya 2,50) ve yerel bir çıkarma işlemi o
   * ücreti görmediği için ekrandaki bakiye ile defterdeki bakiye ayrışırdı.
   * Tazeleme, tek doğru kaynağı defter yapıyor.
   */
  const handleTransfer = async (amount: number, fromAccountId: string, toIban: string, description: string) => {
    const source = data?.accounts.find(a => a.id === fromAccountId)

    await apiClient.createTransfer({
      // Backend IBAN'ı boşluklu da kabul ediyor ama gereksiz yere
      // göndermiyoruz; gösterim biçimi burada bitiyor.
      source: source ? source.accountNumber.replace(/\s+/g, '') : null,
      destination: toIban.replace(/\s+/g, ''),
      amount,
      description: description || null,
    })

    await loadBanking()
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

  if (!data) {
    return (
      <div className="p-6 sm:p-8 min-h-screen">
        <h1 className="text-2xl font-bold tracking-tight text-white">Banka İşlemleri</h1>
        <p className="mt-4 text-slate-400">Verilere ulaşılamadı.</p>
        {loadError && (
          <p className="mt-2 text-sm text-rose-400">{loadError}</p>
        )}
      </div>
    )
  }

  const contextValue: BankingContextType = {
    data,
    transactionsByAccountId,
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
