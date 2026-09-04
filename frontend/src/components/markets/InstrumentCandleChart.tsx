import { useEffect, useRef, useState } from 'react'
import { CandlestickSeries, ColorType, createChart } from 'lightweight-charts'
import type { IChartApi, ISeriesApi } from 'lightweight-charts'

import { CANDLE_RANGES, useCandles, type CandleRangeKey } from '../../hooks/useCandles'
import { currencySymbol } from '../../lib/money'

/**
 * Tek bir enstrümanın mum grafiği.
 *
 * Hisse detay sayfasında hiç grafik yoktu: beş sekme, bir istatistik ızgarası
 * ve metin hâlinde teknik görünüm. Kullanıcı tıkladığı satırın nasıl
 * davrandığını yalnızca günlük yüzdeden okuyabiliyordu.
 *
 * Veri `market_candles`'tan geliyor -- anlık fiyattan DEĞİL. İkisi ayrı seri
 * ve bu deponun kuralı: grafikler mumu okur, anlık fiyat asla oradan gelmez.
 *
 * Kurulum `PortfolioPerformanceChart` ile aynı; ayrı bir bileşen çünkü orası
 * portföyün kendi serisini, burası enstrümanın serisini çiziyor ve ikisi
 * farklı sebeplerle değişir.
 */
export default function InstrumentCandleChart({ symbol }: { symbol: string }) {
    const [range, setRange] = useState<CandleRangeKey>('3A')
    const bars = CANDLE_RANGES.find((entry) => entry.key === range)!.bars
    const { candles, currency, loading, error } = useCandles(symbol, bars)

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
                    Fiyat Grafiği
                    {/* Para birimi başlıkta, çünkü eksende yalnızca sayı var ve
                        bir fiyat birimi olmadan taşınmaz. */}
                    {currency && (
                        <span className="ml-2 normal-case tracking-normal text-slate-500">
                            ({currencySymbol(currency)})
                        </span>
                    )}
                </h3>
                <div className="flex rounded-lg border border-white/10 bg-slate-900/60 p-0.5">
                    {CANDLE_RANGES.map((option) => (
                        <button
                            key={option.key}
                            type="button"
                            onClick={() => setRange(option.key)}
                            aria-pressed={range === option.key}
                            className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
                                range === option.key
                                    ? 'bg-white/10 text-white'
                                    : 'text-slate-400 hover:text-slate-200'
                            }`}
                        >
                            {option.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Grafik kabı HER ZAMAN duruyor: koşullu render, lightweight-charts
                kurulumunu her yükleme turunda söküp yeniden kurardı. */}
            <div ref={containerRef} className="h-[320px] w-full" />

            {loading && <p className="mt-2 text-xs text-slate-500">Grafik yükleniyor…</p>}
            {!loading && error && <p className="mt-2 text-xs text-slate-400">{error}</p>}
            {!loading && !error && candles.length === 0 && (
                <p className="mt-2 text-xs text-slate-400">
                    Bu enstrüman için mum verisi yok.
                </p>
            )}
        </div>
    )
}
