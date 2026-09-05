import { useState, useEffect, useCallback, useRef } from 'react'
import { Outlet, useSearchParams } from 'react-router-dom'
import { MOCK_BANKING_DATA } from '../data/mockBankingData'
import type {
  BankingData, BankAccount, BankTransaction, CreditCardUpdate,
} from '../data/mockBankingData'
import { apiClient } from '../api/client'
import { formatDate, istanbulDayDiff } from '../lib/datetime'
import { BASE_CURRENCY, convert } from '../lib/money'
import { useMarketStream } from '../hooks/useMarketStream'
import type { Movement, PortfolioAccount } from '../api/client'

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
  yatirim: 'Yatırım Hesabı',
}

/**
 * Hesap toplamı, hepsi taban para birimine çevrilerek.
 *
 * Ham `sum + balance` idi. Bugün her hesap TRY olduğu için bu görünmüyor ama
 * `toUiAccountType` TRY olmayan hesabı açıkça `foreign_currency` diye
 * etiketliyor: arayüz o durumu bekliyor, yani 100 USD + 100 TRY = 200 yazacak
 * bir toplam bekleniyor demek. Kuru bilinmeyen hesap toplama KATILMAZ; 1.0
 * varsaymak uydurma bir kur, dolayısıyla uydurma bir toplam üretir.
 */
function totalInBase(
  accounts: BankAccount[],
  rates: Record<string, number>,
): number {
  return accounts.reduce((sum, account) => {
    const converted = convert(account.balance, account.currency, BASE_CURRENCY, rates)
    return converted == null ? sum : sum + converted
  }, 0)
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
  // The investment account is named before currency: it is the one you fund
  // to trade, and that is what distinguishes it, not what it is denominated in.
  if (apiType === 'yatirim') return 'investment'
  if (currencyCode !== 'TRY') return 'foreign_currency'
  if (apiType === 'vadeli' || apiType === 'birikim') return 'savings'
  return 'checking'
}

/** IBAN'ı dörtlü gruplara ayırır: TR000001212962... -> "TR00 0001 2129 62...". */
function formatIban(iban: string): string {
  return (iban || '').replace(/\s+/g, '').replace(/(.{4})/g, '$1 ').trim()
}

