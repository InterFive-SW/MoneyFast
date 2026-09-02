import { usePortfolioNews } from '../../hooks/usePortfolioNews'

/**
 * Analiz > Genel Bakış — "Portföyünüze dokunan haberler".
 *
 * Haberler LİSTELENİR VE TARİHLENİR, yorumlanmaz. Bir başlığın olumlu ya da
 * olumsuz olduğu bir piyasa görüşüdür ve bu ürünün görüş tutma izni yok; o
 * yüzden burada duygu rozeti, önem sıralaması ya da "bu haber şu yüzden
 * önemli" cümlesi yok. Başlık, kaynak, tarih ve hangi hisseye dokunduğu.
 *
 * Haber yoksa panel KAYBOLMUYOR, boş olduğunu söylüyor. Sessizce kaybolan bir
 * panel, veri yokluğunu özellik yokluğu gibi gösterir — kullanıcı hiç haber
 * çekilmediğini mi yoksa hisselerine dair bir şey yayımlanmadığını mı
 * bilemez.
 */
function timeLabel(item: { time: string; publishedAt: string }): string {
    const stamp = new Date(item.publishedAt)
    return `${item.time} · ${stamp.toLocaleDateString('tr-TR', {
        day: 'numeric', month: 'long',
    })}`
}

export default function PortfoyHaberleri() {
    const { news, loading, error, quietSymbols, hasHoldings, heldLabel } = usePortfolioNews()

    return (
        <div className="mb-6 rounded-[2rem] border border-white/10 bg-slate-900/50 p-5 backdrop-blur-xl">
            <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Portföyünüze Dokunan Haberler
                </h3>
                {news && (
                    <span className="text-[11px] text-slate-500">son {news.windowDays} gün</span>
                )}
            </div>

            {loading && <p className="text-sm text-slate-400">Haberler alınıyor…</p>}

            {/* Ulaşılamayan bir uç, ölçülmüş bir sessizlik DEĞİL. */}
            {!loading && error && <p className="text-sm text-slate-400">{error}</p>}

            {!loading && !error && news && (
                <>
                    {!hasHoldings && (
                        <p className="text-sm text-slate-400">
                            Portföyünüzde hisse yok. Bir pozisyon açtığınızda o hisseye dair
                            yayımlananlar burada görünür.
                        </p>
                    )}

                    {hasHoldings && (
                        <div className="mb-4 flex flex-wrap gap-2">
                            {news.symbols.map((row) => (
                                <span
                                    key={row.symbol}
                                    title={row.name}
                                    className={`rounded-full border px-2.5 py-1 text-[11px] tabular-nums ${
                                        row.count > 0
                                            ? 'border-sky-400/30 bg-sky-400/10 text-sky-200'
                                            : 'border-white/10 bg-white/5 text-slate-500'
                                    }`}
                                >
                                    {row.symbol} · {row.count}
                                </span>
                            ))}
                        </div>
                    )}

                    {hasHoldings && news.items.length === 0 && (
                        <p className="text-sm text-slate-400">
                            Bu pencerede hisselerinize dair bir haber eşleşmedi.
                        </p>
                    )}

                    <ul className="flex flex-col divide-y divide-white/5">
                        {news.items.map((item) => (
                            <li key={item.id} className="py-3 first:pt-0 last:pb-0">
                                <a
                                    href={item.url}
                                    target="_blank"
                                    rel="noreferrer noopener"
                                    className="text-sm font-medium leading-snug text-slate-100 hover:text-sky-300"
                                >
                                    {item.title}
                                </a>
                                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-500">
                                    {/* Haber birden çok şirketi anabilir; burada
                                        YALNIZCA kullanıcının sahip olduğu yazılı,
                                        yani listede durma sebebi. */}
                                    <span className="font-semibold text-sky-300/80">
                                        {heldLabel(item)}
                                    </span>
                                    <span>·</span>
                                    <span>{item.source}</span>
                                    <span>·</span>
                                    <span>{timeLabel(item)}</span>
                                </div>
                            </li>
                        ))}
                    </ul>

                    {hasHoldings && quietSymbols.length > 0 && news.items.length > 0 && (
                        <p className="mt-3 text-xs text-slate-500">
                            {quietSymbols.join(', ')} için bu pencerede eşleşen haber yok.
                        </p>
                    )}
                </>
            )}
        </div>
    )
}
