import { apiClient } from '../../api/client'
import { REQUIRED_TOTAL, useAllocationTemplates } from '../../hooks/useAllocationTemplates'
import { useState } from 'react'

/**
 * Hedef formunun başlangıç değerleri.
 *
 * **Şablon bir model portföy değil ve sistem birini seçmiyor.** Bandı beyan
 * edilen toleransla eşleşen şablon listenin başında ve yıldızlı; bu bir
 * sıralama girdisi ve neye göre sıralandığı her kartın cümlesinde yazıyor.
 * Kaydedilen şey yine kullanıcının kendi PUT'u.
 *
 * Hesap yok: toplam ve geçerlilik `useAllocationTemplates`'ten geliyor.
 */
export default function SablonSecici() {
    const state = useAllocationTemplates()
    const [saving, setSaving] = useState(false)
    const [saved, setSaved] = useState(false)
    const [error, setError] = useState('')

    async function save() {
        setSaving(true)
        setError('')
        try {
            await apiClient.setAllocationTarget(
                state.draft.map((row) => ({ bucket: row.bucket, targetPercent: row.percent })),
            )
            setSaved(true)
        } catch (err) {
            setError((err as Error)?.message || 'Hedef kaydedilemedi.')
        } finally {
            setSaving(false)
        }
    }

    return (
        <section className="rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
            <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                Hedef dağılım
            </h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                Şablonlar formun başlangıç değeridir; hedefi siz belirlersiniz.
            </p>

            {state.loading && (
                <p className="mt-4 text-sm text-slate-500">Yükleniyor…</p>
            )}
            {state.error && (
                <p className="mt-4 text-sm text-rose-600">{state.error}</p>
            )}

            <div className="mt-4 grid gap-3 md:grid-cols-3">
                {state.templates.map((template) => (
                    <button
                        key={template.key}
                        type="button"
                        onClick={() => state.selectTemplate(template.key)}
                        className={`rounded-xl border p-3 text-left transition ${
                            state.selectedKey === template.key
                                ? 'border-sky-500 bg-sky-50 dark:bg-sky-950'
                                : 'border-slate-200 dark:border-slate-700'
                        }`}
                    >
                        <span className="flex items-center gap-2 text-sm font-medium text-slate-900 dark:text-slate-100">
                            {template.highlighted && <span aria-hidden>★</span>}
                            {template.label}
                        </span>
                        <span className="mt-1 block text-xs text-slate-500 dark:text-slate-400">
                            {template.statement}
                        </span>
                    </button>
                ))}
            </div>

            {state.draft.length > 0 && (
                <div className="mt-5 flex flex-col gap-2">
                    {state.draft.map((row) => (
                        <label key={row.bucket} className="flex items-center gap-3 text-sm">
                            <span className="w-32 text-slate-600 dark:text-slate-300">
                                {row.label}
                            </span>
                            <input
                                type="number"
                                min={0}
                                max={100}
                                value={row.percent}
                                onChange={(event) =>
                                    state.setPercent(row.bucket, Number(event.target.value))
                                }
                                className="w-24 rounded-lg border border-slate-200 px-2 py-1 dark:border-slate-700 dark:bg-slate-800"
                            />
                            <span className="text-slate-400">%</span>
                        </label>
                    ))}
                    <p
                        className={`text-sm ${
                            state.isValid ? 'text-slate-500' : 'text-amber-600'
                        }`}
                    >
                        Toplam: %{state.total} (tam %{REQUIRED_TOTAL} olmalı)
                    </p>
                    <div className="flex items-center gap-3">
                        <button
                            type="button"
                            disabled={!state.isValid || saving}
                            onClick={() => void save()}
                            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
                        >
                            Hedefi kaydet
                        </button>
                        {saved && <span className="text-sm text-emerald-600">Kaydedildi.</span>}
                        {error && <span className="text-sm text-rose-600">{error}</span>}
                    </div>
                </div>
            )}

            {state.measurementNote && (
                <p className="mt-4 text-xs text-slate-400">{state.measurementNote}</p>
            )}
        </section>
    )
}
