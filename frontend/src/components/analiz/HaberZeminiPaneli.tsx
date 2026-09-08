import {
    IMPACT_WINDOWS,
    coverageStatement,
    moveStatement,
    useNewsImpact,
} from '../../hooks/useNewsImpact'
import { formatDate } from '../../lib/datetime'

/**
 * Analiz > Genel Bakış — "Haberlerin ölçülen zemini".
 *
 * **Burada yorum YOK.** Panel sayıyor ve ölçüyor: kaç haber, kaçı bildirim,
 * hisse ne yaptı, o hissede normal bir hareket ne kadar. Haberlerin ne
 * anlama geldiğine dair okuma sohbet turunda kuruluyor ve orada uygunluk
 * kapısından geçiyor; aynı okumayı burada ikinci kez kurmak, o kapıdan
 * geçmeyen bir kopya üretirdi.
 *
 * Bir hareket ancak KENDİ aralığına karşı büyük: cümle ikisini birlikte
 * yazıyor ve tipik hareket ölçülemediğinde hiç yazılmıyor.
 */
export default function HaberZeminiPaneli() {
    const state = useNewsImpact()
    const coverage = coverageStatement(state.coverage)

    return (
        <div className="mb-6 rounded-[2rem] border border-white/10 bg-slate-900/50 p-5 backdrop-blur-xl">
            <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Haberlerin Ölçülen Zemini
                </h3>
                <div className="flex gap-1">
                    {IMPACT_WINDOWS.map((window) => (
                        <button
                            key={window.days}
                            type="button"
                            onClick={() => state.setDays(window.days)}
                            className={`rounded-md px-2 py-1 text-[11px] ${
                                state.days === window.days
                                    ? 'bg-white/15 text-white'
                                    : 'bg-white/5 text-slate-400'
                            }`}
                        >
                            {window.label}
                        </button>
                    ))}
                </div>
            </div>

            {state.loading && <p className="text-sm text-slate-400">Ölçümler alınıyor…</p>}

            {/* Ulaşılamayan bir uç, ölçülmüş bir sessizlik DEĞİL. */}
            {!state.loading && state.error && (
                <p className="text-sm text-slate-400">{state.error}</p>
            )}

            {!state.loading && !state.error && (
                <>
                    <ul className="space-y-2">
                        {state.rows.map((row) => (
                            <li
                                key={row.symbol}
                                className="rounded-xl border border-white/5 bg-white/5 p-3"
                            >
                                <div className="flex flex-wrap items-baseline justify-between gap-2">
                                    <span className="text-sm font-medium text-slate-200">
                                        {row.symbol}
                                        {row.sector && (
                                            <span className="ml-2 text-[11px] text-slate-500">
                                                {row.sector}
                                            </span>
                                        )}
                                    </span>
                                    <span className="text-[11px] text-slate-400">
                                        {row.news_count} haber
                                        {row.filing_count > 0 &&
                                            `, ${row.filing_count} bildirim`}
                                    </span>
                                </div>

                                {/* Ölçülemediğinde HİÇ yazılmıyor: büyüklük
                                    hakkında söylenecek bir şey yok. */}
                                {moveStatement(row) && (
                                    <p className="mt-1 text-[13px] leading-relaxed text-slate-300">
                                        {moveStatement(row)}
                                    </p>
                                )}

                                {row.articles.length > 0 && (
                                    <button
                                        type="button"
                                        onClick={() => state.toggle(row.symbol)}
                                        className="mt-1 text-[11px] text-sky-400"
                                    >
                                        {state.expanded === row.symbol
                                            ? 'Başlıkları gizle'
                                            : `Başlıklar (${row.articles.length})`}
                                    </button>
                                )}

                                {state.expanded === row.symbol && (
                                    <ul className="mt-2 space-y-1 border-t border-white/5 pt-2">
                                        {row.articles.map((article) => (
                                            <li key={article.id} className="text-[12px]">
                                                <p className="text-slate-300">
                                                    {article.title}
                                                </p>
                                                <p className="mt-0.5 text-[11px] text-slate-500">
                                                    {article.source}
                                                    {article.is_filing && ' · bildirim'}
                                                    {' · '}
                                                    {formatDate(
                                                        new Date(article.published_at),
                                                        { day: 'numeric', month: 'long' },
                                                    )}
                                                </p>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </li>
                        ))}
                    </ul>

                    {coverage && (
                        <p className="mt-4 text-[11px] leading-relaxed text-slate-500">
                            {coverage}
                        </p>
                    )}
                </>
            )}
        </div>
    )
}
