/**
 * Uygunluk testinin durum makinesi.
 *
 * Korunan üç şey:
 *
 * 1. **On altı soru, on altı ekran değil.** Eski anket altı soruydu ve her
 *    soruyu kendi ekranına koyuyordu; aynı kurgu burada on altı ekran demek
 *    olurdu ve onu kimse bitirmez. Sorular adımlara bölünüyor.
 * 2. **Yarıda kalan iş kaybolmuyor.** Cevaplar tarayıcıda saklanıyor — ama
 *    yalnızca AYNI sürüm için: sorular değiştiyse eski cevaplar başka bir
 *    teste verilmiş cevaplardır.
 * 3. **Eksikken gönderilemez.** Sunucu 422 veriyor; onu kullanıcıya hata
 *    olarak göstermek yerine düğmeyi kapalı tutmak daha dürüst, çünkü
 *    tamamlanmamış bir test bir hata değil.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import {
    DRAFT_KEY, QUESTIONNAIRE_LOAD_ERROR, QUESTIONNAIRE_SAVE_ERROR,
    toSteps, useRiskQuestionnaire,
} from './useRiskQuestionnaire'
import { apiClient } from '../api/client'

const option = (value: string) => ({ value, label: value })

const PAYLOAD = {
    version: 'v2',
    sections: [
        {
            key: 'profile', title: 'Müşteri profili',
            helper: 'Kayda geçer; risk puanınızı etkilemez.',
            questions: [
                { key: 'age_band', prompt: 'Yaşınız', helper: null,
                  options: [option('18_30'), option('31_50')] },
                { key: 'education', prompt: 'Eğitim durumunuz', helper: null,
                  options: [option('lise'), option('bachelor')] },
            ],
            groups: [],
        },
        {
            key: 'preferences', title: 'Yatırım tercihleri', helper: null,
            questions: [
                { key: 'horizon', prompt: 'Vade', helper: null,
                  options: [option('under_1y'), option('over_5y')] },
                { key: 'risk_appetite', prompt: 'Risk', helper: null,
                  options: [option('preserve'), option('total')] },
            ],
            groups: [],
        },
        {
            key: 'knowledge', title: 'Bilgi ve tecrübe',
            helper: 'Her ürün grubu için üç soru.',
            questions: [],
            groups: [
                {
                    key: 'deposit', label: 'Mevduat, Repo', risk: 'Çok düşük risk',
                    questions: [
                        { key: 'deposit_knowledge', prompt: 'Bilgi', helper: null,
                          options: [option('none'), option('sufficient')] },
                        { key: 'deposit_frequency', prompt: 'Sıklık', helper: null,
                          options: [option('never'), option('often')] },
                        { key: 'deposit_volume', prompt: 'Hacim', helper: null,
                          options: [option('none'), option('over_500k')] },
                    ],
                },
                {
                    key: 'derivative', label: 'Türev, Varant', risk: 'Çok yüksek risk',
                    questions: [
                        { key: 'derivative_knowledge', prompt: 'Bilgi', helper: null,
                          options: [option('none'), option('sufficient')] },
                        { key: 'derivative_frequency', prompt: 'Sıklık', helper: null,
                          options: [option('never'), option('often')] },
                        { key: 'derivative_volume', prompt: 'Hacim', helper: null,
                          options: [option('none'), option('over_500k')] },
                    ],
                },
            ],
        },
    ],
}

const RESULT = {
    tolerance_level: 'Orta', investment_horizon: '3-5 yıl',
    assessed_at: '2026-09-02T10:00:00Z', questionnaire_version: 'v2', raw_score: 55,
    product_groups: [
        { key: 'deposit', label: 'Mevduat', risk: 'Çok düşük risk',
          knowledge: 'sufficient', frequency: 'often', volume: 'over_500k',
          has_experience: true, eligible: true, reason: 'Koşul aranmıyor.' },
        { key: 'derivative', label: 'Türev', risk: 'Çok yüksek risk',
          knowledge: 'none', frequency: 'never', volume: 'none',
          has_experience: false, eligible: false, reason: 'Bilgi seviyeniz yeterli değil.' },
    ],
}

/** Testin tamamını doldurur. */
async function fillEverything(result: { current: ReturnType<typeof useRiskQuestionnaire> }) {
    for (const key of [
        'age_band', 'education', 'horizon', 'risk_appetite',
        'deposit_knowledge', 'deposit_frequency', 'deposit_volume',
        'derivative_knowledge', 'derivative_frequency', 'derivative_volume',
    ]) {
        await act(async () => { result.current.answer(key, 'x') })
    }
}

