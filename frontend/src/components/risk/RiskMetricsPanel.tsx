import {
    METRIC_COPY,
    NOT_MEASURED,
    benchmarkName,
    describeDrawdown,
    describeLossEstimate,
    formatMetric,
    reliabilityNotice,
} from '../../lib/riskFormat'
import { formatMoney } from '../../lib/money'
import Term from '../common/Term'

/**
 * Ölçülen risk metrikleri.
 *
 * `GET /api/risk/profile` bu bloğu baştan beri döndürüyordu ve sayfa onu
 * çekip hiçbir yerde göstermiyordu. Motor VaR'ı, CVaR'ı, Sharpe'ı, betayı ve
 * düşüşün tepe/dip tarihlerini gerçek mumlardan hesaplıyor; buraya kadar
 * taşınıp atılıyorlardı.
 *
 * Biçimlendirme ve metinler `lib/riskFormat` içinde: kapsama kapısı orayı
 * sayıyor, JSX'i saymıyor.
 */
interface RiskMetricsPanelProps {
    /** Ölçülen betanın hangi endekse göre olduğu. */
    assumptions?: unknown
    metrics: Record<string, unknown>
    currency?: string
}

/** Kart -> sözlük anahtarı. Tanımlar `lib/glossary.ts`'te, tek kaynakta. */
const CARD_ORDER: { name: string; term: string }[] = [
    { name: 'volatility_annualized', term: 'volatility' },
    { name: 'downside_deviation_annualized', term: 'downside_deviation' },
    { name: 'sharpe_ratio', term: 'sharpe' },
    { name: 'beta', term: 'beta' },
    { name: 'correlation_to_benchmark', term: 'correlation' },
]

export default function RiskMetricsPanel({ metrics, currency, assumptions }: RiskMetricsPanelProps) {
    const drawdown = describeDrawdown(metrics.max_drawdown)
    const varView = describeLossEstimate(metrics.var, 'var')
    const cvarView = describeLossEstimate(metrics.cvar, 'cvar')
    const notice = reliabilityNotice(metrics.data_quality)
    // Beta ve korelasyon her zaman BİR ŞEYE göredir ve o şeyin adı
    // ekranda hiç geçmiyordu: XU100 varsayılan olarak kullanılıyor ve
    // kullanıcı neyle kıyaslandığını bilmiyordu.
    const indexName = benchmarkName(
        (assumptions as { benchmark_symbol?: unknown } | undefined)?.benchmark_symbol,
    )
    const RELATIVE = new Set(['beta', 'correlation_to_benchmark'])

    return (
        <div className="flex flex-col rounded-2xl border border-white/10 bg-slate-900/50 p-6 shadow-2xl backdrop-blur-xl">
            <h3 className="mb-1 text-base font-semibold text-white">Ölçülen Risk Metrikleri</h3>
            <p className="mb-4 text-xs text-slate-400">
                Hepsi geçmiş fiyat hareketlerinden hesaplandı. Geleceğe dair bir tahmin değildir.
            </p>

            {notice && (
                <p className="mb-4 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs leading-relaxed text-amber-200">
                    <span className="flex-1">{notice}</span>
                    <Term termKey="reliability" align="right" />
                </p>
            )}

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {CARD_ORDER.map(({ name, term }) => {
                    const copy = METRIC_COPY[name]
                    const raw = metrics[name]
                    const value = typeof raw === 'number' ? raw : null
                    return (
                        <div key={name} className="rounded-xl bg-white/5 p-4">
                            <p className="flex items-center gap-1.5 text-xs font-medium text-slate-400">
                                {copy.label}
                                <Term termKey={term} />
                            </p>
                            <p
                                className={`mt-1 text-xl font-semibold ${
                                    value === null ? 'text-slate-500' : 'text-white'
                                }`}
                            >
                                {formatMetric(name, value)}
                            </p>
                            <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
                                {copy.hint}
                                {indexName && RELATIVE.has(name) && (
                                    <span className="text-slate-400"> {indexName}’e göre ölçüldü.</span>
                                )}
                            </p>
                        </div>
                    )
                })}
            </div>

            {(varView || cvarView) && (
                <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {varView && (
                        <div className="rounded-xl bg-white/5 p-4">
                            <p className="flex items-center gap-1.5 text-xs font-medium text-slate-400">
                                Günlük kayıp eşiği ({varView.confidence} güven)
                                <Term termKey="var" />
                            </p>
                            <p className="mt-1 text-xl font-semibold text-white">
                                {varView.fraction}
                                {varView.amount !== null && (
                                    <span className="ml-2 text-sm font-normal text-slate-400">
                                        ≈ {formatMoney(varView.amount, currency)}
                                    </span>
                                )}
                            </p>
                            <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
                                {varView.hint}
                            </p>
                        </div>
                    )}
                    {cvarView && (
                        <div className="rounded-xl bg-white/5 p-4">
                            <p className="flex items-center gap-1.5 text-xs font-medium text-slate-400">
                                Eşik aşıldığında ortalama kayıp
                                <Term termKey="cvar" align="right" />
                            </p>
                            <p className="mt-1 text-xl font-semibold text-white">
                                {cvarView.fraction}
                                {cvarView.amount !== null && (
                                    <span className="ml-2 text-sm font-normal text-slate-400">
                                        ≈ {formatMoney(cvarView.amount, currency)}
                                    </span>
                                )}
                            </p>
                            <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
                                {cvarView.hint}
                            </p>
                        </div>
                    )}
                </div>
            )}

            {drawdown && (
                <div className="mt-4 rounded-xl bg-white/5 p-4">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <p className="flex items-center gap-1.5 text-xs font-medium text-slate-400">
                            En derin düşüş
                            <Term termKey="max_drawdown" />
                        </p>
                        <p className="text-xl font-semibold text-rose-400">−{drawdown.depth}</p>
                    </div>
                    {/* Tepe → dip → toparlanma. Tarihler zaten hesaplanıyordu ve
                        hiçbir yerde görünmüyordu; bir düşüşün ne zaman
                        yaşandığı, ne kadar olduğu kadar anlamlı. */}
                    <ol className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-0">
                        <li className="flex-1 border-l-2 border-emerald-500/60 pl-3 sm:border-l-0 sm:border-t-2 sm:pl-0 sm:pt-2">
                            <span className="block text-[11px] text-slate-500">Zirve</span>
                            <span className="text-sm text-slate-200">
                                {drawdown.peak ?? NOT_MEASURED}
                            </span>
                        </li>
                        <li className="flex-1 border-l-2 border-rose-500/60 pl-3 sm:border-l-0 sm:border-t-2 sm:pl-0 sm:pt-2">
                            <span className="block text-[11px] text-slate-500">Dip</span>
                            <span className="text-sm text-slate-200">
                                {drawdown.trough ?? NOT_MEASURED}
                            </span>
                        </li>
                        <li className="flex-1 border-l-2 border-slate-600 pl-3 sm:border-l-0 sm:border-t-2 sm:pl-0 sm:pt-2">
                            <span className="block text-[11px] text-slate-500">Toparlanma</span>
                            <span className="text-sm text-slate-200">
                                {/* "Toparlanma yok" ile "veri yok" ayrı şeyler. */}
                                {drawdown.recovered ? drawdown.recovery : 'henüz toparlanmadı'}
                            </span>
                        </li>
                    </ol>
                    {drawdown.durationDays !== null && (
                        <p className="mt-3 text-[11px] text-slate-500">
                            Zirveden dibe {drawdown.durationDays} işlem günü geçti.
                        </p>
                    )}
                </div>
            )}
        </div>
    )
}
