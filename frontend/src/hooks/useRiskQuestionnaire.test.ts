/**
 * Risk tolerans anketinin durum makinesi.
 *
 * Korunan asıl özellik: eksik bir anket gönderilemez. Boşları sıfır sayıp
 * puanlamak, yarıda bırakan birine temkinli bir tolerans atfeder — ve o
 * tolerans sonra kendi portföyüyle karşılaştırılır.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import {
    QUESTIONNAIRE_LOAD_ERROR,
    QUESTIONNAIRE_SAVE_ERROR,
    useRiskQuestionnaire,
} from './useRiskQuestionnaire'
import { apiClient } from '../api/client'

const QUESTIONS = [
    {
        key: 'horizon',
        prompt: 'Ne zaman kullanacaksınız?',
        helper: 'Kısa vade dayanma imkânını sınırlar.',
        options: [
            { value: 'under_1y', label: '1 yıldan kısa' },
            { value: 'over_5y', label: '5 yıldan uzun' },
        ],
    },
    {
        key: 'goal',
        prompt: 'Önceliğiniz nedir?',
        helper: null,
        options: [
            { value: 'preserve', label: 'Korumak' },
            { value: 'growth', label: 'Büyümek' },
        ],
    },
]

beforeEach(() => {
    vi.spyOn(apiClient, 'getRiskQuestionnaire').mockResolvedValue({
        version: 'v1',
        questions: QUESTIONS,
    })
    vi.spyOn(apiClient, 'submitRiskAssessment').mockResolvedValue({
        tolerance_level: 'Orta',
        investment_horizon: '3-5 yıl',
        assessed_at: '2026-08-27T10:00:00Z',
        questionnaire_version: 'v1',
        raw_score: 50,
    })
})
afterEach(() => vi.restoreAllMocks())

async function loaded(onSaved?: () => void) {
    const view = renderHook(() => useRiskQuestionnaire(onSaved))
    await act(async () => { await view.result.current.load() })
    return view
}

describe('yükleme', () => {
    it('soruları getirir ve ilkinden başlar', async () => {
        const { result } = await loaded()
        expect(result.current.total).toBe(2)
        expect(result.current.current?.key).toBe('horizon')
        expect(result.current.index).toBe(0)
    })

    it('yüklenemezse söyler', async () => {
        vi.mocked(apiClient.getRiskQuestionnaire).mockRejectedValue(new Error('boom'))
        const { result } = await loaded()
        expect(result.current.error).toBe(QUESTIONNAIRE_LOAD_ERROR)
        expect(result.current.current).toBeNull()
    })

    it('yeniden yükleme önceki cevapları temizler', async () => {
        const { result } = await loaded()
        act(() => result.current.answer('horizon', 'over_5y'))
        await act(async () => { await result.current.load() })
        expect(result.current.answers).toEqual({})
        expect(result.current.index).toBe(0)
    })

    it('yüklenmeden önce gösterilecek soru yoktur', () => {
        const { result } = renderHook(() => useRiskQuestionnaire())
        expect(result.current.current).toBeNull()
        expect(result.current.complete).toBe(false)
    })
})

describe('ilerleme', () => {
    it('cevap verince sonraki soruya geçer', async () => {
        const { result } = await loaded()
        act(() => result.current.answer('horizon', 'over_5y'))
        expect(result.current.current?.key).toBe('goal')
        expect(result.current.answers.horizon).toBe('over_5y')
    })

    it('son soruda ileri gitmez', async () => {
        const { result } = await loaded()
        act(() => result.current.answer('horizon', 'over_5y'))
        act(() => result.current.answer('goal', 'growth'))
        expect(result.current.index).toBe(1)
    })

    it('geri dönüp cevabı değiştirebilir', async () => {
        const { result } = await loaded()
        act(() => result.current.answer('horizon', 'under_1y'))
        act(() => result.current.back())
        expect(result.current.current?.key).toBe('horizon')
        act(() => result.current.answer('horizon', 'over_5y'))
        expect(result.current.answers.horizon).toBe('over_5y')
    })

    it('ilk sorudan geriye gitmez', async () => {
        const { result } = await loaded()
        act(() => result.current.back())
        expect(result.current.index).toBe(0)
    })

    it('kaç sorunun yanıtlandığını sayar', async () => {
        const { result } = await loaded()
        expect(result.current.answeredCount).toBe(0)
        act(() => result.current.answer('horizon', 'over_5y'))
        expect(result.current.answeredCount).toBe(1)
    })
})

describe('gönderme', () => {
    it('eksik anket gönderilemez', async () => {
        /* Sunucu zaten 422 verir; düğmeyi kapalı tutmak daha dürüst çünkü
           yarıda bırakılmış bir anket hata değil, tamamlanmamış bir iş. */
        const { result } = await loaded()
        act(() => result.current.answer('horizon', 'over_5y'))
        expect(result.current.complete).toBe(false)
        let outcome: boolean | undefined
        await act(async () => { outcome = await result.current.submit() })
        expect(outcome).toBe(false)
        expect(apiClient.submitRiskAssessment).not.toHaveBeenCalled()
    })

    it('tamamlanmış anketi gönderir', async () => {
        const { result } = await loaded()
        act(() => result.current.answer('horizon', 'over_5y'))
        act(() => result.current.answer('goal', 'growth'))
        expect(result.current.complete).toBe(true)
        await act(async () => { await result.current.submit() })
        expect(apiClient.submitRiskAssessment).toHaveBeenCalledWith({
            horizon: 'over_5y',
            goal: 'growth',
        })
    })

    it('kaydedince çağıranı haberdar eder', async () => {
        const onSaved = vi.fn()
        const { result } = await loaded(onSaved)
        act(() => result.current.answer('horizon', 'over_5y'))
        act(() => result.current.answer('goal', 'growth'))
        await act(async () => { await result.current.submit() })
        expect(onSaved).toHaveBeenCalled()
    })

    it('kaydedilemezse söyler ve başarısızlığı bildirir', async () => {
        vi.mocked(apiClient.submitRiskAssessment).mockRejectedValue(new Error('boom'))
        const { result } = await loaded()
        act(() => result.current.answer('horizon', 'over_5y'))
        act(() => result.current.answer('goal', 'growth'))
        let outcome: boolean | undefined
        await act(async () => { outcome = await result.current.submit() })
        expect(outcome).toBe(false)
        expect(result.current.error).toBe(QUESTIONNAIRE_SAVE_ERROR)
    })

    it('kaydetme bittiğinde bekleme durumu kalkar', async () => {
        const { result } = await loaded()
        act(() => result.current.answer('horizon', 'over_5y'))
        act(() => result.current.answer('goal', 'growth'))
        await act(async () => { await result.current.submit() })
        await waitFor(() => expect(result.current.saving).toBe(false))
    })

    it('geri çağrı verilmemişse de çalışır', async () => {
        const { result } = await loaded()
        act(() => result.current.answer('horizon', 'over_5y'))
        act(() => result.current.answer('goal', 'growth'))
        await act(async () => {
            await expect(result.current.submit()).resolves.toBe(true)
        })
    })
})