beforeEach(() => {
    localStorage.clear()
    vi.spyOn(apiClient, 'getRiskQuestionnaire').mockResolvedValue(PAYLOAD as never)
    vi.spyOn(apiClient, 'submitRiskAssessment').mockResolvedValue(RESULT as never)
})
afterEach(() => vi.restoreAllMocks())

describe('toSteps', () => {
    it('bölümleri ve ürün gruplarını adımlara düzleştirir', () => {
        const steps = toSteps(PAYLOAD as never)
        expect(steps.map((s) => s.key)).toEqual([
            'profile', 'preferences', 'knowledge:deposit', 'knowledge:derivative',
        ])
    })

    it('her adımda en fazla üç soru bırakır', () => {
        // On altı soruyu tek ekrana koymak kimsenin dolduracağı bir form değil.
        for (const step of toSteps(PAYLOAD as never)) {
            expect(step.questions.length).toBeLessThanOrEqual(3)
        }
    })

    it('ürün grubu adımı risk etiketini taşır, diğerleri taşımaz', () => {
        const steps = toSteps(PAYLOAD as never)
        expect(steps[0].risk).toBeNull()
        expect(steps[2].risk).toBe('Çok düşük risk')
    })

    it('gövde gelmediyse boş liste döner, çökmez', () => {
        expect(toSteps(null)).toEqual([])
        expect(toSteps({ version: 'v2' } as never)).toEqual([])
    })

    it('grup alanı hiç gelmemiş bir bölüm çökertmez', () => {
        // Sunucu alanı düşürürse adım üretilmemeli, hata verilmemeli.
        const noGroups = { version: 'v2', sections: [
            { key: 'x', title: 'X', helper: null,
              questions: [{ key: 'q', prompt: 'S', helper: null, options: [] }] },
        ] }
        expect(toSteps(noGroups as never).map((s) => s.key)).toEqual(['x'])
    })

    it('sorusu olmayan bir bölüm adım üretmez', () => {
        const empty = { version: 'v2', sections: [
            { key: 'x', title: 'X', helper: null, questions: [], groups: [] },
        ] }
        expect(toSteps(empty as never)).toEqual([])
    })
})

describe('useRiskQuestionnaire', () => {
    it('testi yükler ve ilk adımda başlar', async () => {
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        expect(result.current.version).toBe('v2')
        expect(result.current.total).toBe(4)
        expect(result.current.current?.key).toBe('profile')
        expect(result.current.questionCount).toBe(10)
    })

    it('adımın soruları bitmeden ileri gidilemeyeceğini bildirir', async () => {
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        expect(result.current.stepComplete).toBe(false)
        await act(async () => { result.current.answer('age_band', '31_50') })
        expect(result.current.stepComplete).toBe(false)
        await act(async () => { result.current.answer('education', 'bachelor') })
        expect(result.current.stepComplete).toBe(true)
    })

    it('ileri ve geri adım arasında gezer', async () => {
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        await act(async () => { result.current.next() })
        expect(result.current.current?.key).toBe('preferences')
        await act(async () => { result.current.back() })
        expect(result.current.current?.key).toBe('profile')
    })

    it('ilk adımda geri gitmek başa takılır', async () => {
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        await act(async () => { result.current.back() })
        expect(result.current.step).toBe(0)
    })

    it('son adımı bilir ve ötesine geçmez', async () => {
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        for (let i = 0; i < 10; i += 1) {
            await act(async () => { result.current.next() })
        }
        expect(result.current.step).toBe(3)
        expect(result.current.isLastStep).toBe(true)
    })

    it('eksikken gönderilemez', async () => {
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        await act(async () => { result.current.answer('age_band', '31_50') })
        let sent = true
        await act(async () => { sent = await result.current.submit() })
        expect(sent).toBe(false)
        expect(apiClient.submitRiskAssessment).not.toHaveBeenCalled()
    })

    it('tamamlanınca gönderir ve ürün grubu sonucunu taşır', async () => {
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        await fillEverything(result)
        expect(result.current.complete).toBe(true)
        await act(async () => { await result.current.submit() })
        expect(result.current.result).toHaveLength(2)
        expect(result.current.result?.[1].eligible).toBe(false)
    })

    it('ürün grubu gelmeyen bir yanıtta boş listeye düşer', async () => {
        // v1 ile doldurulmuş bir profilde alan hiç gelmiyor. Boş liste
        // "hiçbiri uygun değil" demek değil, "sorulmadı" demek.
        const { product_groups: _omit, ...withoutGroups } = RESULT
        vi.spyOn(apiClient, 'submitRiskAssessment').mockResolvedValue(withoutGroups as never)
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        await fillEverything(result)
        await act(async () => { await result.current.submit() })
        expect(result.current.result).toEqual([])
    })

    it('gönderim sonrası çağıranı haberdar eder', async () => {
        const onSaved = vi.fn()
        const { result } = renderHook(() => useRiskQuestionnaire(onSaved))
        await act(async () => { await result.current.load() })
        await fillEverything(result)
        await act(async () => { await result.current.submit() })
        expect(onSaved).toHaveBeenCalledOnce()
    })

    it('yükleme düşerse söyler ve boş kalır', async () => {
        vi.spyOn(apiClient, 'getRiskQuestionnaire').mockRejectedValue(new Error('500'))
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        expect(result.current.error).toBe(QUESTIONNAIRE_LOAD_ERROR)
        expect(result.current.total).toBe(0)
        expect(result.current.current).toBeNull()
    })

    it('gönderim düşerse cevaplar durur', async () => {
        vi.spyOn(apiClient, 'submitRiskAssessment').mockRejectedValue(new Error('500'))
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        await fillEverything(result)
        let sent = true
        await act(async () => { sent = await result.current.submit() })
        expect(sent).toBe(false)
        expect(result.current.error).toBe(QUESTIONNAIRE_SAVE_ERROR)
        expect(result.current.answeredCount).toBe(10)
    })
})

