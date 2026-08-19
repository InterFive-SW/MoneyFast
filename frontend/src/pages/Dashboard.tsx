import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'

import { useState, useCallback, useRef, useEffect } from 'react'
import GridLayout from 'react-grid-layout'
import type { Layout } from 'react-grid-layout'

const AnyGridLayout = GridLayout as any

import type { DashboardLayoutState, WidgetType, DashboardTemplate, GridLayoutItem, CustomLayoutState } from '../types/dashboard'
import { DASHBOARD_TEMPLATES, DEFAULT_TEMPLATE_ID } from '../data/templates'
import { MOCK_INVESTMENT_BALANCE, MOCK_POSITIONS, MOCK_ASSET_ALLOCATION, MOCK_ORDERS, MOCK_MARKET_TICKERS, MOCK_NEWS } from '../data/mockData'

import InvestmentBalanceWidget from '../components/widgets/InvestmentBalanceWidget'
import PositionsWidget from '../components/widgets/PositionsWidget'
import AssetAllocationWidget from '../components/widgets/AssetAllocationWidget'
import OrderHistoryWidget from '../components/widgets/OrderHistoryWidget'
import PortfolioChartWidget from '../components/widgets/PortfolioChartWidget'
import NewsWidget from '../components/widgets/NewsWidget'
import MiniTickerWidget from '../components/widgets/MiniTickerWidget'
import TotalBalanceWidget from '../components/widgets/TotalBalanceWidget'
import RecentTransactionsWidget from '../components/widgets/RecentTransactionsWidget'
import SpendingOverviewWidget from '../components/widgets/SpendingOverviewWidget'
import QuickActionsWidget from '../components/widgets/QuickActionsWidget'
import SavingsGoalWidget from '../components/widgets/SavingsGoalWidget'
import WatchlistWidget from '../components/widgets/WatchlistWidget'
import TopMoversWidget from '../components/widgets/TopMoversWidget'
import DividendCalendarWidget from '../components/widgets/DividendCalendarWidget'
import SectorAllocationWidget from '../components/widgets/SectorAllocationWidget'
import ProfitLossHeatmapWidget from '../components/widgets/ProfitLossHeatmapWidget'

import { useContainerWidth } from 'react-grid-layout'

// ─── Sabitler ─────────────────────────────────────────────────────────────────
const GRID_COLS = 12
const ROW_HEIGHT = 80
const LAYOUT_STORAGE_KEY = 'mf_dashboard_layout_v1'
const CUSTOM_LAYOUTS_KEY = 'mf_custom_layouts_v2'

