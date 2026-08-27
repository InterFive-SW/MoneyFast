/**
 * Every dashboard widget, mounted against real API payloads.
 *
 * The hook suite covered the data layer and still reported 100%, but no
 * component was ever mounted -- so a widget that threw on its second render
 * blanked the entire app without a single test going red. React unmounts the
 * whole root when a render throws, which is why one bad widget takes the page
 * with it rather than just its own card.
 *
 * The `empty` scenario is the one that matters: a freshly registered user gets
 * `points: []`, `categories: []`, `[]` from every banking endpoint, and that is
 * precisely the shape that indexing `coords[0]` blows up on.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import payloads from './payloads.json'

const POPULATED = payloads as Record<string, unknown>

/** Same endpoints, but every collection drained -- a brand-new account. */
function emptied(value: unknown): unknown {
  if (Array.isArray(value)) return []
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, emptied(v)]),
    )
  }
  return value
}
const EMPTY = Object.fromEntries(
  Object.entries(POPULATED).map(([k, v]) => [k, emptied(v)]),
)

function stubFetch(table: Record<string, unknown>) {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const path = String(url).split('?')[0]
    const body = table[path] ?? (path.includes('instruments') ? { instruments: [] } : [])
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) })
  }))
}

let consoleError: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  // Installed per test and torn down unconditionally: a widget that throws
  // aborts the test body, so restoring inline would leak React's async error
  // log into whichever test ran next.
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.stubGlobal('EventSource', class {
    onmessage: unknown = null; onerror: unknown = null
    addEventListener() {} removeEventListener() {} close() {}
  } as never)
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

/** Widgets that size themselves from the grid need the props Dashboard passes. */
const SIZED = new Set(['PortfolioChartWidget', 'ProfitLossHeatmapWidget'])
const PROPS: Record<string, Record<string, unknown>> = {
  MiniTickerWidget: { symbol: 'USDTRY', label: 'USD/TRY' },
}

const WIDGETS = [
  'AssetAllocationWidget', 'DividendCalendarWidget', 'InvestmentBalanceWidget',
  'MarketTickerWidget', 'MiniTickerWidget', 'NewsWidget', 'OrderHistoryWidget',
  'PortfolioChartWidget', 'PositionsWidget', 'ProfitLossHeatmapWidget',
  'QuickActionsWidget', 'RecentTransactionsWidget', 'RiskSummaryWidget',
  'SavingsGoalWidget',
  'SectorAllocationWidget', 'SpendingOverviewWidget', 'TopMoversWidget',
  'TotalBalanceWidget', 'WatchlistWidget',
]

describe.each([
  ['populated', POPULATED],
  ['empty (new account)', EMPTY],
])('widgets render against %s payloads', (_label, table) => {
  for (const name of WIDGETS) {
    it(name, async () => {
      stubFetch(table)
      const mod = await import(`../${name}.tsx`)
      const props = { ...(PROPS[name] ?? {}), ...(SIZED.has(name) ? { w: 8, h: 5 } : {}) }
      const { container } = render(
        <MemoryRouter>{/* eslint-disable-next-line */}
          <mod.default {...props} />
        </MemoryRouter>,
      )
      // Let the fetch settle: the crash we are guarding against happens on the
      // re-render after data arrives, not on the first paint.
      await waitFor(() => expect(container).toBeTruthy())
      await new Promise((r) => setTimeout(r, 80))

      const crash = consoleError.mock.calls.find((c: unknown[]) =>
        String(c[0]).includes('The above error occurred'))
      expect(crash?.[0] ?? null, `${name} threw during render`).toBe(null)
    })
  }
})
