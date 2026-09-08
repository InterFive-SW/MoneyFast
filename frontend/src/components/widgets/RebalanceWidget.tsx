import type { RebalanceWidgetPayload } from '../../types/chat'

/**
 * Dengeleme listesinin sohbetteki hâli.
 *
 * **Her satır gerekçesiyle çiziliyor ve bu bir tasarım tercihi değil.**
 * Sistemin bir işlem listesi önermesine izin verilmesinin tek dayanağı, her
 * satırın onu üreten ölçümü taşıması; sebebi görünmeyen bir satır, kaldırılan
 * yasağın engellediği şeyin ta kendisi. Gerekçesi olmayan satır zaten
 * `widgets.py`'de çizilmiyor.
 *
 * **Onay düğmesi YOK.** Emir, ekrandaki Dengeleme sekmesinde kullanıcının
 * kendi tıklamasıyla onaylanıyor; sohbette ikinci bir onay yüzeyi, aynı emri
 * iki yerden verilebilir yapardı ve hangisinin geçerli olduğu okunamazdı.
 *
 * Çekince koşulsuz ve sunucudan.
 */
export default function RebalanceWidget({
    payload,
}: {
    payload: RebalanceWidgetPayload
}) {
    return (
        <div className="mt-3 rounded-xl border border-white/10 bg-slate-900/40 p-3">
            {payload.band_statement && (
                <p className="text-[11px] leading-relaxed text-slate-400">
                    {payload.band_statement}
                </p>
            )}

            <ul className="mt-2 flex flex-col gap-2">
                {payload.rows.map((row) => (
                    <li
                        key={`${row.bucket}:${row.symbol}:${row.side}`}
                        className="border-b border-white/5 pb-2 last:border-0"
                    >
                        <p className="text-xs text-slate-200">{row.statement}</p>
                        <ul className="mt-1 flex flex-col gap-0.5">
                            {row.rationale.map((reason) => (
                                <li
                                    key={reason}
                                    className="text-[11px] leading-relaxed text-slate-400"
                                >
                                    {reason}
                                </li>
                            ))}
                        </ul>
                    </li>
                ))}
            </ul>

            <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
                {payload.disclaimer}
            </p>
        </div>
    )
}
