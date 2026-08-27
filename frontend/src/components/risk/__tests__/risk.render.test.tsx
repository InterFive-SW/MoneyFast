/**
 * The Risk page, mounted against a real /api/risk/profile payload — and
 * against the empty-shaped one a brand-new account produces.
 *
 * The page previously read a fixture, so every widget was guaranteed a
 * complete object with a number in every field. Now the score, the level and
 * the savings rate can each legitimately be null, and each of those is a
 * different way for a component to crash on render.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, act, fireEvent } from '@testing-library/react'
import * as apiClientModule from '../../../api/client'
import { MemoryRouter } from 'react-router-dom'
import payloads from '../../widgets/__tests__/payloads.json'

import Risk from '../../../pages/Risk'

const PROFILE = (payloads as Record<string, any>)['/api/risk/profile']

/** What the endpoint returns for someone with no positions and no ledger. */
const EMPTY = {
  as_of: new Date().toISOString(),
  score: null,
  level: null,
  components: [
    { name: 'volatility', measured: null, weight: 45, penalty: null },
    { name: 'concentration', measured: null, weight: 35, penalty: null },
    { name: 'drawdown', measured: null, weight: 20, penalty: null },
  ],
  findings: [],
  suggestions: [],
  cashflow: {
    period: 'Son 30 gün', currency_code: 'TRY',
    monthly_income: 0, monthly_expense: 0, savings_rate: null,
  },
  metrics: {},
  position_count: 0,
  warnings: ['Portföyünüzde değerlenebilir pozisyon bulunamadı.'],
}

let consoleError: ReturnType<typeof vi.spyOn>

function stubFetch(body: unknown, ok = true) {
  vi.stubGlobal('fetch', vi.fn(() =>
    Promise.resolve({ ok, status: ok ? 200 : 500, json: () => Promise.resolve(body) }),
  ))
}

beforeEach(() => {
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.stubGlobal('ResizeObserver', class {
    observe() {} unobserve() {} disconnect() {}
  } as never)
  localStorage.setItem('access_token', 'test-token')
})
afterEach(() => {
  consoleError.mockRestore()
  vi.unstubAllGlobals()
  localStorage.clear()
})

async function mount() {
  const view = render(<MemoryRouter><Risk /></MemoryRouter>)
  await waitFor(() => expect(view.container).toBeTruthy())
  await new Promise((r) => setTimeout(r, 80))
  const crash = consoleError.mock.calls.find((c: unknown[]) =>
    String(c[0]).includes('The above error occurred'))
  expect(crash?.[0] ?? null, 'Risk page threw during render').toBe(null)
  return view
}

describe('Risk page', () => {
  it('renders a scored profile', async () => {
    stubFetch(PROFILE)
    const { container } = await mount()
    expect(container.textContent).toContain('Risk Analizi')
    expect(container.textContent).toContain('Puan nasıl oluştu')
  })

  it('survives a brand-new account with nothing to measure', async () => {
    stubFetch(EMPTY)
    const { container } = await mount()
    // A dash, not a 0: zero would read as "maximum risk" for someone who
    // holds nothing at all.
    expect(container.textContent).toContain('—')
    expect(container.textContent).toContain('hesaplanamadı')
  })

  it('names what was left out instead of hiding it', async () => {
    stubFetch({ ...PROFILE, warnings: ['BERA: fiyat yok, hesaba katılmadı'] })
    const { container } = await mount()
    expect(container.textContent).toContain('BERA')
  })

  it('shows a failure message rather than a blank page', async () => {
    stubFetch({}, false)
    const { container } = await mount()
    expect(container.textContent).toContain('ulaşılamadı')
  })

  it('reports an unknown savings rate rather than 0%', async () => {
    stubFetch({
      ...PROFILE,
      cashflow: { ...PROFILE.cashflow, monthly_income: 0, savings_rate: null },
    })
    const { container } = await mount()
    expect(container.textContent).toContain('Tasarruf oranı hesaplanamadı')
  })
})

