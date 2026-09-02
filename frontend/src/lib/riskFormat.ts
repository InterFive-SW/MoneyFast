import { formatDate as formatInIstanbul } from './datetime'
/**
 * Risk metriklerini okunabilir Türkçeye çeviren katman.
 *
 * `GET /api/risk/profile` bu metriklerin hepsini baştan beri döndürüyordu ve
 * sayfa hiçbirini render etmiyordu: VaR, CVaR, Sharpe, beta, aşağı yönlü
 * sapma, drawdown'ın tepe/dip tarihleri, sektör ve para birimi kırılımları.
 * Hesaplanıyor, ağdan taşınıyor, atılıyordu.
 *
 * Buradaki iki kural bileşenlerde değil burada, çünkü kapsama kapısı
 * (`vitest.config.ts`) `src/lib/**`'ı sayıyor ve JSX'i saymıyor:
 *
 * 1. **Ölçülemeyen bir değer asla sıfır olarak gösterilmez.** `null` gelen
 *    bir oynaklık "risk yok" değil, "ölçemedik" demektir; sıfır yazmak
 *    kullanıcıya olmayan bir güvence verir.
 * 2. **Hiçbir alan adı ekrana çıkmaz.** CLAUDE.md'nin NAMING kuralı gereği
 *    `max_drawdown`, `hhi`, `value_fraction` gibi anahtarlar kullanıcıya
 *    gösterilmez; ne anlama geldikleri yazılır.
 */

/** Ölçülemeyen değerin tek gösterimi. Sıfır değil, çizgi değil, cümle. */
export const NOT_MEASURED = 'ölçülemedi'

/** Bir metriğin kart başlığı ve altındaki tek cümlelik açıklaması. */
export interface MetricCopy {
    label: string
    hint: string
}

/**
 * Kart metinleri. Açıklamalar kasıtlı olarak tanım cümlesidir, yorum değil:
 * "oynaklığınız yüksek" bir eşik yargısıdır ve `ORCHESTRATOR_SYSTEM_PROMPT`'un
 * yasakladığı şeydir; "yıllık dalgalanmanın ölçüsü" bir tanımdır.
 */
export const METRIC_COPY: Record<string, MetricCopy> = {
    volatility_annualized: {
        label: 'Yıllık oynaklık',
        hint: 'Portföy değerinin bir yıl içinde ortalamadan ne kadar saptığının ölçüsü.',
    },
    downside_deviation_annualized: {
        label: 'Aşağı yönlü sapma',
        hint: 'Yalnızca kayıp günlerinin dalgalanması; yukarı hareketler sayılmaz.',
    },
    sharpe_ratio: {
        label: 'Sharpe oranı',
        hint: 'Alınan dalgalanma başına elde edilen getiri. Faizsiz getiriye göre ölçülür.',
    },
    beta: {
        label: 'Endekse duyarlılık',
        hint: 'Endeks %1 hareket ettiğinde portföyün tarihsel olarak ne kadar hareket ettiği.',
    },
    correlation_to_benchmark: {
        label: 'Endeksle birlikte hareket',
        hint: '1’e yakın değer endeksle aynı yönde, 0 ilişkisiz, -1 ters yönde demek.',
    },
}

const PERCENT_METRICS = new Set([
    'volatility_annualized',
    'downside_deviation_annualized',
])

/** `0.4796` -> `%47,96`. Yüzde işareti Türkçe konvansiyonuyla başta. */
export function formatPercent(value: number | null | undefined, digits = 2): string {
    if (value === null || value === undefined || Number.isNaN(value)) return NOT_MEASURED
    return `%${(value * 100).toLocaleString('tr-TR', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
    })}`
}

/** `0.9969` -> `0,99`. Oranlar yüzde değildir; Sharpe ve beta buradan geçer. */
export function formatRatio(value: number | null | undefined, digits = 2): string {
    if (value === null || value === undefined || Number.isNaN(value)) return NOT_MEASURED
    return value.toLocaleString('tr-TR', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
    })
}

