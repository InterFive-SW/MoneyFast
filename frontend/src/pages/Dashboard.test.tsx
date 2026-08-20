import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Dashboard from './Dashboard'
import { apiClient } from '../api/client'

// Bazı grid widget'ları (MiniTickerWidget, InvestmentBalanceWidget vb.) artık
// useNavigate kullanıyor — Dashboard bir <Router> içinde render edilmediği için mocklanıyor.
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

// PortfolioChartWidget uses lightweight-charts directly — jsdom has no canvas, so we
// fake the library the same way the other chart-widget test files do.
vi.mock('lightweight-charts', () => ({
  createChart: () => ({
    addSeries: () => ({ setData: () => {}, applyOptions: () => {} }),
    priceScale: () => ({ applyOptions: () => {} }),
    applyOptions: () => {},
    timeScale: () => ({ fitContent: () => {} }),
    remove: () => {},
  }),
  ColorType: { Solid: 'solid' },
  CandlestickSeries: {},
  HistogramSeries: {},
}))

function mockAllApiClientCalls() {
  vi.spyOn(apiClient, 'getPositions').mockResolvedValue([])
  vi.spyOn(apiClient, 'getOrders').mockResolvedValue([])
  vi.spyOn(apiClient, 'getWatchlist').mockResolvedValue({})
  vi.spyOn(apiClient, 'getTopMovers').mockResolvedValue({})
  vi.spyOn(apiClient, 'getDividends').mockResolvedValue([])
  vi.spyOn(apiClient, 'getSectorAllocation').mockResolvedValue([])
  vi.spyOn(apiClient, 'getHeatmap').mockResolvedValue([])
  vi.spyOn(apiClient, 'getAssetAllocation').mockResolvedValue([])
}

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
  mockAllApiClientCalls()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Dashboard — default render', () => {
  it('renders the default (investor-view) template with its widgets', async () => {
    render(<Dashboard />)
    expect(screen.getByText('Hoş Geldiniz 👋')).toBeInTheDocument()
    expect(screen.getByText('Profesyonel Trader')).toBeInTheDocument()
    await waitFor(() => expect(apiClient.getPositions).toHaveBeenCalled())
  })
})

describe('Dashboard — template switching', () => {
  it('switches to a different template via the selector dropdown', () => {
    render(<Dashboard />)
    fireEvent.click(screen.getByText('Profesyonel Trader'))
    fireEvent.click(screen.getByText('Kapsamlı Finans'))
    expect(screen.getByText('Kapsamlı Finans')).toBeInTheDocument()
  })

  it('closes the dropdown when clicking outside of it', () => {
    render(<Dashboard />)
    fireEvent.click(screen.getByText('Profesyonel Trader'))
    expect(screen.getByText('Günlük Bankacılık')).toBeInTheDocument()
    fireEvent.click(document.querySelector('.fixed.inset-0.z-10')!)
    expect(screen.queryByText('Günlük Bankacılık')).not.toBeInTheDocument()
  })
})

