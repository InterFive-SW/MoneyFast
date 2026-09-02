/**
 * Risk metrik biçimlendirme.
 *
 * Buradaki testlerin çoğu tek bir özelliği koruyor: **ölçülemeyen bir değer
 * asla sıfır olarak gösterilmez.** `null` bir oynaklığı "%0" diye yazmak,
 * kullanıcıya risk almadığını söylemektir.
 */
import { describe, expect, it } from 'vitest'
import {
    METRIC_COPY,
    alignmentBadge,
    benchmarkName,
    describeContribution,
    measurementCaption,
    toComparisonSeries,
    toContributions,
    NOT_MEASURED,
    describeDrawdown,
    describeEffectiveN,
    describeLossEstimate,
    formatDate,
    formatMetric,
    formatPercent,
    formatRatio,
    reliabilityNotice,
    toBreakdown,
} from './riskFormat'

describe('formatPercent', () => {
    it('yüzdeyi Türkçe biçimle yazar', () => {
        expect(formatPercent(0.4796281)).toBe('%47,96')
    })

    it('basamak sayısı ayarlanabilir', () => {
        expect(formatPercent(0.95, 0)).toBe('%95')
    })

    it('ölçülemeyen değer sıfır değil, cümledir', () => {
        expect(formatPercent(null)).toBe(NOT_MEASURED)
        expect(formatPercent(undefined)).toBe(NOT_MEASURED)
        expect(formatPercent(Number.NaN)).toBe(NOT_MEASURED)
    })

    it('gerçek sıfır yine sıfır olarak yazılır', () => {
        /* Ölçülmüş sıfır ile ölçülememiş değer aynı şey değil. */
        expect(formatPercent(0)).toBe('%0,00')
    })
})

describe('formatRatio', () => {
    it('oranı yüzdeye çevirmez', () => {
        expect(formatRatio(0.9969)).toBe('1,00')
        expect(formatRatio(0.039559, 3)).toBe('0,040')
    })

    it('negatif oranı korur', () => {
        expect(formatRatio(-0.5)).toBe('-0,50')
    })

    it('ölçülemeyeni işaretler', () => {
        expect(formatRatio(null)).toBe(NOT_MEASURED)
        expect(formatRatio(undefined)).toBe(NOT_MEASURED)
        expect(formatRatio(Number.NaN)).toBe(NOT_MEASURED)
    })
})

describe('formatMetric', () => {
    it('oynaklık yüzde, Sharpe oran olarak yazılır', () => {
        expect(formatMetric('volatility_annualized', 0.48)).toBe('%48,00')
        expect(formatMetric('sharpe_ratio', 0.9969)).toBe('1,00')
    })

    it('aşağı yönlü sapma da yüzdedir', () => {
        expect(formatMetric('downside_deviation_annualized', 0.2919)).toBe('%29,19')
    })

    it('tanınmayan metrik oran sayılır', () => {
        expect(formatMetric('beta', 0.04)).toBe('0,04')
    })
})

describe('METRIC_COPY', () => {
    it('her metriğin başlığı ve tanımı var', () => {
        for (const [name, copy] of Object.entries(METRIC_COPY)) {
            expect(copy.label, name).toBeTruthy()
            expect(copy.hint, name).toBeTruthy()
        }
    })

    it('hiçbir açıklama alan adı sızdırmaz', () => {
        /* NAMING kuralı: kullanıcı bir veritabanı satırı değil, finansal bir
           cevap okuyor. */
        const text = Object.values(METRIC_COPY)
            .map((c) => `${c.label} ${c.hint}`)
            .join(' ')
        expect(text).not.toMatch(/_[a-z]/)
    })

    it('hiçbir açıklama eşik yargısı içermez', () => {
        const text = Object.values(METRIC_COPY).map((c) => c.hint).join(' ')
        for (const banned of ['yüksek', 'düşük', 'iyi', 'kötü', 'ideal']) {
            expect(text).not.toContain(banned)
        }
    })
})

