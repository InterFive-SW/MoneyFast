import { Link } from 'react-router-dom'

import { DIGEST_WINDOWS, useNewsImpactSummary } from '../../hooks/useNewsDigest'

/**
 * Piyasalar — "Haberler hangi enstrümanı etkiliyor".
 *
 * Portföyden bağımsız: bu ekranın sorusu "bugün piyasada ne konuşuluyor".
 * Yanındaki `NewsWidget` başlıkları listeliyor, bu kart onların hangi
 * enstrümana hangi yönde dokunduğunu söylüyor.
 *
 * Sıralama yorum SAYISINA göre ve bu bir cazibe sıralaması DEĞİL: bir
 * enstrümanın listede üstte olması, hakkında çok konuşulduğu anlamına gelir.
 * `YonTaramasi` ile aynı kural -- "en iyi" dili yok, çekince kalıcı.
 *
 * Burada ölçüm cümlesi YOK: fiyat ölçümü sembolün kendi sayfasında. On iki
 * enstrüman için mum okumak, kullanıcının hiç sormadığı bir iş olurdu.
 */
export default function HaberEtkiKarti() {
    const state = useNewsImpactSummary(24, 8)

    return (
        <div className="flex h-full flex-col rounded-2xl border border-white/10 bg-slate-900/50 p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-sm font-semibold text-white">Haberler neyi etkiliyor</h3>
                <div className="flex gap-1">
                    {DIGEST_WINDOWS.map((window) => (
                        <button
                            key={window.hours}
                            type="button"
                            onClick={() => state.setHours(window.hours)}
                            className={`rounded-md px-2 py-1 text-[10px] ${
                                state.hours === window.hours
                                    ? 'bg-white/15 text-white'
                                    : 'bg-white/5 text-slate-400'
                            }`}
                        >
                            {window.label}
                        </button>
                    ))}
                </div>
            </div>

            {state.loading && <p className="mt-3 text-xs text-slate-400">Yükleniyor…</p>}
            {state.error && <p className="mt-3 text-xs text-rose-400">{state.error}</p>}
            {!state.loading && !state.error && state.entries.length === 0 && (
                <p className="mt-3 text-xs text-slate-400">
                    Bu pencerede yorumlanmış bir haber yok.
                </p>
            )}

            <ul className="mt-3 flex-1 space-y-2 overflow-y-auto">
                {state.entries.map((entry) => (
                    <li key={entry.symbol} className="border-b border-white/5 pb-2">
                        <Link
                            to={`/investment/hisseler/${entry.symbol}`}
                            className="text-xs font-medium text-slate-200 hover:text-white"
                        >
                            {entry.symbol}
                        </Link>
                        <p className="mt-0.5 text-[11px] leading-relaxed text-slate-400">
                            {entry.sentence}
                        </p>
                        <button
                            type="button"
                            onClick={() => state.toggle(entry.symbol)}
                            className="mt-1 text-[10px] text-sky-400"
                        >
                            {state.expanded === entry.symbol ? 'Gizle' : 'Neden'}
                        </button>
                        {state.expanded === entry.symbol && (
                            <ul className="mt-1 space-y-1">
                                {entry.reasons.map((reason) => (
                                    <li
                                        key={reason.newsId}
                                        className="text-[11px] leading-relaxed text-slate-300"
                                    >
                                        {reason.mechanism}
                                    </li>
                                ))}
                            </ul>
                        )}
                    </li>
                ))}
            </ul>

            {/* Koşulsuz ve sunucudan. */}
            {state.disclaimer && (
                <p className="mt-3 text-[10px] leading-relaxed text-slate-500">
                    {state.disclaimer}
                </p>
            )}
        </div>
    )
}
