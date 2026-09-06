import { useState } from 'react'
import type { ScenarioFactor } from '../../api/client'
import { FACTOR_LABELS, useScenario } from '../../hooks/useScenario'
import { formatMoney } from '../../lib/money'
import { formatDate } from '../../lib/datetime'

/**
 * Analiz > Senaryo — "bir faktör oynasaydı" ve "gerçekte ne oldu".
 *
 * İkisi de ÖLÇÜM. Cümleyi backend kuruyor ve buraya olduğu gibi geliyor:
 * çekincesiyle birlikte tek parça, çünkü ikiye bölüp ilk yarısını göstermek
 * koşulu düşürüp iddiayı bırakmak olur.
 *
 * Faiz seçicide YOK. Sistemde faiz serisi tutulmuyor ve seçeneği koyup 422
 * göstermek, kullanıcıya var olmayan bir yetenek vaat etmek olurdu. Panel
 * bunu bir kez, açıkça söylüyor.
 */
const FACTORS = Object.keys(FACTOR_LABELS) as ScenarioFactor[]
const SHOCKS = [-20, -10, -5, 5, 10, 20]

function pct(value: number | null | undefined, digits = 1): string {
    if (value == null) return '—'
    const sign = value >= 0 ? '+' : '−'
    return `${sign}%${Math.abs(value).toLocaleString('tr-TR', {
        minimumFractionDigits: digits, maximumFractionDigits: digits,
    })}`
}