describe('yarım kalan test', () => {
    it('cevapları ve bulunulan adımı tarayıcıya yazar', async () => {
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        await act(async () => { result.current.answer('age_band', '31_50') })
        await waitFor(() => expect(localStorage.getItem(DRAFT_KEY)).not.toBeNull())
        expect(JSON.parse(localStorage.getItem(DRAFT_KEY)!).answers.age_band).toBe('31_50')
    })

    it('aynı sürümde kaldığı yerden devam eder', async () => {
        // On altı sorunun ortasında sekmesi kapanan biri baştan başlamamalı.
        localStorage.setItem(DRAFT_KEY, JSON.stringify({
            version: 'v2', answers: { age_band: '31_50', education: 'bachelor' }, step: 1,
        }))
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        expect(result.current.step).toBe(1)
        expect(result.current.answers.age_band).toBe('31_50')
    })

    it('farklı bir sürümün taslağını yüklemez', async () => {
        // Sorular değiştiyse eski cevaplar başka bir teste verilmiş cevaplardır.
        localStorage.setItem(DRAFT_KEY, JSON.stringify({
            version: 'v1', answers: { goal: 'balanced' }, step: 2,
        }))
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        expect(result.current.answers).toEqual({})
        expect(result.current.step).toBe(0)
    })

    it('bozuk bir taslak testi açmayı engellemez', async () => {
        localStorage.setItem(DRAFT_KEY, '{bozuk')
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        expect(result.current.total).toBe(4)
        expect(result.current.error).toBeNull()
    })

    it('eksik alanlı bir taslak varsayılanlara düşer', async () => {
        localStorage.setItem(DRAFT_KEY, JSON.stringify({ version: 'v2' }))
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        expect(result.current.answers).toEqual({})
        expect(result.current.step).toBe(0)
    })

    it('gönderim sonrası taslağı siler', async () => {
        // Bir sonraki güncellemede eski cevapların işaretli gelmesi, o an
        // verilmemiş bir beyanı verilmiş gibi gösterirdi.
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        await fillEverything(result)
        await act(async () => { await result.current.submit() })
        expect(localStorage.getItem(DRAFT_KEY)).toBeNull()
    })

    it('depolama yazılamıyorsa test yine doldurulabilir', async () => {
        const setItem = vi.spyOn(Storage.prototype, 'setItem')
            .mockImplementation(() => { throw new Error('gizli sekme') })
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        await act(async () => { result.current.answer('age_band', '31_50') })
        expect(result.current.answers.age_band).toBe('31_50')
        setItem.mockRestore()
    })

    it('depolama okunamıyorsa test yine açılır', async () => {
        const getItem = vi.spyOn(Storage.prototype, 'getItem')
            .mockImplementation(() => { throw new Error('erişim yok') })
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        expect(result.current.total).toBe(4)
        getItem.mockRestore()
    })

    it('silme başarısız olsa da gönderim tamamlanır', async () => {
        const remove = vi.spyOn(Storage.prototype, 'removeItem')
            .mockImplementation(() => { throw new Error('erişim yok') })
        const { result } = renderHook(() => useRiskQuestionnaire())
        await act(async () => { await result.current.load() })
        await fillEverything(result)
        let sent = false
        await act(async () => { sent = await result.current.submit() })
        expect(sent).toBe(true)
        remove.mockRestore()
    })
})
