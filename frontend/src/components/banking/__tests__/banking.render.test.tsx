/**
 * The banking demo page.
 *
 * It arrived through a merge whose conflict resolution kept BOTH sides of
 * several files, so the app would not even build. These mount the page the
 * way the router does — nested routes under an <Outlet/> fed by context — so
 * a repeat of that cannot reach a demo unnoticed.
 *
 * The page is deliberately mock-only: it reads MOCK_BANKING_DATA and calls no
 * endpoint. Wiring it to the real banking API is a later, separate job.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import Banking from '../../../pages/Banking'
import BankingDashboard from '../BankingDashboard'
import AccountsView from '../AccountsView'
import CardsView from '../CardsView'
import MoneyTransferWizard from '../MoneyTransferWizard'

let consoleError: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.stubGlobal('ResizeObserver', class {
    observe() {} unobserve() {} disconnect() {}
  } as never)
  // Any call at all would be wiring we have not done yet.
  vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('banking must not call the network'))))
})
afterEach(() => {
  consoleError.mockRestore()
  vi.unstubAllGlobals()
})

async function mountAt(path: string) {
  const view = render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/banking" element={<Banking />}>
          <Route index element={<BankingDashboard />} />
          <Route path="accounts" element={<AccountsView />} />
          <Route path="cards" element={<CardsView />} />
          <Route path="transfer" element={<MoneyTransferWizard />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
  // The page fakes an 800ms load before revealing its mock data.
  await waitFor(() => expect(screen.queryByText(/yükleniyor/i)).toBeNull(), { timeout: 3000 })
  const crash = consoleError.mock.calls.find((c: unknown[]) =>
    String(c[0]).includes('The above error occurred'))
  expect(crash?.[0] ?? null, `banking route ${path} threw during render`).toBe(null)
  return view
}

describe('banking demo', () => {
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

  it('never touches the network', async () => {
    await mountAt('/banking')
    expect(fetch).not.toHaveBeenCalled()
  })
})
