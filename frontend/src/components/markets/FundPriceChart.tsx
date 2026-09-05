import { useEffect, useRef, useState } from 'react'
import { CandlestickSeries, ColorType, createChart } from 'lightweight-charts'
import type { IChartApi, ISeriesApi } from 'lightweight-charts'

import { FUND_RANGES, useFundCandles, type FundRange } from '../../hooks/useFundCandles'

/**
 * Fonun mum grafigi.
 *
 * Bir donem duz cizgiydi ve ondan once tamamen SENTETIKTI
 * (`comparisonSeries.ts`, seed'li rastgele yuruyus). Simdi gercek NAV
 * serisinden.
 *
 * Mumlar KOVALANMIS: fon gunde tek fiyat yayimliyor, dolayisiyla gunluk bir
 * mumun acilis/yuksek/dusuk/kapanisi ayni sayi olurdu -- yassi bir cizgi.
 * Sunucu haftalik ya da aylik kovaliyor ve kova genisligi baslikta yaziyor:
 * kullanici baktigi cubugun bir haftayi mi bir ayi mi ozetledigini bilmeli.
 *
 * Kurulum `InstrumentCandleChart` ile ayni.
 */

const BUCKET_TR: Record<string, string> = { week: 'haftalik', month: 'aylik' }

export default function FundPriceChart({ code }: { code: string }) {
    const [range, setRange] = useState<FundRange>('3A')
    const { candles, bucket, loading, error } = useFundCandles(code, range)

    const containerRef = useRef<HTMLDivElement>(null)
    const chartRef = useRef<IChartApi | null>(null)
    const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)

    useEffect(() => {
        const container = containerRef.current
        if (!container) return

        const chart = createChart(container, {
            layout: {
                background: { type: ColorType.Solid, color: 'transparent' },
                textColor: '#94a3b8',
                attributionLogo: false,
            },
            grid: {
                vertLines: { color: 'rgba(148, 163, 184, 0.10)' },
                horzLines: { color: 'rgba(148, 163, 184, 0.10)' },
            },
            rightPriceScale: { borderVisible: false },
            timeScale: { borderVisible: false },
            crosshair: { mode: 0 },
            width: container.clientWidth > 0 ? container.clientWidth : 600,
            height: container.clientHeight > 0 ? container.clientHeight : 320,
        })
        chartRef.current = chart
        seriesRef.current = chart.addSeries(CandlestickSeries, {
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        })

        const observer = new ResizeObserver((entries) => {
            const rect = entries[0]?.contentRect
            if (rect && rect.width > 0 && rect.height > 0) {
                chart.applyOptions({ width: rect.width, height: rect.height })
            }
        })
        observer.observe(container)

        return () => {
            observer.disconnect()
            chart.remove()
            chartRef.current = null
            seriesRef.current = null
        }
    }, [])

    useEffect(() => {
        if (!seriesRef.current || !chartRef.current) return
        seriesRef.current.setData(candles)
        chartRef.current.timeScale().fitContent()
    }, [candles])

    return (
        <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Fiyat Grafigi
                    {/* Kova genisligi baslikta: fon gunde tek fiyat
                        yayimliyor ve kullanici cubugun neyi ozetledigini
                        bilmeli. */}
                    {bucket && (
                        <span className="ml-2 normal-case tracking-normal text-slate-500">
                            (₺ · {BUCKET_TR[bucket] ?? bucket} mum)
                        </span>
                    )}
                </h3>
                <div className="flex rounded-lg border border-white/10 bg-slate-900/60 p-0.5">
                    {FUND_RANGES.map((option) => (
                        <button
                            key={option}
                            type="button"
                            onClick={() => setRange(option)}
                            aria-pressed={range === option}
                            className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
                                range === option
                                    ? 'bg-white/10 text-white'
                                    : 'text-slate-400 hover:text-slate-200'
                            }`}
                        >
                            {option}
                        </button>
                    ))}
                </div>
            </div>

            {/* Kap HER ZAMAN duruyor: kosullu render, lightweight-charts
                kurulumunu her yukleme turunda sokup yeniden kurardi. */}
            <div ref={containerRef} className="h-[320px] w-full" />

            {loading && <p className="mt-2 text-xs text-slate-500">Grafik yukleniyor…</p>}
            {!loading && error && <p className="mt-2 text-xs text-rose-400">{error}</p>}
            {!loading && !error && candles.length === 0 && (
                <p className="mt-2 text-xs text-slate-400">
                    Bu fon icin fiyat serisi henuz alinmadi.
                </p>
            )}
        </div>
    )
}