/** Bir metriği kendi birimiyle biçimler. Hangisinin yüzde olduğunu tek yer bilir. */
export function formatMetric(name: string, value: number | null | undefined): string {
    return PERCENT_METRICS.has(name) ? formatPercent(value) : formatRatio(value)
}

/** `2026-05-05` -> `5 Mayıs 2026`. Geçersiz veya boş tarih `null` döner.
 *
 *  Kendi `null` sözleşmesi var (çağıranlar "tarih yok" ile "tarih bozuk"u
 *  ayırt etmiyor, ikisinde de satırı çizmiyorlar), o yüzden ortak
 *  biçimlendiriciyi sarmalıyor -- ama saat dilimi ondan geliyor. */
export function formatDate(value: string | null | undefined): string | null {
    if (!value) return null
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return null
    return formatInIstanbul(parsed, { day: 'numeric', month: 'long', year: 'numeric' })
}

export interface DrawdownView {
    depth: string
    peak: string | null
    trough: string | null
    /** Toparlanma olmadıysa `null` — "henüz toparlanmadı" ayrı bir bilgidir. */
    recovery: string | null
    recovered: boolean
    durationDays: number | null
}

/**
 * En derin düşüşü bir zaman şeridine çevirir.
 *
 * `recovery_date: null` "toparlanma yok" demek, "veri yok" değil — ikisi
 * ayrı gösterilir, çünkü hâlâ dipte olan bir portföy toparlanmış olandan
 * farklı bir durumdur.
 */
export function describeDrawdown(raw: unknown): DrawdownView | null {
    if (!raw || typeof raw !== 'object') return null
    const block = raw as Record<string, unknown>
    const value = typeof block.value === 'number' ? block.value : null
    if (value === null) return null
    return {
        depth: formatPercent(Math.abs(value)),
        peak: formatDate(block.peak_date as string | null),
        trough: formatDate(block.trough_date as string | null),
        recovery: formatDate(block.recovery_date as string | null),
        recovered: Boolean(block.recovery_date),
        durationDays:
            typeof block.duration_days === 'number' ? block.duration_days : null,
    }
}

export interface LossEstimateView {
    fraction: string
    amount: number | null
    confidence: string
    hint: string
}

/**
 * VaR / CVaR kartı.
 *
 * `hint` metni MCP sözleşmesinin şartı: bu sayılar TARİHSEL ölçümlerdir,
 * bir kayıp tahmini ya da üst sınırı değildir. Sözleşme bunu kelimesi
 * kelimesine şart koşuyor, o yüzden metin burada sabit.
 */
export function describeLossEstimate(
    raw: unknown,
    kind: 'var' | 'cvar',
): LossEstimateView | null {
    if (!raw || typeof raw !== 'object') return null
    const block = raw as Record<string, unknown>
    const fraction = typeof block.value_fraction === 'number' ? block.value_fraction : null
    if (fraction === null) return null
    const confidence =
        typeof block.confidence_level === 'number'
            ? formatPercent(block.confidence_level, 0)
            : NOT_MEASURED
    return {
        fraction: formatPercent(Math.abs(fraction)),
        amount: typeof block.value_currency === 'number' ? Math.abs(block.value_currency) : null,
        confidence,
        hint:
            kind === 'var'
                ? `Geçmiş günlerin ${confidence}’inde günlük kayıp bu seviyenin altında kalmış. Gelecek için bir sınır değildir.`
                : `Kaybın bu eşiği aştığı günlerde ortalama kayıp. Geçmiş ölçümdür, tahmin değildir.`,
    }
}

export interface BreakdownSlice {
    label: string
    weight: number
    percent: string
}

/**
 * Ham enum -> Türkçe.
 *
 * `investment_products.product_type` `stock`/`commodity`/`fx`/`index` tutuyor
 * ve MCP yolundaki sözleşme `EQUITY`/`ETF` gibi büyük harfli değerler
 * kullanıyor. NAMING kuralı alan adlarını olduğu kadar enum değerlerini de
 * yasaklıyor: "stock" bir varlık sınıfı adı değil, bir veritabanı değeri.
 */