// --------------------------------------------------------------------------
// Faz 1: motorun hesaplayıp sayfanın hiç göstermediği blok
//
// `GET /api/risk/profile` bu metrikleri baştan beri döndürüyordu; sayfa
// `data.metrics`'i alıp render etmeden atıyordu. Bu testler onların ekrana
// ulaştığını sabitliyor.
// --------------------------------------------------------------------------
describe('Risk page — ölçülen metrikler', () => {
  it('VaR, CVaR, Sharpe ve betayı gösterir', async () => {
    stubFetch(PROFILE)
    const { container } = await mount()
    const text = container.textContent ?? ''
    expect(text).toContain('Ölçülen Risk Metrikleri')
    expect(text).toContain('Sharpe oranı')
    expect(text).toContain('Endekse duyarlılık')
    expect(text).toContain('Günlük kayıp eşiği')
  })

  it('en derin düşüşü tarihleriyle birlikte anlatır', async () => {
    stubFetch(PROFILE)
    const { container } = await mount()
    const text = container.textContent ?? ''
    expect(text).toContain('En derin düşüş')
    // payloads.json'daki gerçek yanıt: 5 Mayıs zirvesi, 2 Ağustos dibi.
    expect(text).toContain('5 Mayıs 2026')
    expect(text).toContain('2 Ağustos 2026')
  })

  it('toparlanmamış bir düşüşü toparlanmış gibi göstermez', async () => {
    /* `recovery_date: null` "toparlanma yok" demek, "veri yok" değil. */
    stubFetch(PROFILE)
    const { container } = await mount()
    expect(container.textContent).toContain('henüz toparlanmadı')
  })

  it('yoğunlaşma kırılımlarını gösterir', async () => {
    stubFetch(PROFILE)
    const { container } = await mount()
    const text = container.textContent ?? ''
    expect(text).toContain('Yoğunlaşma')
    expect(text).toContain('pozisyona denk')
    expect(text).toContain('En büyük pozisyon')
    // Ham enum kullanıcıya çıkmaz.
    expect(text).not.toContain('UNCLASSIFIED')
  })

  it('hiçbir alan adını ekrana sızdırmaz', async () => {
    /* NAMING kuralı: `max_drawdown`, `value_fraction`, `hhi` gibi anahtarlar
       kullanıcıya gösterilmez. */
    stubFetch(PROFILE)
    const { container } = await mount()
    const text = container.textContent ?? ''
    for (const key of ['max_drawdown', 'value_fraction', 'sharpe_ratio', 'by_sector', 'hhi']) {
      expect(text, key).not.toContain(key)
    }
  })

  it('ölçülemeyen metriği sıfır olarak göstermez', async () => {
    /* Sıfır bir oynaklık "risk yok" diye okunur. */
    stubFetch({
      ...PROFILE,
      metrics: {
        ...PROFILE.metrics,
        sharpe_ratio: null,
        beta: null,
        correlation_to_benchmark: null,
      },
    })
    const { container } = await mount()
    expect(container.textContent).toContain('ölçülemedi')
  })

  it('pozisyon yokken metrik panelini hiç çizmez', async () => {
    stubFetch({ ...PROFILE, position_count: 0, metrics: {} })
    const { container } = await mount()
    expect(container.textContent).not.toContain('Ölçülen Risk Metrikleri')
    expect(container.textContent).toContain('hesaplanamadı')
  })

  it('pencere seçicisini sunar', async () => {
    /* Uç nokta `lookback`'i baştan beri kabul ediyordu; istemci hiç
       geçmiyordu, dolayısıyla pencere değiştirilemiyordu. */
    stubFetch(PROFILE)
    const { container } = await mount()
    const text = container.textContent ?? ''
    expect(text).toContain('1 Ay')
    expect(text).toContain('1 Yıl')
  })
})

