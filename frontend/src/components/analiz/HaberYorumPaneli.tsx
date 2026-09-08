import { DIGEST_WINDOWS, useNewsDigest } from '../../hooks/useNewsDigest'
import { formatDate } from '../../lib/datetime'

/**
 * Analiz > Genel Bakış — "Haberler ne anlama geliyor".
 *
 * Yanındaki `PortfoyHaberleri` başlıkları LİSTELİYOR ve yorumlamıyor; bu
 * panel yorumluyor. İkisi ayrı duruyor çünkü ayrı sorular ve ayrı
 * dayanaklar: biri yayımlanmış bir olgu, diğeri bir modelin yargısı. Aynı
 * kutuda göstermek, ikisini aynı ağırlıkta iki satır gibi okuturdu.
 *
 * **Cümleler SUNUCUDAN geliyor ve olduğu gibi yazılıyor.** Koşulluluk,
 * ölçüm ve çekince kodda çivili; burada yeniden kurulan bir cümle o çivinin
 * dışında kalırdı. Bu bileşende hesap yok: hangi satırın açık olduğu bile
 * hook'ta.
 *
 * Çekince koşulsuz ve SUNUCUDAN: arayüzde yazılı bir kopya, sunucudaki metin
 * değiştiğinde sessizce eskiyen ikinci bir çekince olurdu.
 */
const SCOPE_TR: Record<string, string> = {
    DIRECT: 'doğrudan',
    SPILLOVER: 'yansıma',
}

const DIRECTION_TR: Record<string, string> = {
    UP: 'Yükseliş yönünde',
    DOWN: 'Düşüş yönünde',
    NEUTRAL: 'Yön belirtmeyen',
}

export default function HaberYorumPaneli() {
    const state = useNewsDigest()

    return (
        <div className="mb-6 rounded-[2rem] border border-white/10 bg-slate-900/50 p-5 backdrop-blur-xl">
            <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Haberler Ne Anlama Geliyor
                </h3>
                <div className="flex gap-1">
                    {DIGEST_WINDOWS.map((window) => (
                        <button
                            key={window.hours}
                            type="button"
                            onClick={() => state.setHours(window.hours)}
                            className={`rounded-md px-2 py-1 text-[11px] ${
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

            {state.loading && <p className="text-sm text-slate-400">Yorumlar alınıyor…</p>}

            {/* Ulaşılamayan bir uç, ölçülmüş bir sessizlik DEĞİL. */}
            {!state.loading && state.error && (
                <p className="text-sm text-slate-400">{state.error}</p>
            )}

            {!state.loading && !state.error && (
                <>
                    <p className="mb-4 text-sm text-slate-200">{state.headline}</p>

                    <ul className="space-y-2">
                        {state.entries.map((entry) => (
                            <li
                                key={entry.symbol}
                                className="rounded-xl border border-white/5 bg-white/5 p-3"
                            >
                                <button
                                    type="button"
                                    onClick={() => state.toggle(entry.symbol)}
                                    className="w-full text-left"
                                >
                                    <p className="text-sm leading-relaxed text-slate-200">
                                        {entry.sentence}
                                    </p>
                                    <span className="mt-1 inline-block text-[11px] text-sky-400">
                                        {state.expanded === entry.symbol
                                            ? 'Gerekçeleri gizle'
                                            : `Gerekçeleri gör (${entry.reasons.length})`}
                                    </span>
                                </button>

                                {state.expanded === entry.symbol && (
                                    <ul className="mt-3 space-y-2 border-t border-white/5 pt-3">
                                        {entry.reasons.map((reason) => (
                                            <li key={reason.newsId} className="text-[13px]">
                                                <p className="text-slate-300">
                                                    {reason.mechanism}
                                                </p>
                                                <p className="mt-0.5 text-[11px] text-slate-500">
                                                    {DIRECTION_TR[reason.direction] ??
                                                        reason.direction}
                                                    {' · '}
                                                    {SCOPE_TR[reason.scope] ?? reason.scope}
                                                    {' · '}
                                                    {formatDate(new Date(reason.publishedAt), {
                                                        day: 'numeric',
                                                        month: 'long',
                                                    })}
                                                </p>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </li>
                        ))}
                    </ul>

                    {/* Koşulsuz. Kullanıcının okuduğu şey bir modelin yorumu. */}
                    <p className="mt-4 text-[11px] leading-relaxed text-slate-500">
                        {state.disclaimer}
                    </p>
                </>
            )}
        </div>
    )
}