const LABELS: Record<string, string> = {
    UNCLASSIFIED: 'Sınıflandırılmamış',
    STOCK: 'Hisse senedi',
    EQUITY: 'Hisse senedi',
    COMMODITY: 'Emtia',
    FX: 'Döviz',
    INDEX: 'Endeks',
    ETF: 'Borsa yatırım fonu',
    FUND: 'Fon',
    BOND: 'Tahvil',
    CASH: 'Nakit',
}

/**
 * `{"stock": 0.7, "commodity": 0.3}` -> ağırlığa göre azalan dilimler.
 *
 * Tanınmayan bir etiket olduğu gibi geçer: sektör adları (`Technology`,
 * `Basic Materials`) zaten okunabilir ve onları bir haritaya hapsetmek, yeni
 * bir sektör eklendiği gün onu görünmez kılardı.
 */
export function toBreakdown(raw: unknown): BreakdownSlice[] {
    if (!raw || typeof raw !== 'object') return []
    return Object.entries(raw as Record<string, unknown>)
        .filter(([, weight]) => typeof weight === 'number')
        .map(([label, weight]) => ({
            label: LABELS[label.toUpperCase()] ?? label,
            weight: weight as number,
            percent: formatPercent(weight as number, 1),
        }))
        .sort((a, b) => b.weight - a.weight)
}

/**
 * Etkin pozisyon sayısı: HHI'nin tersi.
 *
 * "1,6 pozisyona denk" cümlesi, 0,62'lik bir HHI'den çok daha okunabilir.
 */
export function describeEffectiveN(value: number | null | undefined): string {
    if (value === null || value === undefined || Number.isNaN(value)) return NOT_MEASURED
    return `${formatRatio(value, 1)} pozisyona denk`
}

/**
 * Veri kalitesi uyarısı — güvenilir değilse bir cümle, güvenilirse hiçbir şey.
 *
 * Sessiz kalmak, altmış günden az gözlemle hesaplanmış bir oynaklığı kesin
 * bir rakam gibi göstermek demekti.
 */
export function reliabilityNotice(raw: unknown): string | null {
    if (!raw || typeof raw !== 'object') return null
    const block = raw as Record<string, unknown>
    if (block.is_statistically_reliable === true) return null
    const excluded = Array.isArray(block.excluded_symbols) ? block.excluded_symbols : []
    const tail = excluded.length
        ? ` Yeterli fiyat geçmişi olmayanlar hesaba katılmadı: ${excluded.join(', ')}.`
        : ''
    return `Bu ölçümler istatistiksel olarak güvenilir sayılacak kadar uzun bir geçmişe dayanmıyor.${tail}`
}

/**
 * Uyum rozetinin metni ve rengi.
 *
 * Ham enum (`PORTFOLIO_RISKIER`) kullanıcıya asla yazılmaz — bkz. NAMING
 * kuralı. Renk bir yargı değil bir yön: portföy beyanın üzerindeyse dikkat
 * çeken, altındaysa sakin bir ton. "İyi/kötü" demiyor, hangi tarafta
 * olduğunu söylüyor.
 *
 * `UNKNOWN` bir uyuşmazlık DEĞİL: iki taraftan biri henüz yok. Rozet bunu
 * nötr tonla ve "anket bekliyor" diyerek gösteriyor, çünkü kırmızı bir
 * "bilinmiyor" doldurulmamış bir formu bir sorun gibi okutur.
 */
export interface AlignmentBadge {
    label: string
    tone: string
}

export const ALIGNMENT_BADGE: Record<string, AlignmentBadge> = {
    ALIGNED: { label: 'Beyanınızla aynı bandda', tone: 'bg-emerald-500/10 text-emerald-400' },
    PORTFOLIO_RISKIER: {
        label: 'Beyanınızın üzerinde',
        tone: 'bg-rose-500/10 text-rose-400',
    },
    PORTFOLIO_CALMER: {
        label: 'Beyanınızın altında',
        tone: 'bg-sky-500/10 text-sky-400',
    },
    UNKNOWN: { label: 'Anket bekliyor', tone: 'bg-white/5 text-slate-400' },
}

