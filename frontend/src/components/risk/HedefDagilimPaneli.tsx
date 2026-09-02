import { useEffect, useMemo, useState } from 'react'
import { apiClient } from '../../api/client'
import { formatMoney } from '../../lib/money'

/**
 * Hedef dağılım ve ondan sapma.
 *
 * Hedefi KULLANICI koyuyor, sistem değil, ve bu bilerek böyle.
 * `compliance/rules.py:SUI-001`'in gerekçesi şunu söylüyor: "sistem ölçüm ile
 * kullanıcının kendi beyanını karşılaştırır, bir ürünün kişiye uygunluğuna
 * karar vermez." Bir model portföy önermek tam olarak o kararı vermek olurdu
 * — üstelik dört SPK ürün grubundan yalnızca hisse senedinin bu sistemde
 * enstrümanı var, dolayısıyla önerilenin çoğu uygulanamaz bir talimat olurdu.
 *
 * Panel hiçbir yerde ne yapılması gerektiğini söylemiyor. "Hedefe ulaşmak
 * için 7.419 TL fark var" bir çıkarma işlemi; "7.419 TL satın" bir tavsiye.
 *
 * Sapma cümlesi SUNUCUDAN geliyor, burada kurulmuyor: sapmanın yönü yanlış
 * okunursa kullanıcı hedefinin tersine hareket eder ve bu, iki yerde
 * yaşayacak bir kural değil.
 */
interface DriftBucket {
    bucket: string
    label: string
    amount: number
    currentPercent: number | null
    targetPercent: number | null
    gapPoints: number | null
    gapAmount: number | null
}

