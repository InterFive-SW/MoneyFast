/**
 * The Risk page, mounted against a real /api/risk/profile payload — and
 * against the empty-shaped one a brand-new account produces.
 *
 * The page previously read a fixture, so every widget was guaranteed a
 * complete object with a number in every field. Now the score, the level and
 * the savings rate can each legitimately be null, and each of those is a
 * different way for a component to crash on render.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import payloads from '../../widgets/__tests__/payloads.json'

import Risk from '../../../pages/Risk'

const PROFILE = (payloads as Record<string, any>)['/api/risk/profile']

/** What the endpoint returns for someone with no positions and no ledger. */
const EMPTY = {
  as_of: new Date().toISOString(),
  score: null,
  level: null,
  components: [
    { name: 'volatility', measured: null, weight: 45, penalty: null },
    { name: 'concentration', measured: null, weight: 35, penalty: null },
    { name: 'drawdown', measured: null, weight: 20, penalty: null },
  ],
  findings: [],
  suggestions: [],
  cashflow: {
    period: 'Son 30 gün', currency_code: 'TRY',
    monthly_income: 0, monthly_expense: 0, savings_rate: null,
  },
  metrics: {},
  position_count: 0,
  warnings: ['Portföyünüzde değerlenebilir pozisyon bulunamadı.'],
}

let consoleError: ReturnType<typeof vi.spyOn>

function stubFetch(body: unknown, ok = true) {
  vi.stubGlobal('fetch', vi.fn(() =>
    Promise.resolve({ ok, status: ok ? 200 : 500, json: () => Promise.resolve(body) }),
  ))
}

beforeEach(() => {
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.stubGlobal('ResizeObserver', class {
    observe() {} unobserve() {} disconnect() {}
  } as never)
  localStorage.setItem('access_token', 'test-token')
})
afterEach(() => {
  consoleError.mockRestore()
  vi.unstubAllGlobals()
  localStorage.clear()
})

async function mount() {
  const view = render(<MemoryRouter><Risk /></MemoryRouter>)
  await waitFor(() => expect(view.container).toBeTruthy())
  await new Promise((r) => setTimeout(r, 80))
  const crash = consoleError.mock.calls.find((c: unknown[]) =>
    String(c[0]).includes('The above error occurred'))
  expect(crash?.[0] ?? null, 'Risk page threw during render').toBe(null)
  return view
}

describe('Risk page', () => {
  it('renders a scored profile', async () => {
    stubFetch(PROFILE)
    const { container } = await mount()
    expect(container.textContent).toContain('Risk Analizi')
    expect(container.textContent).toContain('Puan nasıl oluştu')
  })

  it('survives a brand-new account with nothing to measure', async () => {
    stubFetch(EMPTY)
    const { container } = await mount()
    // A dash, not a 0: zero would read as "maximum risk" for someone who
    // holds nothing at all.
    expect(container.textContent).toContain('—')
    expect(container.textContent).toContain('hesaplanamadı')
  })

  it('names what was left out instead of hiding it', async () => {
    stubFetch({ ...PROFILE, warnings: ['BERA: fiyat yok, hesaba katılmadı'] })
    const { container } = await mount()
    expect(container.textContent).toContain('BERA')
  })

  it('shows a failure message rather than a blank page', async () => {
    stubFetch({}, false)
    const { container } = await mount()
    expect(container.textContent).toContain('ulaşılamadı')
  })

  it('reports an unknown savings rate rather than 0%', async () => {
    stubFetch({
      ...PROFILE,
      cashflow: { ...PROFILE.cashflow, monthly_income: 0, savings_rate: null },
    })
    const { container } = await mount()
    expect(container.textContent).toContain('Tasarruf oranı hesaplanamadı')
  })
})