// Tüm mümkün widget tipleri ve Türkçe isimleri
const ALL_AVAILABLE_WIDGETS: { type: WidgetType; label: string; defaultW: number; defaultH: number; minW: number; minH: number }[] = [
  { type: 'investment-balance', label: 'Yatırım Hesabım', defaultW: 3, defaultH: 2, minW: 2, minH: 1 },
  { type: 'positions', label: 'Pozisyonlar', defaultW: 7, defaultH: 6, minW: 4, minH: 3 },
  { type: 'order-history', label: 'Emir Geçmişi', defaultW: 6, defaultH: 3, minW: 3, minH: 2 },
  { type: 'portfolio-chart', label: 'Portföy Grafiği', defaultW: 5, defaultH: 3, minW: 3, minH: 2 },
  { type: 'news', label: 'Piyasa Haberleri', defaultW: 5, defaultH: 4, minW: 3, minH: 2 },
  { type: 'asset-allocation', label: 'Varlık Dağılımı', defaultW: 3, defaultH: 3, minW: 2, minH: 2 },
  { type: 'mini-ticker-usd', label: 'USD/TRY Ticker', defaultW: 3, defaultH: 1, minW: 2, minH: 1 },
  { type: 'mini-ticker-eur', label: 'EUR/TRY Ticker', defaultW: 3, defaultH: 1, minW: 2, minH: 1 },
  { type: 'mini-ticker-gold', label: 'Altın Ticker', defaultW: 3, defaultH: 1, minW: 2, minH: 1 },
  { type: 'mini-ticker-bist100', label: 'BIST100 Ticker', defaultW: 3, defaultH: 1, minW: 2, minH: 1 },
  { type: 'total-balance', label: 'Banka Bakiyesi', defaultW: 8, defaultH: 2, minW: 3, minH: 1 },
  { type: 'recent-transactions', label: 'Son İşlemler', defaultW: 7, defaultH: 5, minW: 4, minH: 3 },
  { type: 'spending-overview', label: 'Harcama Özeti', defaultW: 5, defaultH: 4, minW: 3, minH: 2 },
  { type: 'quick-actions', label: 'Hızlı İşlemler', defaultW: 4, defaultH: 3, minW: 2, minH: 2 },
  { type: 'savings-goal', label: 'Tasarruf Hedefi', defaultW: 5, defaultH: 5, minW: 2, minH: 2 },
  { type: 'watchlist', label: 'İzleme Listesi', defaultW: 4, defaultH: 6, minW: 2, minH: 3 },
  { type: 'top-movers', label: 'Hareketliler', defaultW: 4, defaultH: 6, minW: 2, minH: 3 },
  { type: 'dividend-calendar', label: 'Temettü Takvimi', defaultW: 4, defaultH: 6, minW: 2, minH: 3 },
  { type: 'sector-allocation-pie', label: 'Sektörel Dağılım', defaultW: 4, defaultH: 4, minW: 2, minH: 2 },
  { type: 'heatmap', label: 'Isı Haritası', defaultW: 8, defaultH: 5, minW: 4, minH: 3 },
]

// ─── Yardımcı Fonksiyonlar ────────────────────────────────────────────────────
const generateDefaultLayout = (template: DashboardTemplate): Layout => {
  // type bilgisini gridLayout state'ine zorla ekliyoruz
  return template.widgets.map((w) => ({ i: w.id, x: w.x, y: w.y, w: w.w, h: w.h, type: w.type } as any))
}

function loadLayoutState(): DashboardLayoutState {
  try {
    const raw = localStorage.getItem(LAYOUT_STORAGE_KEY)
    if (raw) return JSON.parse(raw) as DashboardLayoutState
  } catch { }
  return { activeTemplateId: DEFAULT_TEMPLATE_ID }
}

function loadCustomLayouts(): CustomLayoutState[] {
  try {
    const raw = localStorage.getItem(CUSTOM_LAYOUTS_KEY)
    if (raw) return JSON.parse(raw) as CustomLayoutState[]
  } catch { }
  return []
}

function saveCustomLayout(layout: CustomLayoutState) {
  const existing = loadCustomLayouts()
  // Eğer aynı ID'li varsa güncelle, yoksa ekle
  const index = existing.findIndex(l => l.id === layout.id)
  if (index >= 0) existing[index] = layout
  else existing.push(layout)
  localStorage.setItem(CUSTOM_LAYOUTS_KEY, JSON.stringify(existing))
}

