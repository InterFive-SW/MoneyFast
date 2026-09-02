import { useEffect, useState } from 'react'
import { apiClient } from '../../api/client'

/**
 * "Detaylı Rapor Oluştur" — tek tıkla, sistemin ölçtüğü her şey.
 *
 * Proje dokümanı bu düğmeyi adıyla istiyor. Rapor YENİ BİR ÖLÇÜM YAPMIYOR:
 * her bölüm zaten var olan bir servisten okunuyor.
 *
 * Bölüm cümleleri BACKEND'de kuruluyor ve burada olduğu gibi gösteriliyor.
 * Ekran, yazdırma çıktısı ve sohbet aynı metni okumalı; bu depoda iki
 * yüzeyin ayrışması defalarca ölçüldü ve rapor üç yüzeye birden gidiyor.
 *
 * PDF tarayıcıya bırakıldı: `window.print()` Türkçe karakterleri bozmadan
 * çıkarıyor. Sunucuda üretmek imaja bir Unicode font paketi eklemeyi
 * gerektiriyor -- mevcut PDF üreteci `Helvetica` kullandığı için "Kisisel",
 * "Olusturulma" diye yazmak zorunda kalmış. Herkesin build'ini etkileyen bir
 * karar olduğu için alınmadı.
 */
interface Section {
    key: string
    title: string
    summary: string
    lines: string[]
}

interface Report {
    generated_at: string
    as_of: string
    is_delayed: boolean
    delay_minutes: number
    sections: Section[]
}

function formatMoment(iso: string): string {
    const at = new Date(iso)
    return Number.isNaN(at.getTime())
        ? iso
        : at.toLocaleString('tr-TR', { dateStyle: 'long', timeStyle: 'short' })
}

export default function DetayliRaporModal({ onClose }: { onClose: () => void }) {
    const [report, setReport] = useState<Report | null>(null)
    const [error, setError] = useState('')

    useEffect(() => {
        apiClient
            .getPortfolioReport()
            .then((data) => setReport(data as never))
            .catch(() => setError('Rapor oluşturulamadı.'))
    }, [])

    return (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/80 p-4 backdrop-blur-sm">
            <section className="my-8 w-full max-w-3xl rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl">
                <header className="mb-5 flex items-start justify-between gap-4">
                    <div>
                        <h2 className="text-lg font-semibold text-white">Detaylı Rapor</h2>
                        {report && (
                            <p className="mt-1 text-xs text-slate-400">
                                {formatMoment(report.generated_at)} tarihinde oluşturuldu.
                                {/* Fiyatların ait olduğu an, belgenin üretildiği andan
                                    AYRI: raporu üretim saatiyle tarihlemek, fiyatları
                                    olduğundan taze göstermek olurdu. */}
                                {report.is_delayed && (
                                    <> Fiyatlar {report.delay_minutes} dakika gecikmeli;{' '}
                                        {formatMoment(report.as_of)} itibarıyla.</>
                                )}
                            </p>
                        )}
                    </div>
                    <div className="flex shrink-0 gap-2">
                        <button
                            onClick={() => window.print()}
                            className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:bg-white/10"
                        >
                            Yazdır / PDF
                        </button>
                        <button
                            onClick={onClose}
                            className="rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-400 transition hover:text-white"
                        >
                            Kapat
                        </button>
                    </div>
                </header>

                {error && <p role="alert" className="text-sm text-rose-400">{error}</p>}
                {!report && !error && (
                    <p className="py-10 text-center text-sm text-slate-400">
                        Rapor hazırlanıyor…
                    </p>
                )}

                {report?.sections.map((section) => (
                    <article key={section.key} className="mb-5 border-t border-white/5 pt-4">
                        <h3 className="text-sm font-semibold text-white">{section.title}</h3>
                        {/* Cümle sunucudan geldiği gibi. */}
                        <p className="mt-1 text-sm text-slate-300">{section.summary}</p>
                        {section.lines.length > 0 && (
                            <ul className="mt-2 space-y-1">
                                {section.lines.map((line, index) => (
                                    <li key={index} className="text-xs text-slate-400">
                                        {line}
                                    </li>
                                ))}
                            </ul>
                        )}
                    </article>
                ))}
            </section>
        </div>
    )
}