export default function HedefDagilimPaneli() {
    const [drift, setDrift] = useState<{
        hasTarget: boolean
        totalValue: number
        buckets: DriftBucket[]
        statement: string
    } | null>(null)
    const [editing, setEditing] = useState(false)
    const [draft, setDraft] = useState<Record<string, string>>({})
    const [error, setError] = useState('')
    const [saving, setSaving] = useState(false)

    async function load() {
        try {
            setDrift(await apiClient.getAllocationDrift() as never)
        } catch {
            setDrift(null)
        }
    }

    useEffect(() => { void load() }, [])

    const total = useMemo(
        () => Object.values(draft).reduce((sum, v) => sum + (Number(v) || 0), 0),
        [draft],
    )

    function startEditing() {
        const seed: Record<string, string> = {}
        for (const row of drift?.buckets ?? []) {
            if (row.targetPercent !== null) seed[row.bucket] = String(row.targetPercent)
        }
        setDraft(seed)
        setError('')
        setEditing(true)
    }

    async function save() {
        // Toplam KAYDETMEDEN önce kontrol ediliyor. Sunucu da reddediyor —
        // bu, kullanıcıyı bir tur beklemekten kurtaran ikinci kapı, tek kapı
        // değil.
        if (Math.round(total * 100) / 100 !== 100) {
            setError(`Hedeflerin toplamı 100 olmalı; şu an ${total.toFixed(0)}.`)
            return
        }
        setSaving(true)
        try {
            await apiClient.setAllocationTarget(
                Object.entries(draft)
                    .filter(([, value]) => Number(value) > 0)
                    .map(([bucket, value]) => ({ bucket, targetPercent: Number(value) })),
            )
            setEditing(false)
            await load()
        } catch (err: any) {
            setError(err?.message || 'Hedef kaydedilemedi.')
        } finally {
            setSaving(false)
        }
    }

    if (!drift) return null

    const rows = drift.buckets

    return (
        <section className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h3 className="text-sm font-semibold text-white">Hedef dağılım</h3>
                    <p className="mt-1 text-xs text-slate-400">
                        Hedefi siz belirlersiniz; buradaki fark, ölçülen ağırlıkla
                        kendi hedefinizin çıkarmasıdır.
                    </p>
                </div>
                {!editing && (
                    <button
                        onClick={startEditing}
                        className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:bg-white/10"
                    >
                        {drift.hasTarget ? 'Hedefi düzenle' : 'Hedef belirle'}
                    </button>
                )}
            </div>

            {editing ? (
                <div className="space-y-3">
                    {rows.length === 0 && (
                        <p className="text-xs text-slate-400">
                            Hedef belirlenebilecek bir kova bulunamadı.
                        </p>
                    )}
                    {['cash', 'bist_equity', 'us_equity', 'gold', 'fx'].map((bucket) => {
                        const label = rows.find((r) => r.bucket === bucket)?.label
                            ?? BUCKET_LABELS[bucket]
                        return (
                            <label key={bucket} className="flex items-center gap-3 text-sm">
                                <span className="w-32 text-slate-300">{label}</span>
                                <input
                                    type="number"
                                    min={0}
                                    max={100}
                                    value={draft[bucket] ?? ''}
                                    onChange={(e) =>
                                        setDraft({ ...draft, [bucket]: e.target.value })}
                                    className="w-24 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-right text-white outline-none focus:border-brandBlue"
                                />
                                <span className="text-slate-500">%</span>
                            </label>
                        )
                    })}

                    <div className="flex items-center justify-between border-t border-white/10 pt-3 text-sm">
                        <span className={total === 100 ? 'text-emerald-400' : 'text-amber-400'}>
                            Toplam: %{total.toFixed(0)}
                        </span>
                        <div className="flex gap-2">
                            <button
                                onClick={() => setEditing(false)}
                                className="rounded-lg px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200"
                            >
                                Vazgeç
                            </button>
                            <button
                                onClick={save}
                                disabled={saving}
                                className="rounded-lg bg-brandBlue px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
                            >
                                {saving ? 'Kaydediliyor…' : 'Kaydet'}
                            </button>
                        </div>
                    </div>

                    {error && (
                        <p role="alert" className="text-xs text-rose-400">{error}</p>
                    )}
                </div>
            ) : (
                <>
                    {/* Cümle sunucudan geldiği gibi aktarılıyor. */}
                    <p className="mb-4 text-sm text-slate-300">{drift.statement}</p>

                    {drift.hasTarget && (
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-xs uppercase text-slate-500">
                                        <th className="pb-2 text-left font-medium">Kova</th>
                                        <th className="pb-2 text-right font-medium">Ölçülen</th>
                                        <th className="pb-2 text-right font-medium">Hedef</th>
                                        <th className="pb-2 text-right font-medium">Fark</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {rows.map((row) => (
                                        <tr key={row.bucket} className="border-t border-white/5">
                                            <td className="py-2 text-slate-300">{row.label}</td>
                                            <td className="py-2 text-right tabular-nums text-slate-200">
                                                {row.currentPercent === null
                                                    ? '—' : `%${row.currentPercent}`}
                                            </td>
                                            {/* Hedefi olmayan kova "—", %0 DEĞİL:
                                                "hedefim yok" ile "hedefim sıfır"
                                                farklı şeyler. */}
                                            <td className="py-2 text-right tabular-nums text-slate-400">
                                                {row.targetPercent === null
                                                    ? '—' : `%${row.targetPercent}`}
                                            </td>
                                            <td className="py-2 text-right tabular-nums">
                                                {row.gapPoints === null ? (
                                                    <span className="text-slate-500">—</span>
                                                ) : (
                                                    <span className={row.gapPoints > 0
                                                        ? 'text-amber-400' : 'text-sky-400'}>
                                                        {row.gapPoints > 0 ? '+' : ''}
                                                        {row.gapPoints} puan
                                                        <span className="ml-1 text-slate-500">
                                                            ({formatMoney(
                                                                Math.abs(row.gapAmount ?? 0))})
                                                        </span>
                                                    </span>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </>
            )}
        </section>
    )
}

/** Elde hiç olmayan bir kovaya da hedef koyulabilsin diye. */
const BUCKET_LABELS: Record<string, string> = {
    cash: 'Nakit (TRY)',
    bist_equity: 'BIST Hisse',
    us_equity: 'ABD Hisse',
    gold: 'Altın',
    fx: 'Döviz',
}