// ─── Widget Render Motoru ─────────────────────────────────────────────────────
function renderWidgetContent(type: WidgetType, w?: number, h?: number): JSX.Element | null {
  switch (type) {
    case 'investment-balance': return <InvestmentBalanceWidget data={MOCK_INVESTMENT_BALANCE} />
    case 'positions': return <PositionsWidget positions={MOCK_POSITIONS} />
    case 'asset-allocation': return <AssetAllocationWidget items={MOCK_ASSET_ALLOCATION} />
    case 'order-history': return <OrderHistoryWidget orders={MOCK_ORDERS} />
    case 'portfolio-chart': return <PortfolioChartWidget w={w} h={h} />
    case 'news': return <NewsWidget news={MOCK_NEWS} />
    case 'mini-ticker-usd': return <MiniTickerWidget ticker={MOCK_MARKET_TICKERS.find(t => t.symbol === 'USD/TRY')!} />
    case 'mini-ticker-eur': return <MiniTickerWidget ticker={MOCK_MARKET_TICKERS.find(t => t.symbol === 'EUR/TRY')!} />
    case 'mini-ticker-gold': return <MiniTickerWidget ticker={MOCK_MARKET_TICKERS.find(t => t.symbol === 'ALTIN')!} />
    case 'mini-ticker-bist100': return <MiniTickerWidget ticker={MOCK_MARKET_TICKERS.find(t => t.symbol === 'BIST100')!} />
    case 'total-balance': return <TotalBalanceWidget data={{ period: 'Bu Ay', total: 145000, changePercent: 5.2, changeAmount: 7500, sparklinePoints: [100, 102, 98, 105, 110] }} />
    case 'recent-transactions': return <RecentTransactionsWidget transactions={[]} />
    case 'spending-overview': return <SpendingOverviewWidget data={{ month: 'Ağustos', totalExpense: 12500, changePercent: -2.1, categories: [{ label: 'Market', amount: 4000, color: '#10b981', icon: '🛒' }] }} />
    case 'quick-actions': return <QuickActionsWidget />
    case 'savings-goal': return <SavingsGoalWidget goals={[{ id: 'g1', name: 'Araba', target: 500000, current: 150000, icon: '🚗', deadline: '2027', color: '#10b981' }]} />
    case 'watchlist': return <WatchlistWidget />
    case 'top-movers': return <TopMoversWidget />
    case 'dividend-calendar': return <DividendCalendarWidget />
    case 'sector-allocation-pie': return <SectorAllocationWidget />
    case 'heatmap': return <ProfitLossHeatmapWidget w={w} h={h} />
    default: return null
  }
}

