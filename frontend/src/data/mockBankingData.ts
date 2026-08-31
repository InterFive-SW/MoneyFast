export interface BankAccount {
  id: string
  name: string
  /** `investment` is the yatırım account. Its balance lives in
   *  `investment_accounts.cash_balance`, not in banking — but it spends and
   *  receives like an account, so it is one here. */
  type: 'checking' | 'savings' | 'foreign_currency' | 'investment'
  balance: number
  currency: string
  accountNumber: string
  /** Vadeli hesabın saklanan yıllık oranı ve vadesi; vadesizde tanımsız.
   *  Ekranda bir dönem `%42.50` / `32 Gün` diye sabit yazılıydı. */
  interestRate?: number | null
  termDays?: number | null
}

export interface CreditCard {
  id: string
  name: string
  brand: 'mastercard' | 'visa'
  cardNumber: string
  limit: number
  currentDebt: number
  availableLimit: number
  dueDate: string
  color: string
  isDigital?: boolean
  settings?: CardSettings
  linkedAccountId?: string
}

export interface CardSettings {
  onlineShopping: boolean
  contactless: boolean
  isFrozen: boolean
}

/** What `updateCard` accepts: any field, and settings one flag at a time. */
export type CreditCardUpdate =
  Partial<Omit<CreditCard, 'settings'>> & { settings?: Partial<CardSettings> }

export interface SavedContact {
  id: string
  name: string
  iban: string
  avatarInitials: string
  avatarColor: string
}

export interface BankTransaction {
  id: string
  title: string
  date: string
  amount: number
  type: 'income' | 'expense'
  category: string
  icon: string
}

export interface Bill {
  id: string
  institution: string
  type: 'water' | 'electricity' | 'internet' | 'phone'
  amount: number
  dueDate: string
  status: 'pending' | 'paid' | 'overdue'
}

export interface Loan {
  id: string
  title: string
  remainingAmount: number
  totalAmount: number
  nextInstallmentAmount: number
  nextInstallmentDate: string
  remainingMonths: number
  progressPercentage: number
}

export interface BankingData {
  accounts: BankAccount[]
  creditCards: CreditCard[]
  savedContacts: SavedContact[]
  recentTransactions: BankTransaction[]
  bills: Bill[]
  loans: Loan[]
  totalAssets: number
}

export const MOCK_BANKING_DATA: BankingData = {
  totalAssets: 182500.50,
  accounts: [
    {
      id: 'acc-1',
      name: 'Vadesiz Maaş Hesabı',
      type: 'checking',
      balance: 12500.50,
      currency: 'TRY',
      accountNumber: 'TR12 0006 2000 0001 2345 67'
    },
    {
      id: 'acc-2',
      name: 'Dolar Hesabı',
      type: 'foreign_currency',
      balance: 1200.00,
      currency: 'USD',
      accountNumber: 'TR12 0006 2000 0001 2345 88'
    },
    {
      id: 'acc-3',
      name: 'Birikim Hesabı',
      type: 'savings',
      balance: 130000.00,
      currency: 'TRY',
      accountNumber: 'TR12 0006 2000 0009 8765 43'
    }
  ],
  creditCards: [
    {
      id: 'cc-1',
      name: 'MoneyFast Platinum',
      brand: 'mastercard',
      cardNumber: '**** **** **** 4582',
      limit: 100000,
      currentDebt: 32450.75,
      availableLimit: 67549.25,
      dueDate: '2026-08-25',
      color: 'from-slate-800 to-slate-900'
    },
    {
      id: 'cc-2',
      name: 'Seyahat Kartı',
      brand: 'visa',
      cardNumber: '**** **** **** 9012',
      limit: 50000,
      currentDebt: 8200.00,
      availableLimit: 41800.00,
      dueDate: '2026-08-28',
      color: 'from-blue-900 to-brandBlue'
    }
  ],
  savedContacts: [
    { id: 'c-1', name: 'Mustafa', iban: 'TR11...', avatarInitials: 'M', avatarColor: 'bg-emerald-500' },
    { id: 'c-2', name: 'Şevval', iban: 'TR22...', avatarInitials: 'Ş', avatarColor: 'bg-purple-500' },
    { id: 'c-3', name: 'Burak', iban: 'TR33...', avatarInitials: 'B', avatarColor: 'bg-blue-500' },
    { id: 'c-4', name: 'Ev Sahibi', iban: 'TR44...', avatarInitials: 'E', avatarColor: 'bg-amber-500' }
  ],
  recentTransactions: [
    { id: 'tx-1', title: 'Migros Sanal Market', date: 'Bugün', amount: 850.40, type: 'expense', category: 'Market', icon: '🛒' },
    { id: 'tx-2', title: 'Mustafa (Gelen Transfer)', date: 'Dün', amount: 2500.00, type: 'income', category: 'Transfer', icon: '💸' },
    { id: 'tx-3', title: 'Netflix', date: '17 Ağu', amount: 149.99, type: 'expense', category: 'Abonelik', icon: '🎬' },
    { id: 'tx-4', title: 'Shell Akaryakıt', date: '16 Ağu', amount: 1200.00, type: 'expense', category: 'Ulaşım', icon: '⛽' },
    { id: 'tx-5', title: 'Şevval (Kira)', date: '15 Ağu', amount: 8000.00, type: 'expense', category: 'Transfer', icon: '🏠' }
  ],
  bills: [
    { id: 'b-1', institution: 'İSKİ Su', type: 'water', amount: 245.50, dueDate: '2026-08-20', status: 'pending' },
    { id: 'b-2', institution: 'EnerjiSA Elektrik', type: 'electricity', amount: 840.00, dueDate: '2026-08-22', status: 'pending' },
    { id: 'b-3', institution: 'Superonline', type: 'internet', amount: 350.00, dueDate: '2026-08-25', status: 'pending' }
  ],
  loans: [
    { 
      id: 'l-1', 
      title: 'İhtiyaç Kredisi', 
      remainingAmount: 45000.00, 
      totalAmount: 100000.00,
      nextInstallmentAmount: 5200.00,
      nextInstallmentDate: '2026-09-05',
      remainingMonths: 9,
      progressPercentage: 55
    }
  ]
}