describe('Dashboard — edit mode', () => {
  it('toggles edit mode on and off, showing/hiding the widget palette', () => {
    render(<Dashboard />)
    expect(screen.queryByText('Widget Paleti')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('Paneli Düzenle'))
    expect(screen.getByText('🔧 Panel Düzenleme Modu')).toBeInTheDocument()
    expect(screen.getByText('Widget Paleti')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Kaydet'))
    expect(screen.queryByText('Widget Paleti')).not.toBeInTheDocument()
  })

  it('reverts the layout when Escape is pressed in edit mode', () => {
    render(<Dashboard />)
    fireEvent.click(screen.getByText('Paneli Düzenle'))
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByText('Widget Paleti')).not.toBeInTheDocument()
    expect(screen.getByText('Paneli Düzenle')).toBeInTheDocument()
  })

  it('ignores unrelated key presses and Escape outside of edit mode', () => {
    render(<Dashboard />)
    fireEvent.keyDown(window, { key: 'Escape' }) // not in edit mode: no-op
    fireEvent.click(screen.getByText('Paneli Düzenle'))
    fireEvent.keyDown(window, { key: 'a' }) // wrong key: no-op
    expect(screen.getByText('Widget Paleti')).toBeInTheDocument()
  })

  it('shows "all widgets are on screen" once every pool widget has been added', () => {
    render(<Dashboard />)
    fireEvent.click(screen.getByText('Paneli Düzenle'))

    let pool = document.querySelector('.custom-scrollbar')!
    let firstCard = pool.querySelector('[draggable="true"]')
    let guard = 0
    while (firstCard && guard < 25) {
      fireEvent.click(firstCard)
      pool = document.querySelector('.custom-scrollbar')!
      firstCard = pool.querySelector('[draggable="true"]')
      guard++
    }

    expect(screen.getByText('Tüm modüller ekranda mevcut.')).toBeInTheDocument()
  })

  it('reverts the layout when the İptal button is clicked', () => {
    render(<Dashboard />)
    fireEvent.click(screen.getByText('Paneli Düzenle'))
    fireEvent.click(screen.getByText('İptal'))
    expect(screen.queryByText('Widget Paleti')).not.toBeInTheDocument()
  })

  it('clears the whole layout with Tümünü Temizle, making all widgets available in the pool', () => {
    render(<Dashboard />)
    fireEvent.click(screen.getByText('Paneli Düzenle'))
    fireEvent.click(screen.getByText('Tümünü Temizle'))
    expect(screen.queryByText('Tüm modüller ekranda mevcut.')).not.toBeInTheDocument()
    expect(screen.getAllByText('Yatırım Hesabım').length).toBeGreaterThan(0)
  })

  it('removes a widget from the grid, adding it back to the pool', () => {
    render(<Dashboard />)
    fireEvent.click(screen.getByText('Paneli Düzenle'))

    // investment-balance is on the grid initially, so its pool preview isn't shown yet.
    expect(document.querySelector('.custom-scrollbar')?.textContent).not.toContain('Yatırım Hesabım')

    // Find its grid card specifically and click the remove ("x") button inside it.
    const card = screen.getByText('Yatırım Hesabım').closest('.group')!
    fireEvent.click(card.querySelector('button')!)

    // Removing it makes it selectable in the pool again.
    expect(screen.getAllByText('Yatırım Hesabım').length).toBeGreaterThan(0)
  })

  it('adds a widget from the pool by clicking it', () => {
    render(<Dashboard />)
    fireEvent.click(screen.getByText('Paneli Düzenle'))
    // quick-actions is not part of the default template: shown twice in the pool
    // (label + embedded live preview).
    expect(screen.getAllByText('Hızlı İşlemler').length).toBe(2)
    fireEvent.click(screen.getAllByText('Hızlı İşlemler')[0])
    // Once added it becomes a real grid widget instance (renders its own heading
    // once) and is no longer offered in the pool.
    expect(screen.getAllByText('Hızlı İşlemler').length).toBe(1)
    expect(document.querySelector('.custom-scrollbar')?.textContent).not.toContain('Hızlı İşlemler')
  })
})

// Native fireEvent.dragStart/dragOver/drop construct a real jsdom DragEvent, whose
// dataTransfer support is incomplete and hangs the test runner. The standard jsdom
// workaround is to dispatch a plain Event with a fake dataTransfer attached manually.
function dispatchDragEvent(target: Element, type: string, props: Record<string, unknown> = {}) {
  const event = new Event(type, { bubbles: true, cancelable: true })
  Object.assign(event, props)
  act(() => {
    target.dispatchEvent(event)
  })
}