describe('formatDate', () => {
    it('ISO tarihi Türkçe yazar', () => {
        expect(formatDate('2026-05-05')).toBe('5 Mayıs 2026')
    })

    it('boş ve geçersiz tarih null döner', () => {
        expect(formatDate(null)).toBeNull()
        expect(formatDate(undefined)).toBeNull()
        expect(formatDate('')).toBeNull()
        expect(formatDate('tarih değil')).toBeNull()
    })
})

describe('describeDrawdown', () => {
    const RAW = {
        value: -0.22523,
        peak_date: '2026-05-05',
        trough_date: '2026-08-02',
        recovery_date: null,
        duration_days: 60,
    }

    it('derinliği pozitif yüzde olarak verir', () => {
        expect(describeDrawdown(RAW)?.depth).toBe('%22,52')
    })

    it('tepe ve dip tarihlerini taşır', () => {
        const view = describeDrawdown(RAW)
        expect(view?.peak).toBe('5 Mayıs 2026')
        expect(view?.trough).toBe('2 Ağustos 2026')
    })

    it('toparlanmamış düşüşü toparlanmıştan ayırır', () => {
        /* "Toparlanma yok" ile "veri yok" farklı durumlar. */
        expect(describeDrawdown(RAW)?.recovered).toBe(false)
        expect(describeDrawdown(RAW)?.recovery).toBeNull()
        const healed = describeDrawdown({ ...RAW, recovery_date: '2026-09-01' })
        expect(healed?.recovered).toBe(true)
        expect(healed?.recovery).toBe('1 Eylül 2026')
    })

    it('süre yoksa null taşır', () => {
        expect(describeDrawdown({ ...RAW, duration_days: null })?.durationDays).toBeNull()
    })

    it('ölçülemeyen düşüş için hiçbir şey döndürmez', () => {
        expect(describeDrawdown(null)).toBeNull()
        expect(describeDrawdown('yok')).toBeNull()
        expect(describeDrawdown({ value: null })).toBeNull()
    })
})

describe('describeLossEstimate', () => {
    const RAW = {
        method: 'HISTORICAL',
        confidence_level: 0.95,
        value_fraction: -0.046671,
        value_currency: -18.82,
    }

    it('kaybı pozitif yüzde ve tutar olarak verir', () => {
        const view = describeLossEstimate(RAW, 'var')
        expect(view?.fraction).toBe('%4,67')
        expect(view?.amount).toBeCloseTo(18.82)
        expect(view?.confidence).toBe('%95')
    })

    it('VaR açıklaması bunun bir sınır olmadığını söyler', () => {
        /* MCP sözleşmesinin şartı: tarihsel ölçüm, tahmin değil. */
        expect(describeLossEstimate(RAW, 'var')?.hint).toContain('sınır değildir')
    })

    it('CVaR açıklaması eşiğin aşıldığı günleri anlatır', () => {
        const view = describeLossEstimate(RAW, 'cvar')
        expect(view?.hint).toContain('ortalama kayıp')
        expect(view?.hint).toContain('tahmin değildir')
    })

    it('güven seviyesi yoksa uydurmaz', () => {
        const view = describeLossEstimate({ ...RAW, confidence_level: null }, 'var')
        expect(view?.confidence).toBe(NOT_MEASURED)
    })

    it('tutar yoksa null kalır', () => {
        expect(describeLossEstimate({ ...RAW, value_currency: null }, 'var')?.amount).toBeNull()
    })

    it('ölçülemeyen tahmin için hiçbir şey döndürmez', () => {
        expect(describeLossEstimate(null, 'var')).toBeNull()
        expect(describeLossEstimate(42, 'var')).toBeNull()
        expect(describeLossEstimate({ value_fraction: null }, 'var')).toBeNull()
    })
})

