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
        expect(badge.label).toBe('Anket bekliyor')
        expect(badge.tone).not.toContain('rose')
    })

    it('tanınmayan ve eksik değerler beklemeye düşer', () => {
        expect(alignmentBadge(undefined).label).toBe('Anket bekliyor')
        expect(alignmentBadge(null).label).toBe('Anket bekliyor')
        expect(alignmentBadge('MOSTLY_FINE').label).toBe('Anket bekliyor')
    })
})
