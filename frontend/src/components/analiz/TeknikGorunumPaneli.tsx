import { usePortfolioTechnical, TREND_LABEL } from '../../hooks/usePortfolioTechnical'

/**
 * Analiz > Risk — "Teknik Görünüm".
 *
 * Eğilim bir ÖLÇÜMDÜR ("50 günlük ortalamanın üzerinde"), bir tahmin değil.
 * Cümleler backend'de kuruluyor ve olduğu gibi gösteriliyor; sohbet de aynı
 * uç noktadan aynı cümleyi alıyor.
 *
 * Sayı ve değer AYRI yazılı. "3 pozisyonun 2'si" ile "değerin %95'i" farklı
 * iddialar ve zıt yönü gösterebilirler; ölçülen test portföyünde tam olarak
 * öyle. Tek bir yüzde vermek hangisinin kastedildiğini okunamaz yapardı.
 */
const TREND_TONE: Record<string, string> = {
    UPTREND: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300',
    DOWNTREND: 'border-rose-400/30 bg-rose-400/10 text-rose-300',
    SIDEWAYS: 'border-amber-400/30 bg-amber-400/10 text-amber-300',
    UNKNOWN: 'border-white/10 bg-white/5 text-slate-500',
}

function pct(value: number | null | undefined): string {
    if (value == null) return '—'
    const sign = value >= 0 ? '+' : '−'
    return `${sign}%${Math.abs(value).toLocaleString('tr-TR', {
        minimumFractionDigits: 1, maximumFractionDigits: 1,
    })}`
}

export default function TeknikGorunumPaneli() {
    const { data, summary, loading, error, rows, coverageNote } = usePortfolioTechnical()

    return (
        <div className="mb-6 rounded-[2rem] border border-white/10 bg-slate-900/50 p-5 backdrop-blur-xl">
            <h3 className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Teknik Görünüm
            </h3>

            {loading && <p className="text-sm text-slate-400">Ölçülüyor…</p>}
            {!loading && error && <p className="text-sm text-slate-400">{error}</p>}

            {!loading && !error && data && (
                <>
                    {/* Sayfanın ve sohbetin AYNI cümlesi */}
                    {summary?.statement && (
                        <p className="mb-4 text-sm leading-relaxed text-slate-200">
                            {summary.statement}
                        </p>
                    )}

                    {rows.length > 0 && (
                        <div className="overflow-x-auto">
                            <table className="w-full min-w-[520px] text-left text-sm">
                                <thead>
                                    <tr className="text-[11px] uppercase tracking-wider text-slate-500">
                                        <th className="pb-2 font-medium">Hisse</th>
                                        <th className="pb-2 font-medium">Eğilim</th>
                                        <th className="pb-2 text-right font-medium">50g ort.</th>
                                        <th className="pb-2 text-right font-medium">200g ort.</th>
                                        <th className="pb-2 text-right font-medium">52h konumu</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-white/5">
                                    {rows.map((row) => (
                                        <tr key={row.symbol}>
                                            <td className="py-2.5">
                                                <div className="font-semibold text-white">{row.symbol}</div>
                                                <div className="text-[11px] text-slate-500">{row.name}</div>
                                            </td>
                                            <td className="py-2.5">
                                                <span
                                                    className={`rounded-full border px-2 py-0.5 text-[11px] ${
                                                        TREND_TONE[row.signals.trend ?? 'UNKNOWN']
                                                    }`}
                                                >
                                                    {TREND_LABEL[row.signals.trend ?? 'UNKNOWN']}
                                                </span>
                                            </td>
                                            {/* `veri yok` değil `—`: alan aracın döndürdüğü
                                                bir alan ve o satırda ÖLÇÜLEMEDİ. */}
                                            <td className="py-2.5 text-right tabular-nums text-slate-300">
                                                {pct(row.signals.pct_from_sma_50)}
                                            </td>
                                            <td className="py-2.5 text-right tabular-nums text-slate-300">
                                                {pct(row.signals.pct_from_sma_200)}
                                            </td>
                                            <td className="py-2.5 text-right tabular-nums text-slate-300">
                                                {row.signals.week52_position_pct == null
                                                    ? '—'
                                                    : `%${row.signals.week52_position_pct.toFixed(0)}`}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {coverageNote && (
                        <p className="mt-3 text-xs text-amber-300/80">{coverageNote}</p>
                    )}
                    <p className="mt-3 text-xs text-slate-500">
                        Eğilim, fiyatın kendi hareketli ortalamalarına göre konumudur —
                        bir ölçümdür, gelecek hakkında bir iddia değildir.
                    </p>
                </>
            )}
        </div>
    )
}