describe('Dashboard — drag and drop', () => {
  it('drags a pool widget onto the grid and drops it', () => {
    render(<Dashboard />)
    fireEvent.click(screen.getByText('Paneli Düzenle'))
    const poolCard = screen.getAllByText('Hızlı İşlemler')[0].closest('[draggable="true"]')!
    const grid = document.querySelector('.react-grid-layout')!.parentElement!

    dispatchDragEvent(poolCard, 'dragstart', { dataTransfer: { setData: () => {}, effectAllowed: '' } })
    dispatchDragEvent(grid, 'dragover', { clientX: 100, clientY: 100, dataTransfer: { dropEffect: '' } })
    dispatchDragEvent(grid, 'drop', { clientX: 100, clientY: 100 })

    // Dropped: now a single real grid widget instance, no longer offered in the pool.
    expect(screen.getAllByText('Hızlı İşlemler').length).toBe(1)
    expect(document.querySelector('.custom-scrollbar')?.textContent).not.toContain('Hızlı İşlemler')
  })

  it('clears the drop preview on dragLeave when leaving the container', () => {
    render(<Dashboard />)
    fireEvent.click(screen.getByText('Paneli Düzenle'))
    const poolCard = screen.getAllByText('Hızlı İşlemler')[0].closest('[draggable="true"]')!
    const grid = document.querySelector('.react-grid-layout')!.parentElement!

    dispatchDragEvent(poolCard, 'dragstart', { dataTransfer: { setData: () => {}, effectAllowed: '' } })
    dispatchDragEvent(grid, 'dragover', { clientX: 100, clientY: 100, dataTransfer: { dropEffect: '' } })
    dispatchDragEvent(grid, 'dragleave', { relatedTarget: document.body })
    dispatchDragEvent(poolCard, 'dragend')

    expect(screen.getByText('Widget Paleti')).toBeInTheDocument() // still in edit mode, no crash
  })

  it('dragOver does nothing outside of edit mode / without a drag in progress', () => {
    render(<Dashboard />)
    const gridWrapper = document.querySelector('.react-grid-layout')!.parentElement!
    // Not in edit mode yet: should be a no-op, no crash.
    dispatchDragEvent(gridWrapper, 'dragover', { clientX: 50, clientY: 50, dataTransfer: { dropEffect: '' } })

    fireEvent.click(screen.getByText('Paneli Düzenle'))
    // In edit mode but no dragstart happened: dragTypeRef.current is still null.
    dispatchDragEvent(gridWrapper, 'dragover', { clientX: 50, clientY: 50, dataTransfer: { dropEffect: '' } })
    expect(screen.getByText('Widget Paleti')).toBeInTheDocument()
  })

  it('dragLeave does not clear the preview when staying within the container (relatedTarget is a child)', () => {
    render(<Dashboard />)
    fireEvent.click(screen.getByText('Paneli Düzenle'))
    const poolCard = screen.getAllByText('Hızlı İşlemler')[0].closest('[draggable="true"]')!
    const grid = document.querySelector('.react-grid-layout')!.parentElement!
    const child = grid.querySelector('.react-grid-layout')!

    dispatchDragEvent(poolCard, 'dragstart', { dataTransfer: { setData: () => {}, effectAllowed: '' } })
    dispatchDragEvent(grid, 'dragover', { clientX: 100, clientY: 100, dataTransfer: { dropEffect: '' } })
    dispatchDragEvent(grid, 'dragleave', { relatedTarget: child })
    expect(screen.getByText('Widget Paleti')).toBeInTheDocument() // no crash, still in edit mode
  })

  it('drop without a preceding dragstart is a no-op', () => {
    render(<Dashboard />)
    fireEvent.click(screen.getByText('Paneli Düzenle'))
    const grid = document.querySelector('.react-grid-layout')!.parentElement!
    dispatchDragEvent(grid, 'drop', { clientX: 50, clientY: 50 })
    expect(screen.getAllByText('Hızlı İşlemler').length).toBe(2) // untouched, still in the pool twice
  })

  it('dragEnd without a preceding dragstart is a no-op', () => {
    render(<Dashboard />)
    fireEvent.click(screen.getByText('Paneli Düzenle'))
    const poolCard = screen.getAllByText('Hızlı İşlemler')[0].closest('[draggable="true"]')!
    dispatchDragEvent(poolCard, 'dragend')
    expect(screen.getByText('Widget Paleti')).toBeInTheDocument()
  })

  it('mouseEnter on a pool card updates the dropping-item preview size (no crash)', () => {
    render(<Dashboard />)
    fireEvent.click(screen.getByText('Paneli Düzenle'))
    const poolCard = screen.getAllByText('Hızlı İşlemler')[0].closest('[draggable="true"]')!
    fireEvent.mouseEnter(poolCard)
    expect(screen.getByText('Widget Paleti')).toBeInTheDocument()
  })
})

describe('Dashboard — save flows', () => {
  it('opens the save-as modal, disables Kaydet for an empty name, and saves under a new name', () => {
    render(<Dashboard />)
    fireEvent.click(screen.getByText('Paneli Düzenle'))
    fireEvent.click(screen.getByText('Farklı Kaydet'))

    expect(screen.getByText('Düzeni Kaydet')).toBeInTheDocument()
    const modalSaveBtn = screen.getByText('Düzeni Kaydet').closest('div')!.parentElement!.querySelector('button.bg-brandBlue')!
    expect(modalSaveBtn).toBeDisabled()

    fireEvent.change(screen.getByPlaceholderText('Örn: Hafta Sonu Görünümü'), { target: { value: 'My Layout' } })
    expect(modalSaveBtn).not.toBeDisabled()
    fireEvent.click(modalSaveBtn)

    // Saving switches to the new template and exits edit mode.
    expect(screen.queryByText('Widget Paleti')).not.toBeInTheDocument()
    expect(screen.getByText('My Layout')).toBeInTheDocument()

    // The new custom layout is now selectable from "Kişisel Düzenlerim".
    fireEvent.click(screen.getByText('My Layout'))
    expect(screen.getByText('Kişisel Düzenlerim')).toBeInTheDocument()
  })

  it('closes the save-as modal via İptal without saving', () => {
    render(<Dashboard />)
    fireEvent.click(screen.getByText('Paneli Düzenle'))
    fireEvent.click(screen.getByText('Farklı Kaydet'))
    fireEvent.click(screen.getByText('Düzeni Kaydet').closest('div')!.parentElement!.querySelector('button:not(.bg-brandBlue)')!)
    expect(screen.queryByText('Düzeni Kaydet')).not.toBeInTheDocument()
  })

  function clickModalSave() {
    fireEvent.click(screen.getByText('Düzeni Kaydet').closest('div')!.parentElement!.querySelector('button.bg-brandBlue')!)
  }

  it('overwrites an existing custom layout with the same generated id (Date.now collision)', () => {
    const now = 1_700_000_000_000
    vi.spyOn(Date, 'now').mockReturnValue(now)

    render(<Dashboard />)
    fireEvent.click(screen.getByText('Paneli Düzenle'))
    fireEvent.click(screen.getByText('Farklı Kaydet'))
    fireEvent.change(screen.getByPlaceholderText('Örn: Hafta Sonu Görünümü'), { target: { value: 'First Save' } })
    clickModalSave()

    fireEvent.click(screen.getByText('First Save'))
    fireEvent.click(screen.getByText('Paneli Düzenle'))
    fireEvent.click(screen.getByText('Farklı Kaydet'))
    fireEvent.change(screen.getByPlaceholderText('Örn: Hafta Sonu Görünümü'), { target: { value: 'Second Save' } })
    clickModalSave()

    // Same Date.now() -> same generated id -> the first entry gets overwritten, not duplicated.
    const saved = JSON.parse(localStorage.getItem('mf_custom_layouts_v2')!)
    expect(saved).toHaveLength(1)
    expect(saved[0].name).toBe('Second Save')
  })
})