describe('toBreakdown', () => {
    it('ağırlığa göre azalan sıralar', () => {
        expect(toBreakdown({ Technology: 0.3, Energy: 0.7 }).map((s) => s.label)).toEqual([
            'Energy',
            'Technology',
        ])
    })

    it('yüzdeyi hazır verir', () => {
        expect(toBreakdown({ TRY: 0.7 })[0].percent).toBe('%70,0')
    })

    it('UNCLASSIFIED ham hâliyle gösterilmez', () => {
        expect(toBreakdown({ UNCLASSIFIED: 1.0 })[0].label).toBe('Sınıflandırılmamış')
    })

    it('ham ürün tipi enum değeri kullanıcıya çıkmaz', () => {
        /* Gerçek veride `by_asset_class` `{"stock": 1.0}` dönüyor; NAMING
           kuralı alan adları kadar enum değerlerini de yasaklıyor. */
        expect(toBreakdown({ stock: 1.0 })[0].label).toBe('Hisse senedi')
        expect(toBreakdown({ commodity: 1.0 })[0].label).toBe('Emtia')
        expect(toBreakdown({ fx: 1.0 })[0].label).toBe('Döviz')
        expect(toBreakdown({ EQUITY: 1.0 })[0].label).toBe('Hisse senedi')
    })

    it('tanınmayan etiket olduğu gibi geçer', () => {
        /* Sektör adları zaten okunabilir; haritaya hapsetmek yeni bir
           sektörü görünmez kılardı. */
        expect(toBreakdown({ Technology: 1.0 })[0].label).toBe('Technology')
    })

    it('sayı olmayan değerleri atar', () => {
        expect(toBreakdown({ TRY: 0.5, USD: 'çok' })).toHaveLength(1)
    })

    it('boş ve geçersiz girdi boş liste döner', () => {
        expect(toBreakdown(null)).toEqual([])
        expect(toBreakdown('kırılım')).toEqual([])
        expect(toBreakdown({})).toEqual([])
    })
})

describe('describeEffectiveN', () => {
    it('HHI yerine okunabilir bir cümle verir', () => {
        expect(describeEffectiveN(1.61)).toBe('1,6 pozisyona denk')
    })

    it('ölçülemeyeni işaretler', () => {
        expect(describeEffectiveN(null)).toBe(NOT_MEASURED)
        expect(describeEffectiveN(undefined)).toBe(NOT_MEASURED)
        expect(describeEffectiveN(Number.NaN)).toBe(NOT_MEASURED)
    })
})

describe('reliabilityNotice', () => {
    it('güvenilir ölçümde sessiz kalır', () => {
        expect(reliabilityNotice({ is_statistically_reliable: true })).toBeNull()
    })

    it('güvenilir olmayan ölçümü söyler', () => {
        const notice = reliabilityNotice({ is_statistically_reliable: false })
        expect(notice).toContain('güvenilir sayılacak kadar')
    })

    it('dışarıda kalan sembolleri adlandırır', () => {
        /* Sessizce düşürülmüş bir pozisyon, olmayan bir portföy demek. */
        const notice = reliabilityNotice({
            is_statistically_reliable: false,
            excluded_symbols: ['BERA', 'IPEKE'],
        })
        expect(notice).toContain('BERA, IPEKE')
    })

    it('geçersiz girdi için hiçbir şey söylemez', () => {
        expect(reliabilityNotice(null)).toBeNull()
        expect(reliabilityNotice('kalite')).toBeNull()
    })

    it('sembol listesi sayı olmayan bir şeyse cümleyi bozmaz', () => {
        const notice = reliabilityNotice({
            is_statistically_reliable: false,
            excluded_symbols: 'BERA',
        })
        expect(notice).toContain('güvenilir sayılacak kadar')
        expect(notice).not.toContain('BERA')
    })
})


