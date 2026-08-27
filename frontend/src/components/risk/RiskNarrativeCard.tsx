import { reliabilitySentence, summarise } from '../../lib/riskNarrative'

/**
 * Sayfanın tepesindeki düz Türkçe özet.
 *
 * Risk sayfası doğrudan bir rakam yığınıyla açılıyordu: puan, bileşenler,
 * metrikler. Oynaklığın ne olduğunu bilmeyen biri için bu bir duvar. Bu kart
 * aynı ölçümleri üç cümleye çeviriyor — yeni bir veri kaynağı yok, yalnızca
 * okunabilir bir giriş.
 *
 * Cümleler `lib/riskNarrative` içinde üretiliyor: kapsama kapısı orayı sayıyor
 * ve "hiçbir cümle eşik yargısı taşımaz" kuralı orada testle sabitli.
 */
interface RiskNarrativeCardProps {
    metrics: Record<string, unknown>
    lookback: string
}

export default function RiskNarrativeCard({ metrics, lookback }: RiskNarrativeCardProps) {
    const lines = summarise(metrics, lookback)
    // Özetlenecek bir şey yoksa başlık da çizilmez: boş bir "özet" bloğu,
    // ölçüm olmadığını göstermek yerine gizler.
    if (lines.length === 0) return null

    const caveat = reliabilitySentence(metrics)

    return (
        <div className="mb-6 rounded-2xl border border-white/10 bg-slate-900/50 p-6 shadow-2xl backdrop-blur-xl">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
                Kısaca
            </h2>
            <div className="flex flex-col gap-2">
                {lines.map((line) => (
                    <p key={line} className="text-base leading-relaxed text-slate-100">
                        {line}
                    </p>
                ))}
            </div>
            {caveat && (
                <p className="mt-3 border-t border-white/10 pt-3 text-xs leading-relaxed text-amber-200/80">
                    {caveat}
                </p>
            )}
        </div>
    )
}
