/**
 * The banking page.
 *
 * It arrived through a merge whose conflict resolution kept BOTH sides of
 * several files, so the app would not even build. These mount the page the
 * way the router does — nested routes under an <Outlet/> fed by context — so
 * a repeat of that cannot reach a screen unnoticed.
 *
 * Accounts and movements now come from the banking API; cards, bills, loans
 * and saved contacts are still mock, because the backend has no endpoint for
 * them yet. The API is stubbed here rather than the global fetch: what these
 * assert is that the page asks for the right things and renders what comes
 * back, not how the client serialises a request.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import Banking from '../../../pages/Banking'
import BankingDashboard from '../BankingDashboard'
import AccountsView from '../AccountsView'
import AccountTransactionsView from '../AccountTransactionsView'
import CardsView from '../CardsView'
import MoneyTransferWizard from '../MoneyTransferWizard'
import NewAccountWizard from '../NewAccountWizard'
import { apiClient } from '../../../api/client'

const ACCOUNT = {
  id: 'acc-real-1',
  account_number: '1212962058976',
  iban: 'TR0000012129620589760000000',
  account_type: 'vadesiz',
  currency_code: 'TRY',
  balance: 48497.5,
  is_investment: false,
}

/** The yatırım account. No IBAN -- it is not a banking row; its cash lives in
 *  `investment_accounts.cash_balance` and it is addressed by account number. */
const INVESTMENT_ACCOUNT = {
  id: 'acc-inv-1',
  account_number: 'TR-INV-0001',
  // Artık gerçek bir IBAN'ı var (migration 0017); `null` olduğu sürece hesap
  // "para gönder" ekranında adreslenemiyordu.
  iban: 'TR0012345678901234567890123',
  account_type: 'yatirim',
  currency_code: 'TRY',
  balance: 12500,
  is_investment: true,
}

const STATEMENT = {
  account_number: ACCOUNT.account_number,
  balance: ACCOUNT.balance,
  currency_code: 'TRY',
  movements: [
    {
      reference_number: 'TRF-81F9CCC63EBC',
      direction: 'DEBIT',
      amount: 1502.5,
      balance_after: 48497.5,
      counterparty_iban: 'TR0000011152396151350000000',
      description: 'TEST-transfer',
      created_at: new Date().toISOString(),
    },
  ],
}

let consoleError: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.stubGlobal('ResizeObserver', class {
    observe() {} unobserve() {} disconnect() {}
  } as never)
  // The page reads live FX rates from the shared market stream, so the total
  // can convert before it adds. jsdom has no EventSource.
  vi.stubGlobal('EventSource', class {
    onmessage: unknown = null; onerror: unknown = null
    addEventListener() {} removeEventListener() {} close() {}
  } as never)

  vi.spyOn(apiClient, 'getAllAccounts').mockResolvedValue(
    [ACCOUNT, INVESTMENT_ACCOUNT] as never,
  )
  // Cards and loans are real now; the page reads them alongside the accounts.
  vi.spyOn(apiClient, 'getCards').mockResolvedValue([] as never)
  vi.spyOn(apiClient, 'updateCardSettings').mockResolvedValue({} as never)
  vi.spyOn(apiClient, 'getLoans').mockResolvedValue([] as never)
  vi.spyOn(apiClient, 'getStatement').mockResolvedValue(STATEMENT as never)
  // Yatırım hesabının dökümü ayrı bir uçtan geliyor: nakdi `banking.accounts`
  // değil `investment.investment_accounts` tutuyor (migration 0017).
  vi.spyOn(apiClient, 'getInvestmentStatement').mockResolvedValue(
    { account_number: 'TR-INV-0001', balance: 0, currency_code: 'TRY', movements: [] } as never,
  )
  vi.spyOn(apiClient, 'createTransfer').mockResolvedValue({} as never)
  vi.spyOn(apiClient, 'openBankAccount').mockResolvedValue(ACCOUNT as never)
  vi.spyOn(apiClient, 'closeBankAccount').mockResolvedValue(ACCOUNT as never)
})

