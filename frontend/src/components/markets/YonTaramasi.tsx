import { Link } from 'react-router-dom'

import { SCREEN_FILTERS, useDirectionScreen } from '../../hooks/useDirectionScreen'
import { HORIZONS, HORIZON_LABELS, type Horizon } from '../../hooks/useDirectionSignal'

/**
 * Ölçülen kanıt yönüne göre tarama.
 *
 * **Başlık "en iyi hisseler" DEĞİL ve öyle olmaması bilinçli:** sıralanan şey
 * ölçülen kanıtların meyli, bir cazibe sıralaması değil. Ölçüm değeri her
 * satırda yazılı ki sıralamanın neye göre yapıldığı okunabilsin, ve altta
 * kalıcı bir çekince duruyor.
 *
 * Hesap gecelik: `computedAt` gösteriliyor, çünkü dünkü ölçümü bugünün
 * ölçümü gibi göstermek olurdu.
 */
export default function YonTaramasi() {
    const state = useDirectionScreen()

    return (
        <div className="flex h-full flex-col rounded-2xl border border-white/10 bg-slate-900/50 p-4">
            <h3 className="text-sm font-semibold text-white">Ölçülen kanıt yönü</h3>

            <div className="mt-3 flex flex-wrap gap-1">
                {HORIZONS.map((horizon: Horizon) => (
                    <button
                        key={horizon}
                        type="button"
                        onClick={() => state.setHorizon(horizon)}
                        className={`rounded-md px-2 py-1 text-xs ${
                            state.horizon === horizon
                                ? 'bg-emerald-500 text-white'
                                : 'bg-white/5 text-slate-400'
                        }`}
                    >
                        {HORIZON_LABELS[horizon]}
                    </button>
                ))}
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
                {SCREEN_FILTERS.map((filter) => (
                    <button
                        key={filter.key || 'all'}
                        type="button"
                        onClick={() => state.setDirection(filter.key)}
                        className={`rounded-md px-2 py-1 text-xs ${
                            state.direction === filter.key
                                ? 'bg-white/15 text-white'
                                : 'bg-white/5 text-slate-400'
                        }`}
                    >
                        {filter.label}
                    </button>
                ))}
            </div>

            {state.loading && <p className="mt-3 text-xs text-slate-400">Yükleniyor…</p>}
            {state.error && <p className="mt-3 text-xs text-rose-400">{state.error}</p>}
            {state.note && <p className="mt-3 text-xs text-slate-400">{state.note}</p>}

            <ul className="mt-3 flex-1 overflow-y-auto">
                {state.rows.map((row) => (
                    <li key={row.symbol} className="border-b border-white/5 py-1.5">
                        <Link
                            to={`/investment/hisseler/${row.symbol}`}
                            className="flex items-center justify-between text-xs"
                        >
                            <span className="font-medium text-slate-200">{row.symbol}</span>
                            {/* Ölçüm değeri GÖRÜNÜR: sıralamanın neye göre
                                yapıldığı okunabilmeli. */}
                            <span className="text-slate-400">
                                {row.lean === null ? '—' : row.lean.toFixed(2)}
                            </span>
                        </Link>
                    </li>
                ))}
            </ul>

            <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
                Ölçülen kanıtların yönüne göre sıralanmıştır; bir tavsiye ya da
                başarı sıralaması değildir.
                {state.computedAt && (
                    <> {new Date(state.computedAt).toLocaleDateString('tr-TR')} itibarıyla.</>
                )}
            </p>
        </div>
    )
}