describe('alignmentBadge', () => {
    /* Ham enum kullanıcıya asla yazılmaz -- NAMING kuralı alan adları kadar
       enum değerlerini de kapsıyor. "durumunuz PORTFOLIO_RISKIER" bir
       veritabanı satırı, bir cevap değil. */
    it('hiçbir rozet ham enum göstermez', () => {
        for (const key of ['ALIGNED', 'PORTFOLIO_RISKIER', 'PORTFOLIO_CALMER', 'UNKNOWN']) {
            expect(alignmentBadge(key).label).not.toMatch(/[A-Z]{2,}_/)
        }
    })

    it('portföy beyanın üzerindeyse dikkat çeken tonda', () => {
        expect(alignmentBadge('PORTFOLIO_RISKIER').label).toBe('Beyanınızın üzerinde')
        expect(alignmentBadge('PORTFOLIO_RISKIER').tone).toContain('rose')
    })

    it('portföy beyanın altındaysa uyarı tonu kullanmaz', () => {
        /* Beyandan daha sakin bir portföy bir sorun değil; kırmızı yazmak
           kullanıcıya olmayan bir problem bildirir. */
        expect(alignmentBadge('PORTFOLIO_CALMER').tone).not.toContain('rose')
    })

    it('aynı bandı olumlu tonda gösterir', () => {
        expect(alignmentBadge('ALIGNED').tone).toContain('emerald')
    })

    it('anket doldurulmadığında nötr kalır', () => {
        /* UNKNOWN bir uyuşmazlık DEĞİL: taraflardan biri henüz yok.
           Kırmızı bir "bilinmiyor" doldurulmamış formu sorun gibi okutur. */
        const badge = alignmentBadge('UNKNOWN')
        expect(badge.label).toBe('Test bekliyor')
        expect(badge.tone).not.toContain('rose')
    })

    it('tanınmayan ve eksik değerler beklemeye düşer', () => {
        expect(alignmentBadge(undefined).label).toBe('Test bekliyor')
        expect(alignmentBadge(null).label).toBe('Test bekliyor')
        expect(alignmentBadge('MOSTLY_FINE').label).toBe('Test bekliyor')
    })
})


describe('measurementCaption', () => {
    /* Sayfa Sharpe oranını ve betayı gösteriyordu ama ikisinin de neye göre
       hesaplandığını söylemiyordu. MCP sözleşmesi Sharpe sunulurken faizin
       açıklanmasını şart koşuyor; sohbet yolu yapıyordu, sayfa yapmıyordu. */
    const WINDOW = {
        start_date: '2025-01-27',
        end_date: '2026-08-24',
        observation_count: 253,
        frequency: 'DAILY',
    }
    const ASSUMPTIONS = {
        benchmark_symbol: 'XU100',
        benchmark_history_available: true,
        risk_free_rate: 0.425,
        risk_free_rate_source: 'FIXTURE_POLICY_RATE',
    }

    it('aralığı, ölçütü ve faizi tek satırda söyler', () => {
        const caption = measurementCaption(WINDOW, ASSUMPTIONS)
        expect(caption).toContain('253 işlem günü')
        expect(caption).toContain('BIST 100')
        expect(caption).toContain('%42,5')
    })

    it('hiçbir alan adı veya enum ekrana çıkmaz', () => {
        const caption = measurementCaption(WINDOW, ASSUMPTIONS) ?? ''
        expect(caption).not.toContain('XU100')
        expect(caption).not.toContain('FIXTURE_POLICY_RATE')
        expect(caption).not.toMatch(/[a-z]+_[a-z]+/)
    })

    it('geçmişi olmayan bir ölçütün adını anmaz', () => {
        /* Adını yazıp altında "ölçülemedi" göstermek, olmayan bir
           karşılaştırma vaat eder. */
        const caption = measurementCaption(WINDOW, {
            ...ASSUMPTIONS,
            benchmark_history_available: false,
        })
        expect(caption).not.toContain('BIST 100')
        expect(caption).toContain('253 işlem günü')
    })

    it('caller tarafından verilen faizi politika faizi diye anmaz', () => {
        const caption = measurementCaption(WINDOW, {
            ...ASSUMPTIONS,
            risk_free_rate_source: 'CALLER_SUPPLIED',
        })
        expect(caption).toContain('belirtilen faiz')
        expect(caption).not.toContain('politika faizi')
    })

    it('tarih yoksa yalnızca gözlem sayısını söyler', () => {
        const caption = measurementCaption(
            { observation_count: 67 },
            {},
        )
        expect(caption).toBe('67 işlem günü')
    })

    it('söylenecek bir şey yoksa satır hiç yazılmaz', () => {
        /* Eksik bir aralığı "—" ile doldurmak, ölçümün kapsamı hakkında
           bilgi veriyormuş gibi yapmak olurdu. */
        expect(measurementCaption({}, {})).toBeNull()
        expect(measurementCaption(null, null)).toBeNull()
        expect(measurementCaption(undefined, undefined)).toBeNull()
    })

    it('bozuk tarihler satırı çökertmez', () => {
        const caption = measurementCaption(
            { start_date: 'dün', end_date: '', observation_count: 12 },
            {},
        )
        expect(caption).toBe('12 işlem günü')
    })
})

