/**
 * Ölçülen metrikleri düz Türkçe bir özete çevirir.
 *
 * Sayfanın tepesinde, rakam yığınından önce duran birkaç cümle. Yeni bir veri
 * kaynağı yok: aynı `metrics` bloğundan üretiliyor.
 *
 * Sınır burada da aynı: **anlatır, yargılamaz.** "Portföyünüz son bir yılda
 * ortalama %18 dalgalandı" bir olgudur. "Oynaklığınız yüksek, azaltmalısınız"
 * hem bir eşik yargısı hem bir direktiftir; `ORCHESTRATOR_SYSTEM_PROMPT`
 * asistana bunu yasaklıyor ve ekranın asistandan daha serbest olması için bir
 * sebep yok.
 *
 * Ölçülemeyen bir metrik cümleye hiç girmez. Eksik veriyi "sıfır" diye
 * anlatmak, olmayan bir güvence vermektir.
 */

import { formatPercent } from './riskFormat'

/** Pencere etiketlerinin okunabilir hâli. */
const WINDOW_LABELS: Record<string, string> = {
    '1M': 'son bir ayda',
    '3M': 'son üç ayda',
    '6M': 'son altı ayda',
    '1Y': 'son bir yılda',
    '3Y': 'son üç yılda',
    '5Y': 'son beş yılda',
    MAX: 'ölçülebilen tüm dönemde',
}

function num(value: unknown): number | null {
    return typeof value === 'number' && !Number.isNaN(value) ? value : null
}

/**
 * Bir düşüşün toparlanma durumunu anlatan yan cümle.
 *
 * Toparlanmamış bir düşüş ile toparlanmış olan farklı durumlardır ve ikisi de
 * farklı cümleyi hak eder; "toparlandı" demek için tarihin gerçekten dolu
 * olması gerekir.
 */
function recoveryClause(drawdown: Record<string, unknown>): string {
    if (!drawdown.recovery_date) return ' ve bu kaybı henüz geri almadı'
    const days = num(drawdown.duration_days)
    if (days === null) return ' ve sonrasında bu kaybı geri aldı'
    return ` ve ${days} işlem günü süren bu düşüşten sonra kaybı geri aldı`
}

/**
 * Özet cümleleri. Hiçbir ölçüm yoksa boş dizi döner ve çağıran bloğu hiç
 * çizmez — boş bir "özet" başlığı, özetlenecek bir şey olmadığını gizler.
 */
export function summarise(
    metrics: Record<string, unknown>,
    lookback: string,
): string[] {
    const when = WINDOW_LABELS[lookback] ?? 'ölçülen dönemde'
    const lines: string[] = []

    const volatility = num(metrics.volatility_annualized)
    if (volatility !== null) {
        lines.push(
            `Portföyünüz ${when} ortalama ${formatPercent(volatility, 0)} dalgalandı.`,
        )
    }

    const drawdown = metrics.max_drawdown as Record<string, unknown> | undefined
    const depth = drawdown ? num(drawdown.value) : null
    if (drawdown && depth !== null) {
        lines.push(
            `En derin düşüşünde zirveden ${formatPercent(Math.abs(depth), 0)} değer kaybetti` +
                `${recoveryClause(drawdown)}.`,
        )
    }

    const concentration = metrics.concentration as Record<string, unknown> | undefined
    const effectiveN = concentration ? num(concentration.effective_n) : null
    const largest = concentration?.largest_position as
        | { symbol?: string; weight?: number }
        | undefined
    if (effectiveN !== null) {
        const rounded = effectiveN.toLocaleString('tr-TR', { maximumFractionDigits: 1 })
        const tail =
            largest?.symbol && typeof largest.weight === 'number'
                ? ` En büyük pozisyon ${largest.symbol} ve portföyün ${formatPercent(
                      largest.weight,
                      0,
                  )}’ini oluşturuyor.`
                : ''
        lines.push(`Değeriniz ${rounded} eşit pozisyona denk biçimde dağılmış.${tail}`)
    }

    return lines
}

/**
 * Ölçümün ne kadar sağlam durduğuna dair tek cümle, ya da sessizlik.
 *
 * Ayrı tutuluyor çünkü bu bir uyarı, bir özet değil: özet cümlelerinin
 * yanında aynı tonda okunursa, güvenilir olmayan bir ölçüm güvenilir gibi
 * görünür.
 */
export function reliabilitySentence(metrics: Record<string, unknown>): string | null {
    const quality = metrics.data_quality as Record<string, unknown> | undefined
    if (!quality) return null
    if (quality.is_statistically_reliable === true) return null
    return 'Bu ölçümler kısa bir geçmişe dayanıyor; birkaç haftanın tesadüfünü yansıtıyor olabilir.'
}