export function alignmentBadge(alignment: string | null | undefined): AlignmentBadge {
    return ALIGNMENT_BADGE[alignment ?? ''] ?? ALIGNMENT_BADGE.UNKNOWN
}

/**
 * Ölçümün künyesi: neyi, ne kadar süreyle, neye göre ölçtük.
 *
 * Sayfa Sharpe oranını ve betayı gösteriyordu ama ikisinin de neye göre
 * hesaplandığını söylemiyordu. MCP sözleşmesi Sharpe sunulurken faizin
 * açıklanmasını şart koşuyor; sohbet yolu bunu yapıyordu, sayfa yapmıyordu.
 *
 * Alan adı ve enum ekrana çıkmaz: `XU100` yerine "BIST 100",
 * `FIXTURE_POLICY_RATE` yerine "politika faizi".
 */
const BENCHMARK_NAMES: Record<string, string> = {
    XU100: 'BIST 100',
    XU030: 'BIST 30',
    SPX: 'S&P 500',
    NDX: 'Nasdaq 100',
}

export function benchmarkName(symbol: unknown): string | null {
    if (typeof symbol !== 'string' || !symbol) return null
    return BENCHMARK_NAMES[symbol.toUpperCase()] ?? symbol.toUpperCase()
}

/**
 * `27 Oca 2025 – 24 Ağu 2026 arası 253 işlem günü · BIST 100'e göre ·
 *  Sharpe %42,5 politika faizine göre`
 *
 * Söylenemeyen parça hiç yazılmaz. Eksik bir tarih aralığını "—" ile
 * doldurmak, ölçümün kapsamı hakkında bilgi veriyormuş gibi yapmak olurdu.
 */
export function measurementCaption(
    window: unknown,
    assumptions: unknown,
): string | null {
    const w = (window ?? {}) as Record<string, unknown>
    const a = (assumptions ?? {}) as Record<string, unknown>
    const parts: string[] = []

    const start = formatDate(w.start_date as string | null)
    const end = formatDate(w.end_date as string | null)
    const count = typeof w.observation_count === 'number' ? w.observation_count : null
    if (start && end && count) {
        parts.push(`${start} – ${end} arası ${count} işlem günü`)
    } else if (count) {
        parts.push(`${count} işlem günü`)
    }

    // Yalnızca gerçekten geçmişi bulunan bir ölçüt anılır: adı yazıp
    // altında "ölçülemedi" göstermek, olmayan bir karşılaştırma vaat eder.
    const benchmark = benchmarkName(a.benchmark_symbol)
    if (benchmark && a.benchmark_history_available) {
        parts.push(`${benchmark}’e göre`)
    }

    const rate = typeof a.risk_free_rate === 'number' ? a.risk_free_rate : null
    if (rate !== null) {
        const source =
            a.risk_free_rate_source === 'CALLER_SUPPLIED'
                ? 'belirtilen faiz'
                : 'politika faizi'
        parts.push(`Sharpe ${formatPercent(rate, 1)} ${source}ne göre`)
    }

    return parts.length ? parts.join(' · ') : null
}

export interface ContributionRow {
    symbol: string
    weight: number
    contribution: number
    /** Risk payı ile ağırlık arasındaki fark. Asıl bilgi bu. */
    gap: number
}

/**
 * Risk katkısı satırları, payı büyükten küçüğe.
 *
 * Ağırlık ve risk payı yan yana duruyor çünkü **ikisinin ayrışması** asıl
 * bilgi: yoğunlaşma "etkin çeşitlilik 5,8" diyor ama beş pozisyonun beşi de
 * bankaysa birlikte hareket ederler ve portföy ağırlıkların söylediğinden
 * çok daha az çeşitlendirilmiştir.
 */