describe('Dashboard — corrupted / seeded localStorage', () => {
  it('falls back to defaults when stored layout/custom-layout JSON is corrupted', () => {
    localStorage.setItem('mf_dashboard_layout_v1', '{ not valid json')
    localStorage.setItem('mf_custom_layouts_v2', '{ not valid json')
    render(<Dashboard />)
    expect(screen.getByText('Profesyonel Trader')).toBeInTheDocument()
  })

  it('falls back to the first template name/icon when activeTemplateId matches nothing', () => {
    localStorage.setItem('mf_dashboard_layout_v1', JSON.stringify({ activeTemplateId: 'does-not-exist' }))
    render(<Dashboard />)
    expect(screen.getByText('Profesyonel Trader')).toBeInTheDocument()
  })

  it('loads a saved custom layout as the active one on mount, resolving widget types through every fallback path', () => {
    localStorage.setItem('mf_dashboard_layout_v1', JSON.stringify({ activeTemplateId: 'seeded-custom' }))
    localStorage.setItem('mf_custom_layouts_v2', JSON.stringify([
      {
        id: 'seeded-custom',
        name: 'Seeded Layout',
        savedAt: new Date().toISOString(),
        items: [
          // No `type`, but `i` matches a widget id from the investor-view template.
          { i: 'iv-balance', x: 0, y: 0, w: 4, h: 2 },
          // No `type`, `i` doesn't match any template widget id, but contains a known type substring.
          { i: 'stray-heatmap-item', x: 4, y: 0, w: 4, h: 2 },
          // No `type`, `i` matches nothing at all -> renders nothing.
          { i: 'totally-unrecognized-id', x: 8, y: 0, w: 4, h: 2 },
          // Explicit but unknown `type` -> renderWidgetContent's default case.
          { i: 'bogus-item', x: 0, y: 2, w: 4, h: 2, type: 'not-a-real-widget-type' },
        ],
      },
    ]))

    render(<Dashboard />)
    expect(screen.getByText('Seeded Layout')).toBeInTheDocument()
    expect(screen.getAllByText('Yatırım Hesabım').length).toBeGreaterThan(0) // resolved via template-search fallback
  })

  it('lists a saved-but-inactive custom layout in "Kişisel Düzenlerim" and switches to it when clicked', () => {
    localStorage.setItem('mf_dashboard_layout_v1', JSON.stringify({ activeTemplateId: 'investor-view' }))
    localStorage.setItem('mf_custom_layouts_v2', JSON.stringify([
      { id: 'custom-a', name: 'Custom A', savedAt: new Date().toISOString(), items: [{ i: 'iv-balance', x: 0, y: 0, w: 4, h: 2, type: 'investment-balance' }] },
      { id: 'custom-b', name: 'Custom B', savedAt: new Date().toISOString(), items: [{ i: 'iv-balance', x: 0, y: 0, w: 4, h: 2, type: 'investment-balance' }] },
    ]))

    render(<Dashboard />)
    fireEvent.click(screen.getByText('Profesyonel Trader'))
    expect(screen.getByText('Custom A')).toBeInTheDocument()
    expect(screen.getByText('Custom B')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Custom A'))
    expect(screen.getByText('Custom A')).toBeInTheDocument() // now the active badge
  })
})
