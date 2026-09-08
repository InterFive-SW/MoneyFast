import type { NewsImpactWidgetPayload } from '../../types/chat'

/**
 * Haber okumasının ÖLÇÜLEN zemini, sohbette.
 *
 * **Yorum burada YOK ve olmamalı.** Okuma metinde duruyor ve orada uygunluk
 * kapısından geçti. Bir widget metnin yanında ama metinden BAĞIMSIZ
 * okunuyor: kullanıcı tabloyu okuyup paragrafı atlayabilir, o yüzden
 * tabloda duran her şey tek başına doğru olmak zorunda. Bir kanaat cümlesi
 * bu koşulu sağlamıyor, çünkü çekincesi paragrafta kalıyor.
 *
 * Gerçekleşen hareket, tipik hareketin YANINDA çiziliyor: bir hareket ancak
 * kendi aralığına karşı büyük ya da küçük.
 */
function pct(value: number | null): string {
    if (value === null) return '—'
    return `%${Math.abs(value).toLocaleString('tr-TR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}`
}

export default function NewsImpactWidget({
    payload,
}: {
    payload: NewsImpactWidgetPayload
}) {
    return (
        <div className="mt-3 overflow-x-auto rounded-xl border border-white/10 bg-slate-900/40 p-3">
            <table className="w-full text-left text-[11px]">
                <thead className="text-slate-500">
                    <tr>
                        <th className="pb-1 pr-3 font-normal">Hisse</th>
                        <th className="pb-1 pr-3 font-normal">Haber</th>
                        <th className="pb-1 pr-3 font-normal">Son hareket</th>
                        <th className="pb-1 font-normal">Tipik hareket</th>
                    </tr>
                </thead>
                <tbody>
                    {payload.rows.map((row) => (
                        <tr key={row.symbol} className="border-t border-white/5">
                            <td className="py-1 pr-3 text-slate-200">
                                {row.symbol}
                                {row.sector && (
                                    <span className="ml-1 text-slate-500">
                                        {row.sector}
                                    </span>
                                )}
                            </td>
                            <td className="py-1 pr-3 text-slate-400">
                                {row.news_count}
                                {row.filing_count > 0 && ` (${row.filing_count} bildirim)`}
                            </td>
                            <td className="py-1 pr-3 text-slate-300">
                                {row.recent_move_pct === null
                                    ? '—'
                                    : `${row.recent_move_pct >= 0 ? '+' : '−'}${pct(
                                          row.recent_move_pct,
                                      )}`}
                            </td>
                            <td className="py-1 text-slate-400">
                                {pct(row.typical_move_pct)}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>

            {/* Tabloyu tek başına okuyan biri, listelenenlerin portföyün
                tamamı olduğunu sanmamalı. */}
            <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
                Son {payload.window_days} gün · {payload.coverage.filings} bildirim,{' '}
                {payload.coverage.feed_articles} haber
                {payload.coverage.symbols_omitted > 0 &&
                    ` · ${payload.coverage.symbols} pozisyonun ${payload.coverage.symbols_omitted} tanesi listede yok`}
            </p>
        </div>
    )
}
