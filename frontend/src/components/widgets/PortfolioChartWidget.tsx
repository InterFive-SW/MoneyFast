import { useState, useEffect, useRef } from 'react'
import { createChart, ColorType, IChartApi, ISeriesApi, CandlestickSeries, HistogramSeries } from 'lightweight-charts'
import { MOCK_CHART_DATA } from '../../data/mockData'

type TimeFilter = 'Gün' | 'Hafta' | 'Ay' | '3 Ay' | 'Yıl'

interface Props {
  w?: number
  h?: number
}

export default function PortfolioChartWidget({ w = 4, h = 4 }: Props) {
  const [filter, setFilter] = useState<TimeFilter>('Yıl')
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

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

    // Volume Serisi (Altta olacak)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: '', // priceScaleId boş olmalı ki overlay olarak altta kalsın
    })
    chart.priceScale('').applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    })
    volumeSeriesRef.current = volumeSeries

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
      volumeSeriesRef.current = null
    }
  }, [])

  // Filtre değiştiğinde veriyi güncelle
  useEffect(() => {
    if (!candlestickSeriesRef.current || !volumeSeriesRef.current || !chartRef.current) return

    const data = MOCK_CHART_DATA[filter]

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

    // Hacim datası
    const volumeData = uniqueData.map((d) => ({
      time: d.time as any,
      value: d.value || 0,
      color: d.color,
    }))

    try {
      candlestickSeriesRef.current.setData(candleData)
      volumeSeriesRef.current.setData(volumeData)
      chartRef.current.timeScale().fitContent()
    } catch (err) {
      console.error("Chart data error:", err)
    }
  }, [filter])

  if (w <= 2 || h <= 1) {
    const latestData = MOCK_CHART_DATA[filter].slice(-1)[0];
    const prevData = MOCK_CHART_DATA[filter].slice(-2)[0];
    const change = latestData && prevData ? latestData.close - prevData.close : 0;
    const isPositive = change >= 0;
    
    return (
      <div className="flex flex-col h-full w-full bg-transparent p-1 items-center justify-center text-center">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-2">Portföy Performansı (Özet)</h3>
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
        <div className="flex items-center gap-3">
          <h3 className="text-[13px] uppercase tracking-wider font-semibold text-slate-300">Portföy Performansı</h3>
          <span className="text-[11px] font-medium text-slate-400 bg-white/10 px-2 py-0.5 rounded-full">TRADINGVIEW ALTYAPISI</span>
        </div>
        
        <div className="flex space-x-1 bg-white/5 p-1 rounded-lg">
          {(['Gün', 'Hafta', 'Ay', '3 Ay', 'Yıl'] as TimeFilter[]).map((f) => (
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