// --------------------------------------------------------------------------
// Kullanıcı dostu katman: düz Türkçe özet, terim açıklamaları, öğretici boş
// durum. Sayfa doğrudan bir rakam yığınıyla açılıyordu.
// --------------------------------------------------------------------------
describe('Risk page — anlaşılırlık', () => {
  it('rakamlardan önce düz Türkçe bir özet gösterir', async () => {
    stubFetch(PROFILE)
    const { container } = await mount()
    const text = container.textContent ?? ''
    expect(text).toContain('Kısaca')
    expect(text).toContain('dalgalandı')
  })

  it('puan ölçeğinin yönünü söyler', async () => {
    /* Puan TERS: 100 sakin demek ama sayfanın adı "Risk Analizi". */
    stubFetch(PROFILE)
    const { container } = await mount()
    const text = container.textContent ?? ''
    expect(text).toContain('daha sakin')
    expect(text).toContain('daha oynak')
  })

  it('her metriğin yanında açıklama düğmesi var', async () => {
    stubFetch(PROFILE)
    const { container } = await mount()
    const buttons = container.querySelectorAll('button[aria-label$="nedir?"]')
    expect(buttons.length).toBeGreaterThan(4)
  })

  it('açıklama düğmesi klavyeyle erişilebilir gerçek bir düğme', async () => {
    /* Salt hover mobilde erişilemez ve klavye kullanıcısını dışarıda bırakır. */
    stubFetch(PROFILE)
    const { container } = await mount()
    const button = container.querySelector('button[aria-label$="nedir?"]')
    expect(button?.tagName).toBe('BUTTON')
    expect(button?.getAttribute('aria-expanded')).toBe('false')
  })

  it('tıklanınca tanımı ve ölçeğini açar', async () => {
    stubFetch(PROFILE)
    const { container } = await mount()
    const button = container.querySelector<HTMLButtonElement>(
      'button[aria-label="Risk puanı nedir?"]',
    )
    expect(button).not.toBeNull()
    act(() => button!.click())
    const panel = container.querySelector('[role="tooltip"]')
    expect(panel?.textContent).toContain('TERSTİR')
    expect(panel?.textContent).toContain('Ölçek')
  })

  it('boş portföyde çıkmaz sokak yerine ne olacağını anlatır', async () => {
    stubFetch({ ...PROFILE, position_count: 0, metrics: {} })
    const { container } = await mount()
    const text = container.textContent ?? ''
    expect(text).toContain('önce bir portföy gerekiyor')
    expect(text).toContain('Piyasalara göz at')
  })

  it('boş portföyde özet kartını hiç çizmez', async () => {
    stubFetch({ ...PROFILE, position_count: 0, metrics: {} })
    const { container } = await mount()
    expect(container.textContent).not.toContain('Kısaca')
  })
})

// --------------------------------------------------------------------------
// Faz 2: risk tolerans anketi ve uyum karşılaştırması
// --------------------------------------------------------------------------
const DECLARED = {
  tolerance_level: 'Orta',
  investment_horizon: '3-5 yıl',
  assessed_at: '2026-08-27T10:00:00Z',
  questionnaire_version: 'v1',
}

describe('Risk page — uyum karşılaştırması', () => {
  it('anket doldurulmamışken sayfayı kapatmaz, çağrı gösterir', async () => {
    /* Yumuşak kapı: ölçüm gösterilir, karşılaştırma bekler. Sayfayı
       kapatmak, kullanıcıyı kendi ölçümünden de mahrum bırakırdı. */
    stubFetch({ ...PROFILE, declared: null, suitability: { alignment: 'UNKNOWN' } })
    const { container } = await mount()
    const text = container.textContent ?? ''
    expect(text).toContain('Ankete başla')
    expect(text).toContain('Ölçülen Risk Metrikleri')
  })

  it('anketin bir uygunluk kararı olmadığını söyler', async () => {
    stubFetch({ ...PROFILE, declared: null, suitability: { alignment: 'UNKNOWN' } })
    const { container } = await mount()
    expect(container.textContent).toContain('uygunluk değerlendirmesi değildir')
  })

  it('beyan varsa ölçüm ile beyanı yan yana koyar', async () => {
    stubFetch({
      ...PROFILE,
      declared: DECLARED,
      suitability: {
        measured_level: 'Yüksek',
        declared_tolerance: 'Orta',
        alignment: 'PORTFOLIO_RISKIER',
        statement:
          'Ölçülen portföy riskiniz "Yüksek" seviyesinde; ankette belirttiğiniz tolerans "Orta". Portföy, beyan ettiğiniz bandın üzerinde ölçülüyor.',
      },
    })
    const { container } = await mount()
    const text = container.textContent ?? ''
    expect(text).toContain('Ölçülen portföy riski')
    expect(text).toContain('Beyan ettiğiniz tolerans')
    expect(text).toContain('bandın üzerinde ölçülüyor')
    expect(text).toContain('3-5 yıl')
  })

  it('karşılaştırma cümlesi bir direktif içermez', async () => {
    stubFetch({
      ...PROFILE,
      declared: DECLARED,
      suitability: {
        measured_level: 'Yüksek',
        declared_tolerance: 'Orta',
        alignment: 'PORTFOLIO_RISKIER',
        statement:
          'Ölçülen portföy riskiniz "Yüksek" seviyesinde; ankette belirttiğiniz tolerans "Orta". Portföy, beyan ettiğiniz bandın üzerinde ölçülüyor.',
      },
    })
    const { container } = await mount()
    const text = (container.textContent ?? '').toLocaleLowerCase('tr-TR')
    for (const banned of ['azaltın', 'artırın', 'satın alın', 'size uygun']) {
      expect(text, banned).not.toContain(banned)
    }
  })

  it('anketi başlatan düğme modalı açar', async () => {
    // Profil ve anket iki ayrı uç nokta; tek gövdeli stub anket isteğine
    // profil yanıtı döndürüyor ve akış gerçekte olmayan bir şekli görüyor.
    vi.stubGlobal('fetch', vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve(
            String(url).includes('/questionnaire')
              ? { version: 'v1', questions: [
                  { key: 'horizon', prompt: 'Ne zaman?', helper: null,
                    options: [{ value: 'over_5y', label: '5 yıldan uzun' }] },
                ] }
              : { ...PROFILE, declared: null, suitability: { alignment: 'UNKNOWN' } },
          ),
      }),
    ))
    const { container } = await mount()
    const start = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Ankete başla',
    )
    expect(start).toBeDefined()
    await act(async () => { start!.click() })
    expect(container.querySelector('[role="dialog"]')).not.toBeNull()
    expect(container.textContent).toContain('Risk tolerans anketi')
  })

  it('bozuk bir anket yanıtı sayfayı çökertmez', async () => {
    /* Şekli bozuk bir yanıt anketi açamaz ama ölçümü de yok etmemeli. */
    stubFetch({ ...PROFILE, declared: null, suitability: { alignment: 'UNKNOWN' } })
    const { container } = await mount()
    const start = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Ankete başla',
    )
    await act(async () => { start!.click() })
    expect(container.querySelector('[role="dialog"]')).not.toBeNull()
  })
})

