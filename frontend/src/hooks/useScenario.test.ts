/**
 * Senaryo panelinin veri katmanı.
 *
 * Korunan asıl şey: cümle burada ÜRETİLMİYOR, okunuyor. `statement`
 * backend'de kuruluyor, uygunluk kapısına karşı orada test ediliyor ve sohbet
 * de aynı uç noktadan aynı cümleyi alıyor. İstemcide ikinci bir üretici, o
 * testten hiç geçmemiş bir cümlenin ekrana çıkması demekti.
 *
 * İkinci ayrım: bilinmeyen r² ile zayıf r² aynı şey değil. Rozet yalnızca
 * ÖLÇÜLMÜŞ ve düşük çıkmış bir uyum için yanıyor.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import {
    FACTOR_LABELS, SCENARIO_ERROR, STRESS_ERROR, WEAK_FIT_R2, useScenario,
} from './useScenario'
import { apiClient } from '../api/client'

const STATEMENT =
    'BIST 100 %10,0 yükselseydi, son 1 yıl ölçülen duyarlılığa göre portföyünüzün ' +
    'değeri yaklaşık %7,3 artardı — ancak geçmiş fiyat hareketi geleceği belirlemez.'

const SCENARIO = {
    factor: 'XU100', factor_name: 'BIST 100', shock_pct: 10, lookback: '1Y',
    base_currency: 'TRY',
    sensitivity: { beta: 0.7287, correlation: 0.6, r_squared: 0.3621,
                   observation_count: 248, is_statistically_reliable: true },
    estimated_impact_pct: 7.287, estimated_impact_value: 12345.67,
    statement: STATEMENT,
    assumptions: ['Etki doğrusal varsayıldı.'], warnings: [],
}

const STRESS = {
    lookback: '1Y', base_currency: 'TRY', observation_count: 252,
    worst_days: [{ date: '2026-03-01T00:00:00', return_pct: -7.52 }],
    replays: {
        XU100: { start_date: '2026-04-06T00:00:00', end_date: '2026-04-13T00:00:00',
                 factor_move_pct: 9.91, portfolio_move_pct: 7.99, trading_days: 5 },
        XAUUSD: { start_date: '2026-03-11T00:00:00', end_date: '2026-03-23T00:00:00',
                  factor_move_pct: -14.77, portfolio_move_pct: -2.65, trading_days: 5 },
    },
    factor_names: { XU100: 'BIST 100', XAUUSD: 'Ons altın' },
    excluded_symbols: [], warnings: [],
}

beforeEach(() => {
    vi.spyOn(apiClient, 'runScenario').mockResolvedValue(SCENARIO as never)
    vi.spyOn(apiClient, 'getStressTest').mockResolvedValue(STRESS as never)
})
afterEach(() => vi.restoreAllMocks())

describe('useScenario', () => {
    it('stres testini açılışta çeker, senaryoyu çekmez', async () => {
        // Senaryo bir faktör ve şok gerektiriyor; stres testi hiçbir girdi
        // istemiyor ve zaten olanı gösteriyor.
        const { result } = renderHook(() => useScenario('1Y'))
        await waitFor(() => expect(result.current.stressLoading).toBe(false))
        expect(result.current.stress?.observation_count).toBe(252)
        expect(result.current.result).toBeNull()
        expect(apiClient.runScenario).not.toHaveBeenCalled()
    })

    it('cümleyi backendden okur, yeniden yazmaz', async () => {
        const { result } = renderHook(() => useScenario('1Y'))
        await waitFor(() => expect(result.current.stressLoading).toBe(false))
        await act(async () => { await result.current.run('XU100', 10) })
        expect(result.current.result?.statement).toBe(STATEMENT)
    })

    it('seçilen dönemi senaryoya taşır', async () => {
        const { result } = renderHook(() => useScenario('3M'))
        await waitFor(() => expect(result.current.stressLoading).toBe(false))
        await act(async () => { await result.current.run('USDTRY', -20) })
        expect(apiClient.runScenario).toHaveBeenCalledWith('USDTRY', -20, '3M')
        expect(apiClient.getStressTest).toHaveBeenCalledWith('3M')
    })

    it('zayıf uyumu ölçülmüşse işaretler', async () => {
        vi.spyOn(apiClient, 'runScenario').mockResolvedValue({
            ...SCENARIO,
            sensitivity: { ...SCENARIO.sensitivity, r_squared: 0.0011 },
        } as never)
        const { result } = renderHook(() => useScenario('1Y'))
        await act(async () => { await result.current.run('USDTRY', 10) })
        expect(result.current.isWeakFit).toBe(true)
    })

    it('güçlü uyumda rozet yanmaz', async () => {
        const { result } = renderHook(() => useScenario('1Y'))
        await act(async () => { await result.current.run('XU100', 10) })
        expect(result.current.isWeakFit).toBe(false)
    })

    it('ölçülemeyen uyum ZAYIF sayılmaz', async () => {
        // Bilinmeyen bir uyum, zayıf bir uyumdan farklı bir şey.
        vi.spyOn(apiClient, 'runScenario').mockResolvedValue({
            ...SCENARIO,
            sensitivity: { ...SCENARIO.sensitivity, r_squared: null },
        } as never)
        const { result } = renderHook(() => useScenario('1Y'))
        await act(async () => { await result.current.run('USDTRY', 10) })
        expect(result.current.isWeakFit).toBe(false)
    })

    it('eşiğin tam üstü zayıf değildir', async () => {
        vi.spyOn(apiClient, 'runScenario').mockResolvedValue({
            ...SCENARIO,
            sensitivity: { ...SCENARIO.sensitivity, r_squared: WEAK_FIT_R2 },
        } as never)
        const { result } = renderHook(() => useScenario('1Y'))
        await act(async () => { await result.current.run('USDTRY', 10) })
        expect(result.current.isWeakFit).toBe(false)
    })

    it('replayleri hareket BÜYÜKLÜĞÜNE göre sıralar', async () => {
        // Bir çöküş bir sıçrama kadar ilgi çekici; yalnızca yükselişe göre
        // sıralamak en sert olayı listenin dibine atardı.
        const { result } = renderHook(() => useScenario('1Y'))
        await waitFor(() => expect(result.current.stressLoading).toBe(false))
        expect(result.current.replayRows.map((r) => r.symbol)).toEqual(['XAUUSD', 'XU100'])
    })

    it('faktörü adıyla gösterir, sembolüyle değil', async () => {
        const { result } = renderHook(() => useScenario('1Y'))
        await waitFor(() => expect(result.current.stressLoading).toBe(false))
        expect(result.current.replayRows[0].name).toBe('Ons altın')
    })

    it('adı gelmeyen faktör sembolüyle görünür, kaybolmaz', async () => {
        vi.spyOn(apiClient, 'getStressTest').mockResolvedValue({
            ...STRESS, factor_names: {},
        } as never)
        const { result } = renderHook(() => useScenario('1Y'))
        await waitFor(() => expect(result.current.stressLoading).toBe(false))
        expect(result.current.replayRows.map((r) => r.name).sort())
            .toEqual(['XAUUSD', 'XU100'])
    })

    it('senaryo gövdesi eksik gelirse duyarlılık null kalır', async () => {
        vi.spyOn(apiClient, 'runScenario').mockResolvedValue({} as never)
        const { result } = renderHook(() => useScenario('1Y'))
        await act(async () => { await result.current.run('XU100', 10) })
        expect(result.current.sensitivity).toBeNull()
        expect(result.current.isWeakFit).toBe(false)
    })

    it('ölçülen duyarlılık ayrıca okunabilir', async () => {
        const { result } = renderHook(() => useScenario('1Y'))
        await act(async () => { await result.current.run('XU100', 10) })
        expect(result.current.sensitivity?.beta).toBeCloseTo(0.7287)
    })

    it('gövde eksik gelirse panel çökmez', async () => {
        // Ölçüm gösterememek, sayfayı kaybetmekten iyidir.
        vi.spyOn(apiClient, 'getStressTest').mockResolvedValue({} as never)
        const { result } = renderHook(() => useScenario('1Y'))
        await waitFor(() => expect(result.current.stressLoading).toBe(false))
        expect(result.current.worstDays).toEqual([])
        expect(result.current.replayRows).toEqual([])
    })

    it('en kötü günler olduğu gibi taşınır', async () => {
        const { result } = renderHook(() => useScenario('1Y'))
        await waitFor(() => expect(result.current.stressLoading).toBe(false))
        expect(result.current.worstDays[0].return_pct).toBeCloseTo(-7.52)
    })

    it('hiç replay yoksa boş liste döner, hata değil', async () => {
        vi.spyOn(apiClient, 'getStressTest').mockResolvedValue({
            ...STRESS, replays: {}, worst_days: [],
        } as never)
        const { result } = renderHook(() => useScenario('1Y'))
        await waitFor(() => expect(result.current.stressLoading).toBe(false))
        expect(result.current.replayRows).toEqual([])
        expect(result.current.stressError).toBeNull()
    })

    it('senaryo düşerse eski sonucu ekranda bırakmaz', async () => {
        // Kullanıcının SORDUĞU soruya başka bir sorunun cevabını göstermek
        // olurdu.
        const { result } = renderHook(() => useScenario('1Y'))
        await act(async () => { await result.current.run('XU100', 10) })
        expect(result.current.result).not.toBeNull()

        vi.spyOn(apiClient, 'runScenario').mockRejectedValue(new Error('422'))
        await act(async () => { await result.current.run('USDTRY', 10) })
        expect(result.current.error).toBe(SCENARIO_ERROR)
        expect(result.current.result).toBeNull()
        expect(result.current.isWeakFit).toBe(false)
    })

    it('stres testi düşerse söyler', async () => {
        vi.spyOn(apiClient, 'getStressTest').mockRejectedValue(new Error('500'))
        const { result } = renderHook(() => useScenario('1Y'))
        await waitFor(() => expect(result.current.stressLoading).toBe(false))
        expect(result.current.stressError).toBe(STRESS_ERROR)
        expect(result.current.stress).toBeNull()
        expect(result.current.replayRows).toEqual([])
    })

    it('stres testi yeniden yüklenebilir', async () => {
        const { result } = renderHook(() => useScenario('1Y'))
        await waitFor(() => expect(result.current.stressLoading).toBe(false))
        await act(async () => { await result.current.reloadStress() })
        expect(apiClient.getStressTest).toHaveBeenCalledTimes(2)
    })

    it('faiz seçilebilir bir faktör değildir', async () => {
        // Sistemde faiz serisi yok; seçeneği koyup 422 göstermek, var olmayan
        // bir yeteneği vaat etmek olurdu.
        expect(Object.keys(FACTOR_LABELS)).toEqual(
            ['USDTRY', 'EURTRY', 'XU100', 'XAUUSD'],
        )
    })
})
