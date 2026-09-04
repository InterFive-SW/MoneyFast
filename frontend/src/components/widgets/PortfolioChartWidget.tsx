import { useState, useEffect, useRef } from 'react'
import { createChart, ColorType, IChartApi, ISeriesApi, CandlestickSeries } from 'lightweight-charts'
import { apiClient } from '../../api/client'
import { BASE_CURRENCY } from '../../lib/money'

type TimeFilter = 'Gün' | 'Hafta' | 'Ay' | 'Yıl' | '2 Yıl'

/**
 * The backend keys its ranges without diacritics. "3 Ay" is gone because the
 * endpoint has no such bucket — offering a filter with no data behind it just
 * renders an empty chart.
 */
/**
 * Aralık -> sunucunun döndürdüğü seri anahtarı.
 *
 * Her aralık kendi çözünürlüğünde geliyor; gün 5 dakikalık barlardan, hafta ve
 * ay onların 15 dakikalık ve saatlik kovalarından, yıl ve iki yıl günlük
 * barlardan.
 */
const RANGE_KEYS: Record<TimeFilter, string> = {
  'Gün': 'gun',
  'Hafta': 'hafta',
  'Ay': 'ay',
  'Yıl': 'yil',
  '2 Yıl': 'iki_yil',
}

interface ChartPoint {
  time: number
  open: number
  high: number
  low: number
  close: number
  value: number
  color: string
}

interface Props {
  w?: number
  h?: number
}

export default function PortfolioChartWidget({ w = 4, h = 4 }: Props) {
  const [filter, setFilter] = useState<TimeFilter>('Yıl')
  // Real bars from market_candles. This chart drew MOCK_CHART_DATA — candles
  // generated in the browser — while /api/investment/portfolio/chart served
  // the genuine series and was called from nowhere.
  const [series, setSeries] = useState<Record<string, ChartPoint[]>>({})

  // Görünen aralık ne ise o isteniyor; hepsini birden çekmek çağrı başına
  // ~130 sorgu ve ölçülen 5,9 saniye demekti.
  useEffect(() => {
    const key = RANGE_KEYS[filter]
    if (series[key]) return
    let cancelled = false
    apiClient
      .getPortfolioChart(key)
      .then((response) => {
        if (cancelled) return
        setSeries((prev) => ({
          ...prev,
          ...(response as unknown as Record<string, ChartPoint[]>),
        }))
      })
      .catch((error) => console.error('Failed to load portfolio chart', error))
    return () => {
      cancelled = true
    }
  }, [filter, series])

  const points = series[RANGE_KEYS[filter]] ?? []
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)

  useEffect(() => {
    if (!chartContainerRef.current) return

    const container = chartContainerRef.current
    
    // Güvenli boyutlar
    const initialWidth = container.clientWidth > 0 ? container.clientWidth : 400
    const initialHeight = container.clientHeight > 0 ? container.clientHeight : 300

    // Chart başlatma
    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#64748b',
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
      },
      rightPriceScale: {
        borderVisible: false,
      },
      timeScale: {
        borderVisible: false,
      },
      crosshair: {
        mode: 0,
      },
      width: initialWidth,
      height: initialHeight,
    })
    chartRef.current = chart

    // Hacim paneli YOK: bir portföyün işlem hacmi yoktur. Buradaki çubuklar
    // endeksin hacmiydi ve grafik endeksi çizdiği sürece tutarlıydı.

    // Mum Serisi
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#14b8a6',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#14b8a6',
      wickDownColor: '#ef5350',
    })
    candlestickSeriesRef.current = candlestickSeries

    // ResizeObserver ile konteyner boyutunu dinle
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries.length === 0 || entries[0].target !== container) return
      const newRect = entries[0].contentRect
      if (newRect.width > 0 && newRect.height > 0) {
        chart.applyOptions({ width: newRect.width, height: newRect.height })
      }
    })
    
    resizeObserver.observe(container)

    return () => {
      resizeObserver.disconnect()
      chart.remove()
      chartRef.current = null
      candlestickSeriesRef.current = null
    }
  }, [])

  // Filtre DEĞİŞTİĞİNDE ya da veri GELDİĞİNDE. `series` boş başlıyor ve
  // fetch ile doluyor; bağımlılıkta yalnızca `filter` olduğu için ilk veri
  // hiç çizilmiyordu — grafik, kullanıcı aralığı değiştirene kadar boş
  // kalıyordu.
  useEffect(() => {
    if (!candlestickSeriesRef.current || !chartRef.current) return

    const data = points

    // Benzersiz ve sıralı veriler oluştur
    // lightweight-charts verilerin strictly ascending olmasını ister
    const uniqueData = [...data].sort((a, b) => Number(a.time) - Number(b.time))

    // Mum datası
    const candleData = uniqueData.map((d) => ({
      time: d.time as any,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }))

    try {
      candlestickSeriesRef.current.setData(candleData)
      chartRef.current.timeScale().fitContent()
    } catch (err) {
      console.error("Chart data error:", err)
    }
  }, [filter, series])

  if (w <= 2 || h <= 1) {
    const latestData = points.slice(-1)[0];
    const prevData = points.slice(-2)[0];
    const change = latestData && prevData ? latestData.close - prevData.close : 0;
    const isPositive = change >= 0;
    
    return (
      <div className="flex flex-col h-full w-full bg-transparent p-1 items-center justify-center text-center">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-2">
          Portföy Performansı (Özet)
          <span className="ml-1.5 normal-case tracking-normal text-slate-500">({BASE_CURRENCY})</span>
        </h3>
        <div className={`text-2xl font-bold ${isPositive ? 'text-accent-500' : 'text-rose-500'}`}>
          {latestData ? latestData.close.toLocaleString('tr-TR', { style: 'currency', currency: 'TRY' }) : '-'}
        </div>
        <p className="text-xs text-slate-400 mt-1">Son Kapanış</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full w-full bg-transparent p-1">
      <div className="flex items-center justify-between mb-4 z-10">
        {/* "TRADINGVIEW ALTYAPISI" rozeti kaldırıldı: o kütüphane
            kullanılmıyor. Grafik Recharts ve okuduğu seri bizim kendi
            `market_candles` tablomuz -- kullanılmayan bir sağlayıcıyı
            künyede taşımak, verinin nereden geldiği konusunda yanıltıyordu. */}
        <div className="flex items-center gap-3">
          <h3 className="text-[13px] uppercase tracking-wider font-semibold text-slate-300">Portföy Performansı</h3>
        </div>
        
        <div className="flex space-x-1 bg-white/5 p-1 rounded-lg">
          {(['Gün', 'Hafta', 'Ay', 'Yıl', '2 Yıl'] as TimeFilter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 text-[11px] uppercase tracking-wider font-bold rounded-md transition-all duration-200 ${
                filter === f 
                ? 'bg-white/10 shadow-sm text-brandBlue' 
                : 'text-slate-400 hover:text-slate-300 hover:bg-white/10'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 w-full h-full relative">
        <div ref={chartContainerRef} className="absolute inset-0" />
      </div>
    </div>
  )
}


