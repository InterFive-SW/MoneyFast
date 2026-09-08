import { formatMoney } from '../../lib/money'
import { LOOKBACKS, rowKey, useRebalancePlan } from '../../hooks/useRebalancePlan'

/**
 * Yeniden dengeleme listesi, satır satır ve GEREKÇELERİYLE.
 *
 * **Toplu onay yok.** Her satırın kendi onayı var ve o onay mevcut
 * `stage` -> `confirm` yolundan geçiyor. Bir satırın hatası diğerlerini
 * durdurmuyor; üstte kaç satırın onaylandığı yazıyor.
 *
 * Çekince şeridi KOŞULSUZ render ediliyor ve metni sunucudan geliyor: burada
 * ikinci kez yazsaydık iki kopyadan biri değişip diğeri kalabilirdi.
 *
 * **Her satırın "Neden" bağlantısı var ve gerekçesi olmayan satır zaten
 * gelmiyor.** Sistemin bir işlem listesi önermesine izin verilmesinin tek
 * dayanağı bu: sebebi görünmeyen bir satırın yanındaki "Onayla" düğmesi,
 * kaldırılan yasağın engellediği şeyin ta kendisi.
 *
 * Uygunluk testi tamamlanmamışsa liste HİÇ YOK ve nedeni yazılı -- bir hata
 * değil, kullanıcının yapabileceği bir şey.
 */
export default function DengelemePaneli() {
    const state = useRebalancePlan()
    const plan = state.plan

    return (
        <section className="rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                    Hedefe göre emir karşılığı
                </h2>
                {/* Ölçümün penceresi. Sonucu gerçekten değiştiriyor:
                    bağlayıcı bant pencereyle birlikte değişir. */}
                <div className="flex flex-wrap gap-1">
                    {LOOKBACKS.map((window) => (
                        <button
                            key={window.key}
                            type="button"
                            onClick={() => state.setLookback(window.key)}
                            className={`rounded-md px-2 py-1 text-[11px] ${
                                state.lookback === window.key
                                    ? 'bg-slate-900 text-white dark:bg-slate-200 dark:text-slate-900'
                                    : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
                            }`}
                        >
                            {window.label}
                        </button>
                    ))}
                </div>
            </div>

            {plan && (
                <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    {plan.disclaimer}
                </p>
            )}

            {state.loading && <p className="mt-4 text-sm text-slate-500">Yükleniyor…</p>}
            {state.error && <p className="mt-4 text-sm text-rose-600">{state.error}</p>}

            {/* Hedefin NEREDEN geldiği. Bir emir listesinin kaynağı,
                listenin kendisi kadar önemli: kullanıcının kendi hedefi mi,
                ankete verdiği cevapların bağladığı bant mı. */}
            {plan?.bandStatement && (
                <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
                    {plan.bandStatement}
                </p>
            )}

            {plan && !plan.hasTarget && (
                <p className="mt-4 text-sm text-slate-500">{plan.statement}</p>
            )}

            {plan?.warning && (
                <p className="mt-3 text-sm text-amber-600">{plan.warning}</p>
            )}

            {(state.confirmed > 0 || state.failed > 0) && (
                <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
                    {state.confirmed} satır onaylandı, {state.failed} satır başarısız.
                </p>
            )}

            <ul className="mt-4 flex flex-col gap-2">
                {plan?.rows.map((row) => {
                    const key = rowKey(row)
                    const status = state.rowState[key]
                    return (
                        <li
                            key={key}
                            className="flex items-start justify-between gap-4 rounded-xl border border-slate-200 p-3 dark:border-slate-700"
                        >
                            <span className="text-sm text-slate-700 dark:text-slate-200">
                                {row.statement}
                                <button
                                    type="button"
                                    onClick={() => state.toggleRow(key)}
                                    className="mt-1 block text-xs text-sky-600"
                                >
                                    {state.expanded === key
                                        ? 'Gerekçeleri gizle'
                                        : `Neden bu satır? (${row.rationale.length})`}
                                </button>
                                {state.expanded === key && (
                                    <ul className="mt-1 flex flex-col gap-0.5">
                                        {row.rationale.map((reason) => (
                                            <li
                                                key={reason.kind + reason.text}
                                                className="text-xs text-slate-500 dark:text-slate-400"
                                            >
                                                {reason.text}
                                            </li>
                                        ))}
                                    </ul>
                                )}
                                {status?.error && (
                                    <span className="mt-1 block text-xs text-rose-600">
                                        {status.error}
                                    </span>
                                )}
                            </span>
                            <button
                                type="button"
                                disabled={status?.status === 'submitting'}
                                onClick={() => void state.confirmRow(row)}
                                className="shrink-0 rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
                            >
                                {row.side === 'SELL' ? 'Satışı onayla' : 'Alışı onayla'}
                            </button>
                        </li>
                    )
                })}
            </ul>

            {plan && plan.unresolved.length > 0 && (
                <div className="mt-5">
                    <h3 className="text-sm font-medium text-slate-700 dark:text-slate-200">
                        Emir üretilemeyenler
                    </h3>
                    <ul className="mt-2 flex flex-col gap-1">
                        {plan.unresolved.map((row, index) => (
                            <li
                                key={`${row.bucket}-${row.symbol ?? index}`}
                                className="text-xs text-slate-500 dark:text-slate-400"
                            >
                                {row.reason}
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {plan && plan.rounding_residual_base !== 0 && (
                <p className="mt-4 text-xs text-slate-400">
                    Yuvarlamadan artan fark:{' '}
                    {formatMoney(plan.rounding_residual_base)}
                </p>
            )}
        </section>
    )
}
