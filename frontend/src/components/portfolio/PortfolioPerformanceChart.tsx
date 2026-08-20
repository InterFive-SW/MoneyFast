import { useState, useEffect, useMemo, useRef } from 'react'
import { createChart, ColorType, IChartApi, ISeriesApi, CandlestickSeries, HistogramSeries } from 'lightweight-charts'
import {
  getSeries,
  presetRange,
  dateInputToSeconds,
  secondsToDateInput,
  RANGE_PRESETS,
  SERIES_START,
  SERIES_END,
} from '../../data/portfolioSeries'
import type { RangePreset } from '../../data/portfolioSeries'

type Mode = RangePreset | 'custom'

/**
 * Portföy Performansı Grafiği
 *
 * Hazır aralıklar (Gün/Hafta/Ay/3 Ay/Yıl) ve kullanıcının seçtiği serbest tarih
 * aralığı tek bir temel seriden dilimlenir — bkz. data/portfolioSeries.ts
 */
export default function PortfolioPerformanceChart() {
  const [mode, setMode] = useState<Mode>('Yıl')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [fromInput, setFromInput] = useState('')
  const [toInput, setToInput] = useState('')
  const [customRange, setCustomRange] = useState<{ from: number; to: number } | null>(null)
  const [rangeError, setRangeError] = useState('')

  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  const activeRange = useMemo(() => {
    if (mode === 'custom') return customRange
    return presetRange(mode)
  }, [mode, customRange])

  const data = useMemo(() => {
    // mode ve customRange her zaman birlikte güncellenir (bkz. handleApplyCustomRange /
    // handleClearCustomRange) — activeRange'in null olması testle ulaşılamaz (defensive kod).
    /* v8 ignore next */
    if (!activeRange) return []
    return getSeries(activeRange.from, activeRange.to)
  }, [activeRange])

  // Chart kurulumu (yalnızca mount'ta)
  useEffect(() => {
    // React commit'ten sonra ref her zaman dolu olur — testle ulaşılamaz (defensive kod).
    /* v8 ignore next */
    if (!chartContainerRef.current) return

    const container = chartContainerRef.current
    const initialWidth = container.clientWidth > 0 ? container.clientWidth : 400
    const initialHeight = container.clientHeight > 0 ? container.clientHeight : 300

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#64748b',
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: 'rgba(226, 232, 240, 0.6)' },
        horzLines: { color: 'rgba(226, 232, 240, 0.6)' },
      },
      rightPriceScale: { borderVisible: false },
      // timeVisible: saatlik aralıklarda eksende saat de görünsün
      timeScale: { borderVisible: false, timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
      width: initialWidth,
      height: initialHeight,
    })
    chartRef.current = chart

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    })
    chart.priceScale('').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })
    volumeSeriesRef.current = volumeSeries

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    })
    candlestickSeriesRef.current = candlestickSeries

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

  // Seçili aralık değişince veriyi güncelle
  useEffect(() => {
    // İlk effect her zaman önce çalışıp ref'leri doldurur — testle ulaşılamaz (defensive kod).
    /* v8 ignore next */
    if (!candlestickSeriesRef.current || !volumeSeriesRef.current || !chartRef.current) return
    if (data.length === 0) return

    const candleData = data.map((d) => ({
      time: d.time as any,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }))

    const volumeData = data.map((d) => ({
      time: d.time as any,
      value: d.value || 0,
      color: d.color,
    }))

    try {
      candlestickSeriesRef.current.setData(candleData)
      volumeSeriesRef.current.setData(volumeData)
      chartRef.current.timeScale().fitContent()
    } catch (err) {
      console.error('Chart data error:', err)
    }
  }, [data])

  function handleApplyCustomRange() {
    const from = dateInputToSeconds(fromInput)
    const to = dateInputToSeconds(toInput, true)

    if (Number.isNaN(from) || Number.isNaN(to)) {
      setRangeError('Lütfen başlangıç ve bitiş tarihlerini seçin.')
      return
    }
    if (to <= from) {
      setRangeError('Bitiş tarihi başlangıç tarihinden sonra olmalıdır.')
      return
    }
    if (from > SERIES_END || to < SERIES_START) {
      setRangeError('Seçilen aralık veri kapsamının dışında.')
      return
    }

    const clampedFrom = Math.max(from, SERIES_START)
    const clampedTo = Math.min(to, SERIES_END)

    // Temel seri her saatte kesintisiz veri içeriyor ve tarih girişleri gün
    // granülaritesinde (en az ~1 gün açıklık) — bu üst üste gelme kontrolünden
    // geçen bir aralığın boş çıkması testle ulaşılamaz (defensive kod).
    /* v8 ignore next 4 */
    if (getSeries(clampedFrom, clampedTo).length === 0) {
      setRangeError('Seçilen aralıkta veri bulunmuyor.')
      return
    }

    setRangeError('')
    setCustomRange({ from: clampedFrom, to: clampedTo })
    setMode('custom')
    setPickerOpen(false)
  }

  function handleClearCustomRange() {
    setRangeError('')
    setFromInput('')
    setToInput('')
    setCustomRange(null)
    setMode('Yıl')
    setPickerOpen(false)
  }

  const minDate = secondsToDateInput(SERIES_START)
  const maxDate = secondsToDateInput(SERIES_END)

  const rangeLabel =
    mode === 'custom' && customRange
      ? `${secondsToDateInput(customRange.from)} → ${secondsToDateInput(customRange.to)}`
      : null

  return (
    <div className="flex flex-col h-full w-full bg-slate-900/50 backdrop-blur-xl rounded-[2rem] p-5 border border-white/10 shadow-2xl">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4 z-10">
        <div className="flex items-center gap-3">
          <h3 className="text-[13px] uppercase tracking-wider font-semibold text-slate-200">Portföy Performansı</h3>
          {rangeLabel && (
            <span className="text-[11px] font-medium text-slate-400 bg-slate-800/5 px-2 py-0.5 rounded-full tabular-nums">
              {rangeLabel}
            </span>
          )}
        </div>

        <div className="relative flex items-center gap-2">
          <div className="flex space-x-1 bg-slate-800/5/50 p-1 rounded-lg">
            {RANGE_PRESETS.map((preset) => (
              <button
                key={preset}
                onClick={() => {
                  setMode(preset)
                  setRangeError('')
                }}
                className={`px-3 py-1.5 text-[11px] uppercase tracking-wider font-bold rounded-md transition-all duration-200 ${
                  mode === preset
                    ? 'bg-slate-800 shadow-sm text-emerald-600'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-200/50'
                }`}
              >
                {preset}
              </button>
            ))}
          </div>

          <button
            onClick={() => setPickerOpen((v) => !v)}
            className={`px-3 py-1.5 text-[11px] uppercase tracking-wider font-bold rounded-lg border transition-all duration-200 ${
              mode === 'custom'
                ? 'border-emerald-500/40 bg-emerald-500/20 text-emerald-600'
                : 'border-white/10 bg-slate-800 text-slate-400 hover:border-slate-300 hover:text-slate-200'
            }`}
          >
            Özel Aralık
          </button>

          {pickerOpen && (
            <div className="absolute right-0 top-full z-30 mt-2 flex w-[320px] flex-wrap items-end gap-3 rounded-xl border border-white/10 bg-slate-800 p-3 shadow-2xl">
              <div className="flex flex-1 flex-col gap-1">
                <label className="text-[10px] uppercase tracking-wider font-semibold text-slate-400">Başlangıç</label>
                <input
                  type="date"
                  value={fromInput}
                  min={minDate}
                  max={maxDate}
                  onChange={(e) => setFromInput(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-slate-800 px-2 py-1.5 text-xs tabular-nums text-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                />
              </div>
              <div className="flex flex-1 flex-col gap-1">
                <label className="text-[10px] uppercase tracking-wider font-semibold text-slate-400">Bitiş</label>
                <input
                  type="date"
                  value={toInput}
                  min={minDate}
                  max={maxDate}
                  onChange={(e) => setToInput(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-slate-800 px-2 py-1.5 text-xs tabular-nums text-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                />
              </div>

              <div className="flex w-full gap-2">
                <button
                  onClick={handleApplyCustomRange}
                  className="flex-1 rounded-lg bg-emerald-500/200 px-4 py-1.5 text-xs font-semibold text-white shadow-sm shadow-emerald-500/30 hover:bg-emerald-600 transition-colors"
                >
                  Uygula
                </button>
                <button
                  onClick={handleClearCustomRange}
                  className="flex-1 rounded-lg border border-white/10 bg-slate-800 px-4 py-1.5 text-xs font-semibold text-slate-400 hover:border-slate-300 hover:text-slate-200 transition-colors"
                >
                  Temizle
                </button>
              </div>

              {rangeError && <p className="w-full text-xs font-medium text-rose-500">{rangeError}</p>}
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 w-full h-full relative">
        <div ref={chartContainerRef} className="absolute inset-0" />
        {data.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-sm text-slate-400">Seçilen aralıkta veri bulunmuyor.</p>
          </div>
        )}
      </div>
    </div>
  )
}