// --------------------------------------------------------------------------
// Faz 3: "ne olur?" simülasyonu
// --------------------------------------------------------------------------
const SIMULATION = {
  as_of: '2026-08-27T10:00:00Z',
  current: {
    score: 83.4, level: 'Düşük', volatility: 0.18, hhi: 0.16,
    effective_n: 6.1, max_drawdown: -0.11, position_count: 14,
  },
  hypothetical: {
    score: 78.2, level: 'Düşük', volatility: 0.21, hhi: 0.22,
    effective_n: 4.5, max_drawdown: -0.13, position_count: 15,
  },
  deltas: { score: -5.2, volatility: 0.03, hhi: 0.06, effective_n: -1.6, max_drawdown: -0.02 },
  changes: [{ symbol: 'NVDA', quantity_delta: 10, applied: true, note: null }],
  warnings: [],
}

describe('Risk page — ne olurdu', () => {
  it('sembol ve adet girişi sunar', async () => {
    stubFetch(PROFILE)
    const { container } = await mount()
    expect(container.textContent).toContain('Ne olurdu?')
    expect(container.querySelector('input[aria-label="Sembol"]')).not.toBeNull()
    expect(container.querySelector('input[aria-label="Adet"]')).not.toBeNull()
  })

  it('hiçbir emir iletilmediğini söyler', async () => {
    stubFetch(PROFILE)
    const { container } = await mount()
    expect(container.textContent).toContain('Hiçbir emir iletilmez')
  })

  it('girdi tamamlanmadan hesaplama düğmesi kapalı', async () => {
    stubFetch(PROFILE)
    const { container } = await mount()
    const button = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Hesapla',
    )
    expect((button as HTMLButtonElement).disabled).toBe(true)
  })

  it('sonuç geldiğinde iki ölçümü yan yana koyar', async () => {
    stubFetch(PROFILE)
    const { container } = await mount()
    vi.spyOn(apiClientModule.apiClient, 'simulateRisk').mockResolvedValue(SIMULATION as never)

    const symbol = container.querySelector('input[aria-label="Sembol"]') as HTMLInputElement
    const qty = container.querySelector('input[aria-label="Adet"]') as HTMLInputElement
    await act(async () => {
      fireEvent.change(symbol, { target: { value: 'NVDA' } })
      fireEvent.change(qty, { target: { value: '10' } })
    })
    const button = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Hesapla',
    ) as HTMLButtonElement
    await act(async () => { button.click() })

    const text = container.textContent ?? ''
    expect(text).toContain('Şimdi')
    expect(text).toContain('Sonra')
    expect(text).toContain('6,1 pozisyona denk')
    expect(text).toContain('4,5 pozisyona denk')
  })

  it('sonuç hiçbir yerde daha iyi/kötü demez', async () => {
    /* Hesap makinesi, öneri motoru değil: iki ölçüm konur, yorumu okuyan yapar. */
    stubFetch(PROFILE)
    const { container } = await mount()
    vi.spyOn(apiClientModule.apiClient, 'simulateRisk').mockResolvedValue(SIMULATION as never)
    const symbol = container.querySelector('input[aria-label="Sembol"]') as HTMLInputElement
    const qty = container.querySelector('input[aria-label="Adet"]') as HTMLInputElement
    await act(async () => {
      fireEvent.change(symbol, { target: { value: 'NVDA' } })
      fireEvent.change(qty, { target: { value: '10' } })
    })
    const button = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Hesapla',
    ) as HTMLButtonElement
    await act(async () => { button.click() })

    const text = (container.textContent ?? '').toLocaleLowerCase('tr-TR')
    for (const banned of ['daha iyi', 'daha kötü', 'tavsiye', 'öneririz']) {
      expect(text, banned).not.toContain(banned)
    }
  })

  it('uygulanamayan bir değişikliği sessizce yutmaz', async () => {
    stubFetch(PROFILE)
    const { container } = await mount()
    vi.spyOn(apiClientModule.apiClient, 'simulateRisk').mockResolvedValue({
      ...SIMULATION,
      changes: [{ symbol: 'YOKBOYLE', quantity_delta: 5, applied: false, note: 'Bu sembol bulunamadı.' }],
    } as never)
    const symbol = container.querySelector('input[aria-label="Sembol"]') as HTMLInputElement
    const qty = container.querySelector('input[aria-label="Adet"]') as HTMLInputElement
    await act(async () => {
      fireEvent.change(symbol, { target: { value: 'YOKBOYLE' } })
      fireEvent.change(qty, { target: { value: '5' } })
    })
    const button = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Hesapla',
    ) as HTMLButtonElement
    await act(async () => { button.click() })
    expect(container.textContent).toContain('Bu sembol bulunamadı.')
  })
})