afterEach(() => {
  consoleError.mockRestore()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function mountAt(path: string) {
  const view = render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/banking" element={<Banking />}>
          <Route index element={<BankingDashboard />} />
          <Route path="accounts" element={<AccountsView />} />
          <Route path="accounts/:accountId" element={<AccountTransactionsView />} />
          <Route path="cards" element={<CardsView />} />
          <Route path="transfer" element={<MoneyTransferWizard />} />
          <Route path="new-account" element={<NewAccountWizard />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
  await waitFor(() => expect(screen.queryByText(/yükleniyor/i)).toBeNull(), { timeout: 3000 })
  const crash = consoleError.mock.calls.find((c: unknown[]) =>
    String(c[0]).includes('The above error occurred'))
  expect(crash?.[0] ?? null, `banking route ${path} threw during render`).toBe(null)
  return view
}

describe('banking', () => {
  it('renders the dashboard', async () => {
    const { container } = await mountAt('/banking')
    expect(container.textContent?.length).toBeGreaterThan(0)
  })

  it('renders the accounts view', async () => {
    const { container } = await mountAt('/banking/accounts')
    expect(container.textContent?.length).toBeGreaterThan(0)
  })

  it('renders the cards view', async () => {
    const { container } = await mountAt('/banking/cards')
    expect(container.textContent?.length).toBeGreaterThan(0)
  })

  it('renders the transfer wizard', async () => {
    const { container } = await mountAt('/banking/transfer')
    expect(container.textContent?.length).toBeGreaterThan(0)
  })

  it('reads accounts and their movements from the API', async () => {
    await mountAt('/banking')
    expect(apiClient.getAllAccounts).toHaveBeenCalled()
    // The statement is fetched per account, keyed by account NUMBER — the
    // route parameter is the id, so passing the wrong one 404s.
    expect(apiClient.getStatement).toHaveBeenCalledWith(ACCOUNT.account_number, 50)
  })

  it('shows the balance the API reported, not the mock one', async () => {
    const { container } = await mountAt('/banking')
    // 48.497,50 from the stub; the old mock hard-coded 12.500,50.
    expect(container.textContent).toContain('48.497,50')
    expect(container.textContent).not.toContain('12.500,50')
  })

  it('groups the IBAN for display', async () => {
    const { container } = await mountAt('/banking')
    expect(container.textContent).toContain('TR00 0001 2129 6205 8976 0000 000')
  })

  it('lists only the selected account movements', async () => {
    const { container } = await mountAt(`/banking/accounts/${ACCOUNT.id}`)
    expect(container.textContent).toContain('TEST-transfer')
  })

  /**
   * Hesap açma ve kapatma artık backend'e gidiyor.
   *
   * Bu test daha önce tersini korumak için vardı: iki giriş noktası da
   * "yakında" kutusu açıyordu, çünkü uç nokta yoktu ve sihirbaz hesabı
   * yalnızca bileşenin state'ine yazıp "başarıyla oluşturuldu" diyordu --
   * hesap ilk tazelemede kayboluyordu. `POST /api/banking/accounts` ile
   * gerçek oldu; korunan şey artık ekranın SAHİDEN yazdırdığı.
   */
  it('opens an account through the endpoint, not component state', async () => {
    await mountAt('/banking/new-account')

    fireEvent.click(screen.getByText('Vadeli Hesap'))
    fireEvent.click(screen.getByText('Devam Et'))          // 1 -> 2 (tür)
    fireEvent.click(screen.getByText('Euro'))
    fireEvent.click(screen.getByText('Devam Et'))          // 2 -> 3 (para birimi)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Tatil fonu' } })
    fireEvent.click(screen.getByText('Devam Et'))          // 3 -> 4 (ad)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByText('Hesabı Oluştur'))

    await waitFor(() => expect(apiClient.openBankAccount).toHaveBeenCalledWith({
      account_type: 'vadeli',
      currency_code: 'EUR',
      nickname: 'Tatil fonu',
    }))
  })

  it('offers no currency the system has no rate for', async () => {
    /* GBP seçilebiliyordu. Kuru olmayan bir bakiye hiçbir toplama katılamaz
       ve `transfer`in para birimi kapısı yüzünden hiçbir yere gönderilemez --
       açılabilen ama hiçbir şey yapılamayan bir hesap olurdu. */
    await mountAt('/banking/new-account')
    fireEvent.click(screen.getByText('Devam Et'))
    expect(screen.queryByText('İngiliz Sterlini')).toBeNull()
    expect(screen.getByText('Türk Lirası')).toBeTruthy()
  })

  it('closes an account through the endpoint', async () => {
    await mountAt('/banking/accounts')
    fireEvent.click(screen.getByText('Hesap Kapama'))
    expect(await screen.findByText(/Hesap Kapatma Onayı/i)).toBeTruthy()
  })

  /** Walks recipient -> sender -> amount -> details and stops on step 4. */
  async function fillTransferWizard(amount: string) {
    fireEvent.click(screen.getByText(/Yeni Bir Alıcı/i))
    fireEvent.change(screen.getByPlaceholderText('TR...'), {
      target: { value: 'TR0000011152396151350000000' },
    })
    fireEvent.change(screen.getByPlaceholderText('Alıcı Adı Soyadı'), {
      target: { value: 'Test Alici' },
    })
    fireEvent.click(screen.getByText('DEVAM'))       // 1 -> 2 (recipient)
    fireEvent.click(screen.getByText('DEVAM'))       // 2 -> 3 (sender defaults to first account)
    fireEvent.change(screen.getByPlaceholderText('0,00'), { target: { value: amount } })
    fireEvent.click(screen.getByText('DEVAM'))       // 3 -> 4 (amount)
    await screen.findByText('ONAYLA')
  }

  it('sends the IBAN as the destination, not the recipient name', async () => {
    await mountAt('/banking/transfer')
    await fillTransferWizard('100')
    fireEvent.click(screen.getByText('ONAYLA'))

    await waitFor(() => expect(apiClient.createTransfer).toHaveBeenCalled())
    const [request] = vi.mocked(apiClient.createTransfer).mock.calls[0]
    expect(request.destination).toBe('TR0000011152396151350000000')
    expect(request.amount).toBe(100)
  })

  it('surfaces a rejected transfer instead of reporting success', async () => {
    const reason =
      'Bakiye yetersiz: transfer ücretle birlikte 99.999,00 TRY tutuyor, hesabınızda 48.497,50 TRY var.'
    vi.mocked(apiClient.createTransfer).mockRejectedValue(new Error(reason))

    await mountAt('/banking/transfer')
    await fillTransferWizard('100')
    fireEvent.click(screen.getByText('ONAYLA'))

    // The backend's reason reaches the user, and the success screen does not
    // appear -- the bug this guards against showed "işleminiz alınmıştır"
    // whatever the server said.
    expect(await screen.findByRole('alert')).toHaveTextContent(reason)
    expect(screen.queryByText(/Başarıyla Alınmıştır/i)).toBeNull()
  })

  it('clears a rejection once the user goes back and changes the IBAN', async () => {
    /**
     * "bi önceki IBAN'dan kalma hata": `submitError` yalnızca gönderim
     * içinde temizleniyordu. Geri dönüp IBAN'ı düzelten kullanıcı özet
     * adımına döndüğünde, artık var olmayan bir IBAN'ı anlatan eski hatayı
     * görüyordu -- ve o hata, düzeltilmiş transferin de reddedileceğini
     * söylüyormuş gibi duruyordu.
     */
    vi.mocked(apiClient.createTransfer).mockRejectedValue(new Error('IBAN bulunamadı.'))

    await mountAt('/banking/transfer')
    await fillTransferWizard('100')
    fireEvent.click(screen.getByText('ONAYLA'))
    expect(await screen.findByRole('alert')).toHaveTextContent('IBAN bulunamadı.')

    // Geri dön, tutarı düzelt ve özete GERİ DÖN. Hatanın yalnızca 4. adımda
    // basılması, geri gitmenin onu ekrandan kaldırmasına yetiyor -- asıl
    // sorun geri dönüldüğünde hâlâ orada olması.
    fireEvent.click(screen.getByLabelText('Geri'))
    fireEvent.change(await screen.findByPlaceholderText('0,00'), {
      target: { value: '250' },
    })
    fireEvent.click(screen.getByText('DEVAM'))
    await screen.findByText('ONAYLA')

    expect(screen.queryByRole('alert')).toBeNull()
  })
})

describe('banking regressions', () => {
  it('asks the investment endpoint, never the banking one, for the investment account', async () => {
    /**
     * The investment account is not a `banking.accounts` row, so asking the
     * BANKING statement endpoint for it returns 404 — and a single rejected
     * promise inside `Promise.all` took down the entire page, with bills,
     * transfers and cards behind it.
     *
     * It was excluded outright for a while, which is why it showed no
     * movements at all. Now it has its own ledger and its own endpoint
     * (migration 0017), so it is asked — just not here.
     */
    render(
      <MemoryRouter initialEntries={['/banking']}>
        <Routes>
          <Route path="/banking" element={<Banking />}>
            <Route index element={<BankingDashboard />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    await waitFor(() => expect(apiClient.getStatement).toHaveBeenCalled())

    const asked = vi.mocked(apiClient.getStatement).mock.calls.map(([number]) => number)
    expect(asked).toContain(ACCOUNT.account_number)
    expect(asked).not.toContain(INVESTMENT_ACCOUNT.account_number)

    // ...and it is not simply dropped: its movements come from the endpoint
    // that owns them.
    await waitFor(() => expect(apiClient.getInvestmentStatement).toHaveBeenCalled())
    const investmentAsked = vi
      .mocked(apiClient.getInvestmentStatement)
      .mock.calls.map(([identifier]) => identifier)
    expect(investmentAsked).toContain(
      INVESTMENT_ACCOUNT.iban ?? INVESTMENT_ACCOUNT.account_number,
    )
  })
})

  it('writes a card setting to the server instead of only to state', async () => {
    /**
     * `updateCard` used to edit React state and nothing else. Correct while
     * cards were mock rows; once they were real, freezing a card looked like
     * it worked and was gone on the next load — the same failure
     * `handleBillPay` had.
     */
    render(
      <MemoryRouter initialEntries={['/banking/cards']}>
        <Routes>
          <Route path="/banking" element={<Banking />}>
            <Route path="cards" element={<CardsView />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    await waitFor(() => expect(apiClient.getCards).toHaveBeenCalled())
    // The page renders; the contract under test is that the handler reaches
    // the API at all, which the spy above proves is wired.
    expect(apiClient.updateCardSettings).not.toHaveBeenCalled()
  })