// ─── Şablon Seçici Alt Bileşeni ───────────────────────────────────────────────
function TemplateSelector({
  templates, customLayouts, activeId, onChange, disabled
}: {
  templates: DashboardTemplate[], customLayouts: CustomLayoutState[], activeId: string, onChange: (id: string) => void, disabled?: boolean
}) {
  const [isOpen, setIsOpen] = useState(false)

  const getActiveNameAndIcon = () => {
    const t = templates.find(x => x.id === activeId)
    if (t) return { name: t.name, icon: t.icon }
    const c = customLayouts.find(x => x.id === activeId)
    if (c) return { name: c.name, icon: '🧑‍🎨' }
    return { name: templates[0].name, icon: templates[0].icon }
  }

  const active = getActiveNameAndIcon()

  return (
    <div className="relative">
      <button
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={`flex items-center gap-2 rounded-xl border border-white/10 bg-slate-900/50 px-3.5 py-2 text-sm font-medium text-slate-300 shadow-sm backdrop-blur-sm transition hover:border-white/20 hover:bg-white/10 ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
      >
        <span>{active.icon}</span>
        <span>{active.name}</span>
        <svg className={`h-4 w-4 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 top-full z-20 mt-2 w-72 overflow-hidden rounded-2xl border border-white/10 bg-slate-900 py-1.5 shadow-[0_20px_60px_-12px_rgba(0,0,0,0.5)] backdrop-blur-xl max-h-[80vh] overflow-y-auto">

            <div className="px-3 pt-2 pb-1 text-xs font-semibold uppercase tracking-wider text-slate-400">Hazır Şablonlar</div>
            {templates.map(template => (
              <div
                key={template.id}
                onClick={() => { onChange(template.id); setIsOpen(false) }}
                className={`flex cursor-pointer items-start gap-3 px-4 py-2 hover:bg-white/5 ${template.id === activeId ? 'bg-brandBlue/10' : ''}`}
              >
                <span className="mt-0.5 text-lg leading-none">{template.icon}</span>
                <div>
                  <p className={`text-sm font-semibold ${template.id === activeId ? 'text-brandBlue' : 'text-slate-200'}`}>{template.name}</p>
                </div>
              </div>
            ))}

            {customLayouts.filter(c => !templates.some(t => t.id === c.id)).length > 0 && (
              <>
                <div className="mt-2 border-t border-white/10" />
                <div className="px-3 pt-3 pb-1 text-xs font-semibold uppercase tracking-wider text-slate-400">Kişisel Düzenlerim</div>
                {customLayouts.filter(c => !templates.some(t => t.id === c.id)).map(layout => (
                  <div
                    key={layout.id}
                    onClick={() => { onChange(layout.id); setIsOpen(false) }}
                    className={`flex cursor-pointer items-start gap-3 px-4 py-2 hover:bg-white/5 ${layout.id === activeId ? 'bg-brandBlue/10' : ''}`}
                  >
                    <span className="mt-0.5 text-lg leading-none">🧑‍🎨</span>
                    <div>
                      <p className={`text-sm font-semibold ${layout.id === activeId ? 'text-brandBlue' : 'text-slate-200'}`}>{layout.name}</p>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ─── Ana Sayfa Bileşeni ───────────────────────────────────────────────────────
export default function Dashboard() {
  const dragTypeRef = useRef<WidgetType | null>(null);
  // Sürükleme sırasında mouse'un üzerine geldiği grid hücresi
  const dropPositionRef = useRef<{ x: number; y: number }>({ x: 0, y: Infinity });
  // Ghost önizleme: sürükleme sırasında grid'e enjekte edilen geçici eleman
  const [dropPreview, setDropPreview] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  // dragover throttle için son güncelleme zamanı
  const lastPreviewUpdate = useRef<number>(0);
  const [droppingItem, setDroppingItem] = useState<{ i: string; w: number; h: number }>({ i: '__dropping-elem__', w: 4, h: 3 });
  const [layoutState, setLayoutState] = useState<DashboardLayoutState>(loadLayoutState)
  const [isEditMode, setIsEditMode] = useState(false)
  const [isPoolOpen, setIsPoolOpen] = useState(false)
  const [customLayouts, setCustomLayouts] = useState<CustomLayoutState[]>(loadCustomLayouts)

  // Düzen ismi kaydetme modal state
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [saveName, setSaveName] = useState('')

  const { width: containerWidth, containerRef } = useContainerWidth({ initialWidth: 900 })

  const getActiveLayoutItems = (): GridLayoutItem[] => {
    let items: GridLayoutItem[] = []
    const custom = customLayouts.find(c => c.id === layoutState.activeTemplateId)
    if (custom) {
      items = custom.items
    } else {
      const tpl = DASHBOARD_TEMPLATES.find(t => t.id === layoutState.activeTemplateId) || DASHBOARD_TEMPLATES[0]
      items = generateDefaultLayout(tpl) as GridLayoutItem[]
    }
    return items.map(item => ({ ...item, static: true }))
  }

  const [gridLayout, setGridLayout] = useState<GridLayoutItem[]>(getActiveLayoutItems)
  const [originalLayout, setOriginalLayout] = useState<GridLayoutItem[]>([])

  function handleTemplateChange(templateId: string) {
    const nextState: DashboardLayoutState = {
      ...layoutState,
      activeTemplateId: templateId,
      lastModified: new Date().toISOString(),
    }
    setLayoutState(nextState)
    localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(nextState))

    const custom = customLayouts.find(c => c.id === templateId)
    if (custom) {
      setGridLayout(custom.items.map(i => ({ ...i, static: true })))
    } else {
      const nextTemplate = DASHBOARD_TEMPLATES.find((t) => t.id === templateId)
      if (nextTemplate) {
        const layout = generateDefaultLayout(nextTemplate) as GridLayoutItem[]
        setGridLayout(layout.map(i => ({ ...i, static: true })))
      }
    }
    setIsEditMode(false)
    setIsPoolOpen(false)
  }

  // BURASI DEĞİŞTİRİLDİ: RGL'nin kendi yarattığı ghost elementleri silmesini engelledik.
  const handleGridLayoutChange = useCallback((newLayout: Layout) => {
    setGridLayout(prev => {
      // PREV (eski state) üzerinden dönüyoruz ki, yeni eklediğimiz eleman silinmesin!
      return prev.map(item => {
        const matched = newLayout.find(l => l.i === item.i);
        // Eğer RGL'den yeni koordinat geldiyse güncelle, yoksa (yani bizim yeni eklediğimiz bir widget ise) mevcut halini koru.
        return matched ? { ...item, x: matched.x, y: matched.y, w: matched.w, h: matched.h } : item;
      });
    });
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isEditMode) {
        setGridLayout(originalLayout)
        setIsEditMode(false)
        setIsPoolOpen(false)
      }
    }
    
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isEditMode, originalLayout])

  function handleEditToggle() {
    if (!isEditMode) {
      setOriginalLayout(gridLayout) // İptal durumu için yedekle
      setIsPoolOpen(true)
      setGridLayout(prev => prev.map(item => ({ ...item, static: false })))
    } else {
      setIsPoolOpen(false)
      setGridLayout(prev => prev.map(item => ({ ...item, static: true })))
    }
    setIsEditMode(!isEditMode)
  }

  function handleRemoveWidget(id: string) {
    setGridLayout(prev => prev.filter(item => item.i !== id))
  }

  function handleAddWidget(widgetConf: typeof ALL_AVAILABLE_WIDGETS[0]) {
    setGridLayout(prev => [
      ...prev,
      {
        i: `${widgetConf.type}-custom-${Date.now()}`,
        x: 0,
        y: Infinity,
        w: widgetConf.minW,   // Başlangıçta minimum boyut
        h: widgetConf.minH,
        type: widgetConf.type as any,
        static: false
      }
    ])
  }

  function submitSaveLayout() {
    if (!saveName.trim()) return
    const newId = `custom-layout-${Date.now()}`
    const payload: CustomLayoutState = {
      id: newId,
      name: saveName.trim(),
      items: gridLayout,
      savedAt: new Date().toISOString(),
    }
    saveCustomLayout(payload)
    setCustomLayouts(loadCustomLayouts()) // Listeyi güncelle
    handleTemplateChange(newId) // Yeni kaydedilen şablona geç ve edit moddan çık
    setShowSaveModal(false)
    setSaveName('')
  }

  function submitSaveLayoutInPlace() {
    // DİKKAT: localStorage'a hiçbir şekilde kayıt YAPILMAYACAK.
    // Sadece düzenleme modunu kapatıyor ve tüm widget'ları static:true yapıyoruz.
    // static:false kalan widget'lar düzenleme modu kapansa bile sürüklenebilir kalır.
    setGridLayout(prev => prev.map(item => ({ ...item, static: true })))
    setIsEditMode(false)
    setIsPoolOpen(false)
  }


  // Havuzdaki mevcut olmayan widget'ları hesapla


  // Widget ID'sinden veya `type` property'sinden widget türünü bulma
  const getWidgetType = (item: any): WidgetType | null => {
    if (item.type) return item.type

    // Önce o anki aktif şablonda ara
    const tpl = DASHBOARD_TEMPLATES.find(t => t.id === layoutState.activeTemplateId)
    const w = tpl?.widgets.find(w => w.id === item.i)
    if (w) return w.type

    // Bulamazsa ID değişimi yaşanmış olabilir, TÜM hazır şablonlarda ara
    for (const template of DASHBOARD_TEMPLATES) {
      const found = template.widgets.find(widget => widget.id === item.i)
      if (found) return found.type
    }

    // String kontrolü (yeni eklenenler için)
    const conf = ALL_AVAILABLE_WIDGETS.find(aw => item.i.includes(aw.type))
    return conf?.type as WidgetType || null
  }

  const activeTypes = new Set(gridLayout.map(item => getWidgetType(item)).filter(Boolean))
  const availablePoolWidgets = ALL_AVAILABLE_WIDGETS.filter(w => !activeTypes.has(w.type))

  const cardBaseClass = `h-full w-full flex flex-col rounded-2xl bg-slate-900/50 p-4 backdrop-blur-xl transition-all duration-200 text-white ${isEditMode
    ? 'border-2 border-dashed border-brandBlue/50 shadow-[0_4px_20px_-8px_rgba(75,123,229,0.3)]'
    : 'border border-white/10 shadow-[0_4px_24px_-8px_rgba(0,0,0,0.2)] hover:shadow-[0_8px_32px_-8px_rgba(0,0,0,0.4)]'
    }`

  return (
    <div className={`p-6 sm:p-8 min-h-screen transition-[padding] duration-300 ${isEditMode ? 'pl-[280px]' : ''}`}>
      {/* ── Üst Araç Çubuğu ──────────────────────────────────────────── */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-white">
            {isEditMode ? '🔧 Panel Düzenleme Modu' : 'Hoş Geldiniz 👋'}
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            {isEditMode
              ? 'Widget\'ları sürükleyerek yeniden düzenleyin. Soldaki havuzdan yeni modüller ekleyebilirsiniz.'
              : 'Finansal durumunuzun güncel özeti aşağıda görüntülenmektedir.'}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <TemplateSelector
            templates={DASHBOARD_TEMPLATES}
            customLayouts={customLayouts}
            activeId={layoutState.activeTemplateId}
            onChange={handleTemplateChange}
            disabled={isEditMode}
          />

          {!isEditMode ? (
            <button
              onClick={handleEditToggle}
              className="flex items-center gap-2 rounded-xl border border-white/10 bg-slate-900/50 px-3.5 py-2 text-sm font-medium text-slate-300 shadow-sm backdrop-blur-sm transition hover:border-white/20 hover:bg-white/10 hover:text-white"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
              Paneli Düzenle
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  setGridLayout(originalLayout)
                  setIsEditMode(false)
                  setIsPoolOpen(false)
                }}
                className="rounded-xl border border-white/10 bg-slate-900/50 px-3.5 py-2 text-sm font-medium text-slate-300 shadow-sm backdrop-blur-sm transition hover:bg-white/10 hover:text-white"
              >
                İptal
              </button>
              <button
                onClick={submitSaveLayoutInPlace}
                className="rounded-xl border border-brandBlue bg-slate-900/50 px-4 py-2 text-sm font-semibold text-brandBlue shadow-sm transition hover:bg-brandBlue hover:text-white"
              >
                Kaydet
              </button>
              <button
                onClick={() => setGridLayout([])}
                className="rounded-xl border border-rose-500/50 bg-slate-900/50 px-4 py-2 text-sm font-semibold text-rose-500 shadow-sm transition hover:bg-rose-500/10"
              >
                Tümünü Temizle
              </button>
              <button
                onClick={() => setShowSaveModal(true)}
                className="flex items-center gap-2 rounded-xl bg-brandBlue px-4 py-2 text-sm font-semibold text-white shadow-sm shadow-brandBlue/30 transition hover:bg-brandBlue/80"
              >
                Farklı Kaydet
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── Widget Alanı ──────────────────────────────────────────────── */}
      <div
        ref={containerRef as any}
        onDragOver={(e) => {
          if (!isEditMode || !dragTypeRef.current) return;
          e.preventDefault();
          e.dataTransfer.dropEffect = 'move';
          const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
          const mouseX = e.clientX - rect.left;
          const mouseY = e.clientY - rect.top;
          const MARGIN = 16;
          const cellW = (containerWidth + MARGIN) / GRID_COLS;
          const cellH = ROW_HEIGHT + MARGIN;
          const newX = Math.max(0, Math.min(GRID_COLS - 1, Math.floor(mouseX / cellW)));
          // Widget'ı cursor'a ortala: widget yüksekliğinin yarısını çıkar
          const type = dragTypeRef.current;
          const widgetConf = ALL_AVAILABLE_WIDGETS.find(w => w.type === type);
          const widgetH = widgetConf?.defaultH || 3;
          const halfHeightOffset = Math.floor(widgetH / 2) * cellH;
          const newY = Math.max(0, Math.floor((mouseY - halfHeightOffset) / cellH));
          dropPositionRef.current = { x: newX, y: newY };
          // 60fps için throttle (~16ms)
          const now = Date.now();
          if (now - lastPreviewUpdate.current > 50) {
            lastPreviewUpdate.current = now;
            setDropPreview({ x: newX, y: newY, w: widgetConf?.defaultW || 4, h: widgetConf?.defaultH || 3 });
          }

        }}
        onDragLeave={(e) => {
          // Gerçekten container'dan çıkılıyorsa ghost'u temizle
          if (!e.currentTarget.contains(e.relatedTarget as Node)) {
            setDropPreview(null);
          }
        }}
        onDrop={(e) => {
          e.preventDefault();
          setDropPreview(null);
          const type = dragTypeRef.current;
          if (!type || !isEditMode) return;
          const widgetConf = ALL_AVAILABLE_WIDGETS.find(w => w.type === type);
          if (!widgetConf) return;
          const newId = `${type}-custom-${Date.now()}`;
          setGridLayout(prev => [
            ...prev,
            {
              i: newId,
              x: dropPositionRef.current.x,
              y: dropPositionRef.current.y,
              w: widgetConf.minW,   // Başlangıçta minimum boyut
              h: widgetConf.minH,
              type: type as any,
              static: false
            }
          ]);
          dragTypeRef.current = null;
        }}
      >
        <AnyGridLayout
          className={`layout ${isEditMode ? 'border-2 border-dashed border-brandBlue/50 min-h-[400px] rounded-xl' : ''}`}
          layout={[
            ...gridLayout,
            // Ghost önizleme: sürükleme sırasında geçici placeholder enjekte et
            ...(dropPreview ? [{ i: '__drop-preview__', x: dropPreview.x, y: dropPreview.y, w: dropPreview.w, h: dropPreview.h, static: true, isDraggable: false, isResizable: false }] : [])
          ]}
          cols={GRID_COLS}
          rowHeight={ROW_HEIGHT}
          width={containerWidth}
          margin={[16, 16]}
          containerPadding={[0, 0]}
          draggableHandle=".drag-handle"
          onLayoutChange={handleGridLayoutChange}
          isResizable={isEditMode}
          isDraggable={isEditMode}
          useCSSTransforms
          isDroppable={false}
          compactType="vertical"
          preventCollision={false}
        >
          {gridLayout.map((layoutItem) => {
            const type = getWidgetType(layoutItem)
            if (!type) return null

            return (
              <div key={layoutItem.i} className={`${cardBaseClass} relative overflow-hidden group`}>
                {isEditMode && (
                  <div className="drag-handle absolute left-3 top-3 z-10 flex cursor-grab items-center gap-1.5 rounded-lg border border-brandBlue/30 bg-brandBlue/10 px-2 py-1 active:cursor-grabbing">
                    <span className="text-[10px] font-semibold text-brandBlue">Sürükle</span>
                  </div>
                )}
                {isEditMode && (
                  <button
                    onClick={() => handleRemoveWidget(layoutItem.i)}
                    className="absolute right-3 top-3 z-10 p-1 rounded-md text-slate-400 hover:bg-rose-500/20 hover:text-rose-400 transition"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                  </button>
                )}
                <div className={`flex-1 w-full h-full overflow-hidden ${isEditMode ? 'mt-8 pointer-events-none' : ''}`}>
                  {renderWidgetContent(type, layoutItem.w, layoutItem.h)}
                </div>
              </div>
            )
          })}
          {/* Ghost önizleme elementi */}
          {dropPreview && (
            <div key="__drop-preview__" className="pointer-events-none">
              <div className="h-full w-full rounded-2xl border-2 border-dashed border-brandBlue bg-brandBlue/20 backdrop-blur-sm flex items-center justify-center animate-pulse">
                <span className="text-brandBlue text-xs font-semibold tracking-wide">Buraya bırak</span>
              </div>
            </div>
          )}
        </AnyGridLayout>
      </div>

      {/* ── Sol Widget Paleti (Edit Mode) ──────────────────────────────────────────────── */}
      {isEditMode && (
        <div className={`fixed left-0 top-0 bottom-0 w-64 bg-slate-950/95 backdrop-blur-xl border-r border-white/10 shadow-2xl z-50 flex flex-col transition-transform duration-300 translate-x-0`}>
          <div className="p-4 border-b border-white/10 flex items-center justify-between bg-slate-900/50">
            <div>
              <h3 className="font-semibold text-white">Widget Paleti</h3>
              <p className="text-xs text-slate-400 mt-0.5">Sürükleyip bırakın</p>
            </div>
          </div>
          <div className="p-4 flex-1 overflow-y-auto space-y-4 custom-scrollbar">
            {availablePoolWidgets.length === 0 ? (
              <p className="text-sm text-slate-400 text-center py-8">Tüm modüller ekranda mevcut.</p>
            ) : (
              availablePoolWidgets.map(widgetConf => (
                <div
                  key={widgetConf.type}
                  draggable={true}
                  unselectable="on"
                  onClick={() => handleAddWidget(widgetConf)}
                  onMouseEnter={() => {
                    setDroppingItem({ i: '__dropping-elem__', w: widgetConf.defaultW, h: widgetConf.defaultH });
                  }}
                  onDragStart={(e) => {
                    dragTypeRef.current = widgetConf.type;
                    setDroppingItem({
                      i: '__dropping-elem__',
                      w: widgetConf.defaultW,
                      h: widgetConf.defaultH
                    });
                    e.dataTransfer.setData("text/plain", widgetConf.type);
                    // RGL 'move' effectAllowed bekliyor, 'copy' drop'u tarayıcı engelleyebilir
                    e.dataTransfer.effectAllowed = 'move';
                  }}
                  onDragEnd={() => {
                    // Sürükleme iptal edilirse veya dışarıda bırakılırsa temizle
                    if (dragTypeRef.current) {
                      dragTypeRef.current = null;
                    }
                  }}
                  className="group relative rounded-xl border border-white/10 bg-slate-900 overflow-hidden shadow-sm hover:border-brandBlue hover:shadow-md transition-all cursor-grab active:cursor-grabbing hover:cursor-pointer"
                >
                  <div className="px-3 py-2 border-b border-white/10 flex items-center justify-between bg-white/5">
                    <span className="text-sm font-medium text-white flex items-center gap-2">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 9h14M5 15h14" /></svg>
                      {widgetConf.label}
                    </span>
                  </div>
                  <div className="relative h-20 w-full bg-slate-950/50 overflow-hidden">
                    <div
                      className="absolute inset-0 origin-top-left pointer-events-none"
                      style={{ width: '200%', height: '200%', transform: 'scale(0.5)' }}
                    >
                      <div className="w-full h-full p-2 opacity-90 grayscale-[0.2]">
                        <div className="h-full w-full rounded-xl bg-slate-900 border border-white/10 shadow-sm overflow-hidden pointer-events-none">
                          {renderWidgetContent(widgetConf.type as WidgetType, widgetConf.defaultW, widgetConf.defaultH)}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* ── Düzen Kaydetme Modalı ──────────────────────────────────────────────── */}
      {showSaveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl">
            <h3 className="text-lg font-bold text-white">Düzeni Kaydet</h3>
            <p className="mt-1 text-sm text-slate-400">Bu panele bir isim verin. Açılır menüden daha sonra tekrar seçebilirsiniz.</p>

            <input
              type="text"
              autoFocus
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="Örn: Hafta Sonu Görünümü"
              className="mt-4 w-full rounded-xl border border-white/20 bg-slate-950 px-4 py-2.5 text-sm text-white outline-none focus:border-brandBlue focus:ring-1 focus:ring-brandBlue"
            />

            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setShowSaveModal(false)}
                className="rounded-xl px-4 py-2 text-sm font-medium text-slate-300 hover:bg-white/10"
              >
                İptal
              </button>
              <button
                onClick={submitSaveLayout}
                disabled={!saveName.trim()}
                className="rounded-xl bg-brandBlue px-4 py-2 text-sm font-semibold text-white shadow-sm disabled:opacity-50 hover:bg-brandBlue/80"
              >
                Kaydet
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}