export function toContributions(raw: unknown): ContributionRow[] {
    if (!Array.isArray(raw)) return []
    return raw
        .filter(
            (row): row is { symbol: string; weight: number; contribution: number } =>
                !!row &&
                typeof row.symbol === 'string' &&
                typeof row.weight === 'number' &&
                typeof row.contribution === 'number',
        )
        .map((row) => ({
            symbol: row.symbol,
            weight: row.weight,
            contribution: row.contribution,
            gap: row.contribution - row.weight,
        }))
        .sort((a, b) => b.contribution - a.contribution)
}

/**
 * Bir satırın tek cümlelik okunuşu.
 *
 * Tanım cümlesi, yargı değil: "riskin %62'sini taşıyor" bir ölçümdür,
 * "azaltın" bir tavsiye. `ORCHESTRATOR_SYSTEM_PROMPT`'un yasakladığı ikincisi.
 */
export function describeContribution(row: ContributionRow): string {
    if (row.contribution < 0) {
        return 'Portföyün dalgalanmasını azaltan yönde hareket etmiş.'
    }
    // Eşik değil, okunabilirlik: ağırlığa çok yakın bir pay hakkında
    // söylenecek bir şey yok, uydurmak yerine susulur.
    if (Math.abs(row.gap) < 0.05) {
        return 'Riskteki payı ağırlığıyla yaklaşık aynı.'
    }
    return row.gap > 0
        ? 'Riskteki payı ağırlığından büyük: portföyün geri kalanıyla birlikte hareket ediyor.'
        : 'Riskteki payı ağırlığından küçük: portföyün geri kalanından bağımsız hareket etmiş.'
}

export interface ComparisonPoint {
    date: string
    value: number
    /** Endeksin portföyün başlangıç değerine ölçeklenmiş hâli; ortak olmayan
     *  günlerde `null` — grafik orada çizgiyi kesintiye uğratır. */
    benchmark: number | null
}

/**
 * Portföy ile endeksi tek eksende karşılaştırılabilir kılar.
 *
 * Endeks, portföyün İLK değerine ölçekleniyor: ikisi aynı noktadan başlıyor
 * ve sonrasındaki ayrışma tamamen göreli performans. Her ikisini 100'e
 * normalize etmek de aynı bilgiyi verirdi ama portföyün TL büyüklüğünü
 * ekrandan silerdi — bu yol ikisini birden korur.
 *
 * Ortak olmayan gün `null` bırakılır, önceki değere sabitlenmez: endeksi
 * işlem görmediği bir günde yatay çizmek, olmayan bir hareketsizliği
 * göstermek olur.
 */
export function toComparisonSeries(
    trend: unknown,
    benchmark: unknown,
): ComparisonPoint[] {
    const points = Array.isArray(trend) ? trend : []
    if (points.length === 0) return []

    const rawBenchmark = Array.isArray((benchmark as { points?: unknown })?.points)
        ? ((benchmark as { points: { date: string; value: number }[] }).points)
        : []
    const byDay = new Map(rawBenchmark.map((p) => [String(p.date).slice(0, 10), p.value]))

    // Ölçeklemenin dayanağı endeksin ilk ORTAK günü; portföyün ilk günü
    // endekste yoksa oradan ölçeklemek iki seriyi farklı noktadan başlatırdı.
    const firstShared = points
        .map((p) => byDay.get(String((p as { date: string }).date).slice(0, 10)))
        .find((value) => typeof value === 'number')
    const first = points[0] as { value?: number }
    // Ölçek yoksa çizgi de yok. Sayı olmayan bir başlangıç değerini 0 saymak
    // düz bir sıfır çizgisi üretirdi — endeksin yaptığı hakkında bir iddia,
    // üstelik yanlış olanı.
    const base = typeof first?.value === 'number' && firstShared ? first.value : null

    return points.map((point) => {
        const day = String((point as { date: string }).date).slice(0, 10)
        const raw = byDay.get(day)
        return {
            date: day,
            value: (point as { value: number }).value,
            benchmark:
                typeof raw === 'number' && base !== null && firstShared
                    ? Math.round((base * (raw / firstShared)) * 100) / 100
                    : null,
        }
    })
}