export default function SenaryoPaneli({ lookback }: { lookback: string }) {
    const [factor, setFactor] = useState<ScenarioFactor>('USDTRY')
    const [shock, setShock] = useState(10)
    const {
        result, loading, error, isWeakFit, run, sensitivity,
        stress, stressLoading, stressError, replayRows, worstDays,
    } = useScenario(lookback)

    return (
        <>
            <div className="rounded-[2rem] border border-white/10 bg-slate-900/50 p-5 backdrop-blur-xl">
                <h3 className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Koşullu Senaryo
                </h3>

                <div className="mb-4 flex flex-wrap gap-2">
                    {FACTORS.map((key) => (
                        <button
                            key={key}
                            onClick={() => setFactor(key)}
                            className={`rounded-full border px-3 py-1 text-xs ${
                                key === factor
                                    ? 'border-sky-400/40 bg-sky-400/10 text-sky-200'
                                    : 'border-white/10 bg-white/5 text-slate-400 hover:text-slate-200'
                            }`}
                        >
                            {FACTOR_LABELS[key]}
                        </button>
                    ))}
                </div>

                <div className="mb-4 flex flex-wrap items-center gap-2">
                    {SHOCKS.map((value) => (
                        <button
                            key={value}
                            onClick={() => setShock(value)}
                            className={`rounded-lg border px-2.5 py-1 text-xs tabular-nums ${
                                value === shock
                                    ? 'border-sky-400/40 bg-sky-400/10 text-sky-200'
                                    : 'border-white/10 bg-white/5 text-slate-400 hover:text-slate-200'
                            }`}
                        >
                            {pct(value, 0)}
                        </button>
                    ))}
                    <button
                        onClick={() => void run(factor, shock)}
                        disabled={loading}
                        className="ml-auto rounded-lg bg-sky-500/90 px-4 py-1.5 text-xs font-semibold text-white hover:bg-sky-400 disabled:opacity-50"
                    >
                        {loading ? 'Hesaplanıyor…' : 'Senaryoyu hesapla'}
                    </button>
                </div>

                {error && <p className="text-sm text-slate-400">{error}</p>}

                {!error && result && sensitivity && (
                    <>
                        {/* Cümle backend'de kuruldu; sohbet de aynısını alıyor. */}
                        <p className="text-sm leading-relaxed text-slate-200">
                            {result.statement}
                        </p>

                        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
                            {[
                                { label: 'Duyarlılık (beta)',
                                  value: sensitivity.beta.toFixed(2) },
                                { label: 'Açıklama gücü',
                                  value: sensitivity.r_squared == null
                                      ? '—'
                                      : `%${(sensitivity.r_squared * 100).toFixed(1)}` },
                                { label: 'Tahmini etki',
                                  value: pct(result.estimated_impact_pct) },
                                { label: 'Tutar olarak',
                                  value: result.estimated_impact_value == null
                                      ? '—'
                                      : formatMoney(result.estimated_impact_value, 'TRY') },
                            ].map((cell) => (
                                <div key={cell.label}>
                                    <div className="text-[11px] uppercase tracking-wider text-slate-400">
                                        {cell.label}
                                    </div>
                                    <div className="mt-1 text-lg font-bold tabular-nums text-white">
                                        {cell.value}
                                    </div>
                                </div>
                            ))}
                        </div>

                        {/* Zayıf uyum sayıyı silmiyor, ne kadar taşıdığını söylüyor. */}
                        {isWeakFit && (
                            <p className="mt-3 rounded-xl border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-300/90">
                                Bu faktör portföyünüzün geçmiş hareketinin küçük bir kısmını
                                açıklıyor; duyarlılık zayıf bir ilişkiye dayanıyor.
                            </p>
                        )}

                        {/* Gizlenmiş bir varsayım, olmayan bir kesinlik üretir. */}
                        <ul className="mt-3 flex flex-col gap-1">
                            {(result.assumptions ?? []).map((line) => (
                                <li key={line} className="text-xs text-slate-500">• {line}</li>
                            ))}
                            {(result.warnings ?? []).map((line) => (
                                <li key={line} className="text-xs text-amber-300/80">• {line}</li>
                            ))}
                        </ul>
                    </>
                )}

                <p className="mt-4 text-xs text-slate-500">
                    Faiz senaryosu ölçülemiyor: bu sistemde faiz oranının günlük bir
                    serisi tutulmuyor, dolayısıyla portföyün faize duyarlılığı
                    hesaplanamıyor.
                </p>
            </div>

            <div className="rounded-[2rem] border border-white/10 bg-slate-900/50 p-5 backdrop-blur-xl">
                <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Stres Testi
                </h3>
                <p className="mb-4 text-xs text-slate-500">
                    Varsayımsal değil: aşağıdaki günler gerçekten oldu.
                </p>

                {stressLoading && <p className="text-sm text-slate-400">Ölçülüyor…</p>}
                {!stressLoading && stressError && (
                    <p className="text-sm text-slate-400">{stressError}</p>
                )}

                {!stressLoading && !stressError && stress && (
                    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                        <div>
                            <div className="mb-2 text-[11px] uppercase tracking-wider text-slate-400">
                                En kötü günleriniz
                            </div>
                            {worstDays.length === 0 ? (
                                <p className="text-sm text-slate-400">
                                    Bu pencerede getiri serisi oluşturacak kadar geçmiş yok.
                                </p>
                            ) : (
                                <ul className="flex flex-col divide-y divide-white/5">
                                    {worstDays.map((row) => (
                                        <li key={row.date} className="flex justify-between py-2 text-sm">
                                            <span className="text-slate-300">
                                                {formatDate(row.date, {
                                                    day: 'numeric', month: 'long', year: 'numeric',
                                                })}
                                            </span>
                                            <span className="tabular-nums font-semibold text-rose-300">
                                                {pct(row.return_pct, 2)}
                                            </span>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </div>

                        <div>
                            <div className="mb-2 text-[11px] uppercase tracking-wider text-slate-400">
                                Faktörler en sert oynadığında
                            </div>
                            {replayRows.length === 0 ? (
                                <p className="text-sm text-slate-400">
                                    Hiçbir faktör için ortak işlem günü ölçmeye yetmedi.
                                </p>
                            ) : (
                                <ul className="flex flex-col divide-y divide-white/5">
                                    {replayRows.map((row) => (
                                        <li key={row.symbol} className="py-2 text-sm">
                                            <div className="flex justify-between">
                                                <span className="text-slate-300">{row.name}</span>
                                                <span className="tabular-nums text-slate-400">
                                                    {row.days} işlem günü
                                                </span>
                                            </div>
                                            <div className="mt-0.5 flex justify-between text-xs">
                                                <span className="text-slate-500">
                                                    {formatDate(row.start)} –{' '}
                                                    {formatDate(row.end)}
                                                </span>
                                                <span className="tabular-nums">
                                                    <span className="text-slate-400">faktör </span>
                                                    <span className="font-semibold text-slate-200">
                                                        {pct(row.factor)}
                                                    </span>
                                                    <span className="text-slate-400"> · portföy </span>
                                                    <span className="font-semibold text-slate-200">
                                                        {pct(row.portfolio)}
                                                    </span>
                                                </span>
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                            )}
                            {/* Eş zamanlılık nedensellik değil. */}
                            <p className="mt-3 text-xs text-slate-500">
                                İki hareket aynı günlerde ölçüldü; bu, birinin diğerine yol
                                açtığı anlamına gelmez.
                            </p>
                        </div>
                    </div>
                )}
            </div>
        </>
    )
}
