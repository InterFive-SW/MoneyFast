import { useCallback, useState } from 'react'
import { apiClient } from '../api/client'
import type { RiskQuestion } from '../api/client'

/**
 * Risk tolerans anketinin durum makinesi.
 *
 * Bileşende değil burada, çünkü kapsama kapısı (`vitest.config.ts`)
 * `src/hooks/**`'ı sayıyor ve JSX'i saymıyor — anketin kuralları JSX'e
 * gömülürse test edilmeden geçer.
 *
 * Korunan iki kural:
 *
 * 1. **Tek soru tek ekran.** Altı soruyu bir forma dizmek, insanların
 *    okumadan tıklamasına yol açar; cevaplar da sonra kendi portföyleriyle
 *    karşılaştırılır.
 * 2. **Eksik cevapla gönderilemez.** Sunucu zaten 422 veriyor, ama bunu
 *    kullanıcıya bir hata olarak göstermek yerine düğmeyi kapalı tutmak daha
 *    dürüst: yarıda bırakılmış bir anket bir hata değil, tamamlanmamış bir iş.
 */
export const QUESTIONNAIRE_LOAD_ERROR = 'Anket yüklenemedi. Lütfen tekrar deneyin.'
export const QUESTIONNAIRE_SAVE_ERROR = 'Cevaplarınız kaydedilemedi. Lütfen tekrar deneyin.'

export function useRiskQuestionnaire(onSaved?: () => void) {
    const [questions, setQuestions] = useState<RiskQuestion[]>([])
    const [answers, setAnswers] = useState<Record<string, string>>({})
    const [index, setIndex] = useState(0)
    const [loading, setLoading] = useState(false)
    const [saving, setSaving] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const load = useCallback(async () => {
        setLoading(true)
        setError(null)
        try {
            const payload = await apiClient.getRiskQuestionnaire()
            // Şekli bozuk bir yanıt anketi açamaz ama sayfayı da çökertmemeli:
            // `questions` eksik gelirse `questions.length` okuması patlıyordu.
            setQuestions(Array.isArray(payload?.questions) ? payload.questions : [])
            setAnswers({})
            setIndex(0)
        } catch {
            setError(QUESTIONNAIRE_LOAD_ERROR)
        } finally {
            setLoading(false)
        }
    }, [])

    /** Bir soruyu yanıtlar ve varsa sonrakine geçer. */
    const answer = useCallback(
        (key: string, value: string) => {
            setAnswers((previous) => ({ ...previous, [key]: value }))
            setIndex((current) => Math.min(current + 1, questions.length - 1))
        },
        [questions.length],
    )

    const back = useCallback(() => setIndex((current) => Math.max(current - 1, 0)), [])

    const complete =
        questions.length > 0 && questions.every((question) => question.key in answers)

    const submit = useCallback(async () => {
        // Eksikken göndermeye çalışmak, sunucudan bir 422 alıp onu kullanıcıya
        // hata olarak göstermek demek. Tamamlanmamış bir anket hata değil.
        if (!complete) return false
        setSaving(true)
        setError(null)
        try {
            await apiClient.submitRiskAssessment(answers)
            onSaved?.()
            return true
        } catch {
            setError(QUESTIONNAIRE_SAVE_ERROR)
            return false
        } finally {
            setSaving(false)
        }
    }, [answers, complete, onSaved])

    return {
        questions,
        answers,
        /** Şu an gösterilen soru; anket yüklenmediyse `null`. */
        current: questions[index] ?? null,
        index,
        total: questions.length,
        answeredCount: Object.keys(answers).length,
        complete,
        loading,
        saving,
        error,
        load,
        answer,
        back,
        submit,
    }
}