function toUiAccount(account: PortfolioAccount): BankAccount {
  return {
    id: account.id,
    // Kullanıcının verdiği ad varsa o; yoksa türden türetilen etiket.
    // Adı olmayan hesaba ad UYDURULMUYOR -- listede türü yazıyor.
    name: account.nickname || ACCOUNT_TYPE_LABELS[account.account_type] || 'Hesap',
    type: toUiAccountType(account.account_type, account.currency_code),
    interestRate: account.interest_rate,
    termDays: account.term_days,
    balance: account.balance,
    currency: account.currency_code,
    // The investment account has no IBAN -- it is not a banking row. Its own
    // account number is what a transfer addresses it by.
    accountNumber: account.iban ? formatIban(account.iban) : account.account_number,
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

  // Gün farkı ANKARA'nın takvimine göre. Eskiden `getFullYear()/getMonth()/
  // getDate()` ile tarayıcının günü okunuyordu: aynı fonksiyonun son satırı
  // Istanbul yardımcısını kullanırken ilk yarısı tarayıcıyı kullanıyor,
  // yani "Bugün" ile altındaki tarih üç saatlik bir pencerede çelişiyordu.
  const dayDiff = istanbulDayDiff(date)

  if (dayDiff === 0) return 'Bugün'
  if (dayDiff === 1) return 'Dün'
  return formatDate(date, { day: 'numeric', month: 'short' })
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
  /** Hesabı backend'de açar ve defteri yeniden okur. Reddedilirse fırlatır. */
  handleAccountCreate: (currency: string, type: 'checking' | 'savings' | 'foreign_currency', accountName?: string) => Promise<void>;
  /** Hesabı kapatır. Bakiyesi olan hesabı backend reddeder. */
  handleAccountClose: (accountId: string) => Promise<void>;
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
  /** Faturayı hazırlar, onaylar ve defteri yeniden okur. */
  handleBillPay: (institution: string, subscriberNo: string) => Promise<unknown>;
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
  // `?pay=1` opens bill payment straight away, so the dashboard's "Ödeme Yap"
  // lands on the form rather than on the banking menu. Read once at mount:
  // re-reading would reopen the modal every time the user closed it.
  const [searchParams, setSearchParams] = useSearchParams()
  const [isBillModalOpen, setIsBillModalOpen] = useState(
    () => searchParams.get('pay') === '1',
  )
  const [notReadyModalState, setNotReadyModalState] = useState<{ isOpen: boolean, featureName: string }>({ isOpen: false, featureName: '' })

  /**
   * Hesapları ve her hesabın hareketlerini backend'den çeker.
   *
   * Hesaplar, hareketler, kartlar, krediler ve faturalar gerçek. Geriye
   * `MOCK_BANKING_DATA`'dan yalnızca kayıtlı alıcı listesi kalıyor; onu da
   * Kayıtlı İşlemler ekranı gerçek veriyle gösteriyor.
   */
  const { rates: liveRates } = useMarketStream()
  const ratesRef = useRef<Record<string, number>>({})
  ratesRef.current = liveRates

  const loadBanking = useCallback(async () => {
    // Every account money can move between, including Yatırım. Loading only
    // the banking rows is why "para gönder" had nowhere to send: the
    // investment account was invisible to the transfer screen.
    const apiAccounts = await apiClient.getAllAccounts()
    // Kurlar uygulamanın paylaşılan piyasa akışından; ikinci bir kur
    // tablosu tutmak, iki ekranın aynı hesabı farklı toplamayla
    // göstermesi demek olurdu.
    const rates = ratesRef.current

    // Kartlar ve krediler artık gerçek: ikisi de kendi tablolarından geliyor.
    // Türetilen değerler (kullanılabilir limit, ilerleme) backend'de okuma
    // anında hesaplanıyor, saklanmıyor.
    const [apiCards, apiLoans] = await Promise.all([
      apiClient.getCards().catch(() => []),
      apiClient.getLoans().catch(() => []),
    ])

    // Hareketler hesap hesap çekiliyor; tek bir "tüm hareketlerim" ucu yok.
    //
    // Yatırım hesabının dökümü ayrı bir uçtan geliyor: nakdi `banking.accounts`
    // değil `investment.investment_accounts` tutuyor, dolayısıyla hareketleri
    // de kendi defterinde (migration 0017). Bir dönem bu hesap listeden
    // tamamen çıkarılıyordu — ekstresi olmadığı için istemek 404 dönüyor, tek
    // bir reddedilen istek `Promise.all`'u düşürüyor ve sayfanın tamamı
    // "Verilere ulaşılamadı" ekranına kalıyordu. Artık çıkarmak gerekmiyor:
    // hesap kendi hareketlerini anlatabiliyor.
    const statementAccounts = apiAccounts
    const statements = await Promise.all(
      statementAccounts.map((account) =>
        account.is_investment
          ? apiClient.getInvestmentStatement(
              account.iban || account.account_number,
              STATEMENT_LIMIT,
            )
          : apiClient.getStatement(account.account_number, STATEMENT_LIMIT),
      ),
    )

    const accounts = apiAccounts.map(toUiAccount)
    const byAccount: Record<string, BankTransaction[]> = {}
    statementAccounts.forEach((account, index) => {
      byAccount[account.id] = (statements[index].movements ?? []).map(toUiTransaction)
    })

    // Birleşik liste en yeniden eskiye. Hesap bazında gelen listeler zaten
    // sıralı ama hesapları uç uca eklemek sırayı bozar, o yüzden ham tarihe
    // göre yeniden sıralanıyor.
    const merged = statementAccounts
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
      creditCards: apiCards.map((card) => ({
        id: card.id,
        name: card.name,
        brand: (card.brand === 'mastercard' ? 'mastercard' : 'visa') as 'mastercard' | 'visa',
        cardNumber: card.card_number,
        limit: card.limit,
        currentDebt: card.current_debt,
        availableLimit: card.available_limit,
        dueDate: `Her ayın ${card.due_day}.`,
        color: card.color ?? 'from-slate-700 to-slate-900',
        isDigital: card.is_digital,
        settings: card.settings as never,
        linkedAccountId: card.linked_account_id ?? undefined,
      })),
      loans: apiLoans.map((loan) => ({
        id: loan.id,
        title: loan.title,
        remainingAmount: loan.remaining_amount,
        totalAmount: loan.total_amount,
        nextInstallmentAmount: loan.installment_amount,
        nextInstallmentDate: loan.next_due ?? '—',
        remainingMonths: loan.remaining_months,
        progressPercentage: loan.progress_percentage,
      })),
      accounts,
      recentTransactions: merged,
      // Para birimi çevrilmeden toplanmaz. Hesapların hepsi bugün TRY ama
      // `toUiAccountType` TRY olmayanı açıkça `foreign_currency` olarak
      // etiketliyor: arayüz bu durumu bekliyor, dolayısıyla ham toplama
      // 100 USD + 100 TRY = 200 demek olurdu. Kuru bilinmeyen hesap toplama
      // katılmaz — 1.0 varsaymak uydurma bir toplam üretir.
      totalAssets: totalInBase(accounts, rates),
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
   * Hesap açar ve defteri yeniden okur.
   *
   * Eskiden bu fonksiyon backend'e hiç gitmiyordu: rastgele bir IBAN
   * üretilip hesap yalnızca bu bileşenin state'ine yazılıyordu ve bir
   * sonraki tazelemede kayboluyordu. Hesap numarasını ve IBAN'ı artık
   * backend üretiyor -- ikisi de `unique` ve istemcinin uydurduğu bir
   * numaranın çakışmayacağının garantisi yok.
   */
  const handleAccountCreate = async (
    currency: string,
    type: 'checking' | 'savings' | 'foreign_currency',
    accountName?: string,
  ) => {
    await apiClient.openBankAccount({
      // Arayüzün sözcükleri burada çözülüyor; uç nokta veritabanının
      // kullandığı adları alıyor ve çeviri tek yerde duruyor.
      account_type: type === 'savings' ? 'vadeli' : 'vadesiz',
      currency_code: currency,
      nickname: accountName?.trim() || null,
    })
    await loadBanking()
  }

  /** Hesabı kapatır. Bakiyesi varsa backend reddeder ve gerekçesi Türkçe. */
  const handleAccountClose = async (accountId: string) => {
    const account = data?.accounts.find(a => a.id === accountId)
    if (!account) return
    await apiClient.closeBankAccount(account.accountNumber.replace(/\s+/g, ''))
    await loadBanking()
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


  /**
   * Kart ayarını backend'e yazar, sonra veriyi yeniden okur.
   *
   * Eskiden yalnızca React state'ini düzenliyordu. Kartlar mock iken bu
   * doğruydu; gerçek satır olduklarından beri dondurma ya da temassız
   * anahtarı çalışmış görünüyor, bir sonraki açılışta yok oluyordu —
   * `handleBillPay`'in yaptığı şeyin aynısı.
   *
   * Birleştirmeyi backend yapıyor: tek anahtar gönderen bir ekran
   * diğerlerini sıfırlamasın diye. Burada da birleştirseydik iki ayrı
   * "doğru" ayar kümesi olurdu.
   */
  const updateCard = async (cardId: string, updates: CreditCardUpdate) => {
    if (!data) return
    if (updates.settings) {
      await apiClient.updateCardSettings(cardId, updates.settings as Record<string, unknown>)
    }
    await loadBanking()
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

  /**
   * Faturayı gerçekten öder: hazırla, onayla, defteri yeniden oku.
   *
   * Eskiden bu fonksiyon backend'e hiç gitmiyordu. Faturayı yerelde "ödendi"
   * işaretliyor, uydurma bir hareket (`tx-new-${Date.now()}`, "Bugün") gerçek
   * defter satırlarının arasına ekliyor ve `totalAssets`'ten tutarı düşüyordu.
   * Sonuç: hiçbir hesaptan çıkmamış para ekranda çıkmış görünüyor, uydurma
   * hareket gerçeğinden ayırt edilemiyor ve ikisi de yenilemede kayboluyordu.
   *
   * On satır yukarıdaki `handleTransfer` bunun neden yanlış olduğunu zaten
   * anlatıyor; fatura yolu sadece o kurala uymuyordu.
   */
  const handleBillPay = async (institution: string, subscriberNo: string) => {
    const proposal = await apiClient.stagePayment({
      payment_type: 'BILL_PAYMENT',
      institution,
      subscriber_no: subscriberNo,
    })
    await apiClient.confirmPayment(proposal.proposal_id)
    await loadBanking()
    return proposal
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
        onClose={() => {
          setIsBillModalOpen(false)
          // Drop the parameter, or a refresh reopens a modal the user closed.
          if (searchParams.has('pay')) {
            searchParams.delete('pay')
            setSearchParams(searchParams, { replace: true })
          }
        }}
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