describe('benchmarkName', () => {
    it('bilinen endeksleri okunur adıyla verir', () => {
        expect(benchmarkName('XU100')).toBe('BIST 100')
        expect(benchmarkName('spx')).toBe('S&P 500')
    })

    it('tanımadığı sembolü olduğu gibi bırakır', () => {
        /* Bir haritaya hapsetmek, yeni bir ölçüt eklendiği gün onu
           görünmez kılardı. */
        expect(benchmarkName('XU050')).toBe('XU050')
    })

    it('sembol yoksa ad da yok', () => {
        expect(benchmarkName(null)).toBeNull()
        expect(benchmarkName('')).toBeNull()
        expect(benchmarkName(42)).toBeNull()
    })
})


describe('toContributions', () => {
    /* Ağırlık ve risk payı yan yana duruyor çünkü İKİSİNİN AYRIŞMASI asıl
       bilgi: yoğunlaşma "etkin çeşitlilik 5,8" der ama beş pozisyonun beşi de
       bankaysa birlikte hareket ederler. */
    const RAW = [
        { symbol: 'AKBNK', weight: 0.3, contribution: 0.55 },
        { symbol: 'DOAS', weight: 0.6, contribution: 0.5 },
        { symbol: 'ALTIN', weight: 0.1, contribution: -0.05 },
    ]

    it('payı büyükten küçüğe sıralar', () => {
        expect(toContributions(RAW).map((r) => r.symbol)).toEqual([
            'AKBNK', 'DOAS', 'ALTIN',
        ])
    })

    it('ağırlıkla pay arasındaki farkı hesaplar', () => {
        const rows = toContributions(RAW)
        expect(rows[0].gap).toBeCloseTo(0.25)
        expect(rows[1].gap).toBeCloseTo(-0.1)
    })

    it('eksi payı kırpmaz', () => {
        /* Dalgalanmayı azaltan bir pozisyon bir bulgudur, hata değil. */
        expect(toContributions(RAW)[2].contribution).toBe(-0.05)
    })

    it('şekli bozuk satırları atar', () => {
        expect(
            toContributions([
                { symbol: 'A', weight: 0.5, contribution: 0.5 },
                { symbol: 'B', weight: null, contribution: 0.5 },
                null,
                { weight: 0.1, contribution: 0.1 },
            ]),
        ).toHaveLength(1)
    })

    it('liste değilse boş döner', () => {
        expect(toContributions(null)).toEqual([])
        expect(toContributions({ symbol: 'A' })).toEqual([])
        expect(toContributions(undefined)).toEqual([])
    })
})

describe('describeContribution', () => {
    const row = (weight: number, contribution: number) => ({
        symbol: 'X', weight, contribution, gap: contribution - weight,
    })

    it('hiçbir cümle ne yapılacağını söylemez', () => {
        /* Riskin nereden geldiğini söylemek bir ÖLÇÜM, azaltmayı önermek bir
           TAVSİYE. Ayrım kipte: "dalgalanmayı azaltan" pozisyonun ne yaptığını
           anlatır, "riskinizi azaltın" kullanıcıya ne yapacağını söyler.
           Aranan şey emir kipi ve öneri sözcükleri, kökler değil. */
        const sentences = [
            describeContribution(row(0.3, 0.6)),
            describeContribution(row(0.6, 0.3)),
            describeContribution(row(0.5, 0.5)),
            describeContribution(row(0.2, -0.1)),
        ]
        for (const sentence of sentences) {
            expect(sentence).not.toMatch(
                /\b(azalt|artır|çeşitlendir|dengele|sat|al)(ın|ınız|manız|malısınız)\b/i,
            )
            expect(sentence).not.toMatch(/öneri|tavsiye|gerekir|meli|malı/i)
        }
    })

    it('cümleler geçmişi anlatır, gelecek için bir şey vaat etmez', () => {
        expect(describeContribution(row(0.2, -0.1))).toMatch(/etmiş|ediyor/)
        expect(describeContribution(row(0.6, 0.3))).toMatch(/etmiş|ediyor/)
    })

    it('payı ağırlığından büyükse birlikte hareketi söyler', () => {
        expect(describeContribution(row(0.3, 0.6))).toContain('birlikte hareket')
    })

    it('payı ağırlığından küçükse bağımsızlığı söyler', () => {
        expect(describeContribution(row(0.6, 0.3))).toContain('bağımsız')
    })

    it('ağırlığa yakın bir pay hakkında bir şey uydurmaz', () => {
        expect(describeContribution(row(0.5, 0.52))).toContain('yaklaşık aynı')
    })

    it('eksi pay dalgalanmayı azaltmak diye okunur', () => {
        expect(describeContribution(row(0.2, -0.1))).toContain('azaltan')
    })
})