// --------------------------------------------------------------------------
// Faz 4: risk geçmişi
// --------------------------------------------------------------------------
describe('Risk page — geçmiş', () => {
  /** Profil ve geçmiş iki ayrı uç nokta; tek gövdeli stub ikisine de aynı
   *  yanıtı verir ve panel gerçekte olmayan bir şekli görür. */
  function stubBoth(historyBody: unknown) {
    vi.stubGlobal('fetch', vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve(String(url).includes('/risk/history') ? historyBody : PROFILE),
      }),
    ))
  }

  it('hiç ölçüm yokken ne zaman çizileceğini söyler', async () => {
    stubBoth({ lookback: '1Y', days: 90, points: [] })
    const { container } = await mount()
    expect(container.textContent).toContain('Henüz kayıtlı ölçüm yok')
  })

  it('tek ölçümden çizgi çizmez', async () => {
    /* Tek noktalı bir çizgi "değişim yok" gibi okunur; oysa ikinci gün
       henüz gelmemiştir. */
    stubBoth({
      lookback: '1Y', days: 90,
      points: [{ captured_on: '2026-08-27', score: 83.4, level: 'Düşük',
                 volatility: 0.18, hhi: 0.16, max_drawdown: -0.11, position_count: 14 }],
    })
    const { container } = await mount()
    expect(container.textContent).toContain('Şimdilik tek bir ölçüm var')
  })

  it('iki ölçümden seyri ve değişimi gösterir', async () => {
    stubBoth({
      lookback: '1Y', days: 90,
      points: [
        { captured_on: '2026-08-25', score: 80.0, level: 'Düşük',
          volatility: 0.19, hhi: 0.17, max_drawdown: -0.12, position_count: 14 },
        { captured_on: '2026-08-27', score: 83.4, level: 'Düşük',
          volatility: 0.18, hhi: 0.16, max_drawdown: -0.11, position_count: 14 },
      ],
    })
    const { container } = await mount()
    const text = container.textContent ?? ''
    expect(text).toContain('Risk puanınızın seyri')
    expect(text).toContain('+3,4 puan')
    expect(text).toContain('Ölçüm penceresi: 1Y')
  })

  it('geçmişe dönük puan üretmediğini açıkça söyler', async () => {
    stubBoth({ lookback: '1Y', days: 90, points: [] })
    const { container } = await mount()
    expect(container.textContent).toContain('Geçmişe dönük')
  })
})
