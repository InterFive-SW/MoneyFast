import {
    DIRECTION_LABELS,
    HORIZONS,
    HORIZON_LABELS,
    useDirectionSignal,
    type Horizon,
} from '../../hooks/useDirectionSignal'

/**
 * Ölçülen kanıtların hangi yöne meylettiği, gerekçesiyle.
 *
 * Sohbetle AYNI uç noktayı okuyor: ayrı hesaplasalardı aynı hisse için farklı
 * bir yön söyleyebilirlerdi.
 *
 * **Karşı taraf her zaman görünür.** Yalnızca destekleyen ölçümleri göstermek,
 * sonucu desteksiz ve kullanıcıyı denetleyemez bırakırdı. `narrative` sunucuda
 * kurulmuş hâliyle basılıyor -- koşullu okuma ve çekincesi tek cümle.
 */
export default function YonKarti({ symbol }: { symbol: string }) {
    const state = useDirectionSignal(symbol)
    const signal = state.signal

    return (
        <div className="rounded-2xl border border-white/10 bg-slate-800/60 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-white">Ölçülen kanıt yönü</h3>
                <div className="flex gap-1">
                    {HORIZONS.map((horizon: Horizon) => (
                        <button
                            key={horizon}
                            type="button"
                            onClick={() => state.setHorizon(horizon)}
                            className={`rounded-lg px-2.5 py-1 text-xs ${
                                state.horizon === horizon
                                    ? 'bg-emerald-500 text-white'
                                    : 'bg-white/5 text-slate-300'
                            }`}
                        >
                            {HORIZON_LABELS[horizon]}
                        </button>
                    ))}
                </div>
            </div>

            {state.loading && <p className="mt-3 text-sm text-slate-400">Ölçülüyor…</p>}
            {state.error && <p className="mt-3 text-sm text-rose-400">{state.error}</p>}

            {signal && (
                <>
                    <p className="mt-3 text-sm font-medium text-slate-100">
                        {DIRECTION_LABELS[signal.direction] ?? signal.direction}
                    </p>

                    {state.supporting.length > 0 && (
                        <div className="mt-3">
                            <p className="text-xs font-medium text-emerald-400">Artış lehine</p>
                            <ul className="mt-1 flex flex-col gap-0.5">
                                {state.supporting.map((text) => (
                                    <li key={text} className="text-xs text-slate-300">
                                        {text}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {state.opposing.length > 0 && (
                        <div className="mt-3">
                            <p className="text-xs font-medium text-rose-400">Düşüş lehine</p>
                            <ul className="mt-1 flex flex-col gap-0.5">
                                {state.opposing.map((text) => (
                                    <li key={text} className="text-xs text-slate-300">
                                        {text}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {signal.narrative && (
                        <p className="mt-4 text-xs leading-relaxed text-slate-400">
                            {signal.narrative}
                        </p>
                    )}
                    {signal.horizon_note && (
                        <p className="mt-2 text-[11px] text-slate-500">{signal.horizon_note}</p>
                    )}
                </>
            )}
        </div>
    )
}