describe('toComparisonSeries', () => {
    /* Endeks, portföyün İLK değerine ölçekleniyor: ikisi aynı noktadan
       başlar ve sonraki ayrışma tamamen göreli performanstır. */
    const TREND = [
        { date: '2026-08-05T00:00:00Z', value: 1000 },
        { date: '2026-08-06T00:00:00Z', value: 1100 },
        { date: '2026-08-07T00:00:00Z', value: 900 },
    ]
    const BENCH = {
        symbol: 'XU100',
        points: [
            { date: '2026-08-05T00:00:00Z', value: 9000 },
            { date: '2026-08-06T00:00:00Z', value: 9450 },
            { date: '2026-08-07T00:00:00Z', value: 8100 },
        ],
    }

    it('endeksi portföyün başlangıç değerine ölçekler', () => {
        const series = toComparisonSeries(TREND, BENCH)
        expect(series[0].benchmark).toBe(1000)
        // Endeks %5 yükseldi: 1000 -> 1050.
        expect(series[1].benchmark).toBe(1050)
        // %10 düştü: 1000 -> 900.
        expect(series[2].benchmark).toBe(900)
    })

    it('portföy değerlerini olduğu gibi bırakır', () => {
        expect(toComparisonSeries(TREND, BENCH).map((p) => p.value)).toEqual([
            1000, 1100, 900,
        ])
    })

    it('endeksin işlem görmediği günü boş bırakır, önceki değere sabitlemez', () => {
        /* Yatay çizmek, olmayan bir hareketsizliği göstermek olur. */
        const series = toComparisonSeries(TREND, {
            symbol: 'XU100',
            points: [BENCH.points[0], BENCH.points[2]],
        })
        expect(series[1].benchmark).toBeNull()
        expect(series[2].benchmark).toBe(900)
    })

    it('ölçekleme ilk ORTAK günden yapılır', () => {
        /* Portföyün ilk günü endekste yoksa oradan ölçeklemek iki seriyi
           farklı noktadan başlatırdı. */
        const series = toComparisonSeries(TREND, {
            symbol: 'XU100',
            points: [BENCH.points[1], BENCH.points[2]],
        })
        expect(series[0].benchmark).toBeNull()
        expect(series[1].benchmark).toBe(1000)
    })

    it('endeks yoksa yalnızca portföy kalır', () => {
        const series = toComparisonSeries(TREND, null)
        expect(series).toHaveLength(3)
        expect(series.every((p) => p.benchmark === null)).toBe(true)
    })

    it('trend yoksa seri de yok', () => {
        expect(toComparisonSeries(null, BENCH)).toEqual([])
        expect(toComparisonSeries([], BENCH)).toEqual([])
    })

    it('ölçeklenecek bir başlangıç değeri yoksa çizgi çizilmez', () => {
        /* Sayı olmayan bir başlangıcı 0 saymak düz bir sıfır çizgisi
           üretirdi — endeksin yaptığı hakkında yanlış bir iddia. */
        const series = toComparisonSeries(
            [{ date: '2026-08-05T00:00:00Z', value: null }, TREND[1]],
            BENCH,
        )
        expect(series.every((p) => p.benchmark === null)).toBe(true)
    })

    it('tarihleri güne indirger', () => {
        expect(toComparisonSeries(TREND, BENCH)[0].date).toBe('2026-08-05')
    })
})
