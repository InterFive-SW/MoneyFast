import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiClient } from '../api/client'
import type { RiskProductGroup, RiskQuestion, RiskQuestionnaire } from '../api/client'

/**
 * Uygunluk testinin durum makinesi.
 *
 * Bileşende değil burada, çünkü kapsama kapısı (`vitest.config.ts`)
 * `src/hooks/**`'ı sayıyor ve JSX'i saymıyor — testin kuralları JSX'e
 * gömülürse test edilmeden geçer.
 *
 * **v1'den ne değişti.** Eski anket altı soruydu ve her soruyu kendi ekranına
 * koyuyordu. Yeni test on altı soru; aynı kurgu on altı ekran demek olurdu ve
 * onu kimse bitirmez. Sorular bunun yerine ADIMLARA bölünüyor, adım başına
 * iki-üç soru:
 *
 *     1. Müşteri profili     (yaş, eğitim)
 *     2. Yatırım tercihleri  (vade, risk-getiri)
 *     3-6. Ürün grubu başına (bilgi, sıklık, hacim)
 *
 * Bilgi bölümü tek bir 4×3 matris olarak da çizilebilirdi — analist ikisini de
 * öneriyor — ama on iki soruluk bir tablo dar ekranda okunmuyor. Grup başına
 * kart hem masaüstünde hem telefonda aynı işi görüyor.
 *
 * **Yarıda kalan iş kaybolmuyor.** Cevaplar ve bulunulan adım tarayıcıda
 * saklanıyor: on altı sorunun ortasında sekmesi kapanan biri baştan
 * başlamıyor. Gönderildiğinde temizleniyor -- bir sonraki güncellemede eski
 * cevapların önceden işaretli gelmesi, kullanıcının o an vermediği bir beyanı
 * vermiş gibi göstermek olurdu.
 */
export const QUESTIONNAIRE_LOAD_ERROR = 'Test yüklenemedi. Lütfen tekrar deneyin.'
export const QUESTIONNAIRE_SAVE_ERROR = 'Cevaplarınız kaydedilemedi. Lütfen tekrar deneyin.'

/** Yarım kalan cevapların tarayıcıdaki anahtarı. Sürüm adın içinde: yeni bir
 *  test sürümü geldiğinde eski taslak sessizce yüklenmemeli. */
export const DRAFT_KEY = 'moneyfast.suitability.draft'

/** Bir sihirbaz adımı. Bölümlerden ve ürün gruplarından düzleştiriliyor. */
export interface WizardStep {
    key: string
    title: string
    helper: string | null
    /** Ürün grubu adımlarında grubun risk etiketi; diğerlerinde null. */
    risk: string | null
    questions: RiskQuestion[]
}

interface Draft {
    version: string
    answers: Record<string, string>
    step: number
}

function readDraft(): Draft | null {
    try {
        const raw = localStorage.getItem(DRAFT_KEY)
        return raw ? (JSON.parse(raw) as Draft) : null
    } catch {
        // Bozuk ya da erişilemeyen bir taslak testi açamamaya sebep olmamalı.
        return null
    }
}

function writeDraft(draft: Draft): void {
    try {
        localStorage.setItem(DRAFT_KEY, JSON.stringify(draft))
    } catch {
        // Gizli sekmede yazma başarısız olur; test yine de doldurulabilmeli.
    }
}

function clearDraft(): void {
    try {
        localStorage.removeItem(DRAFT_KEY)
    } catch {
        // yok sayılır
    }
}

/** Bölümleri sihirbaz adımlarına düzleştirir. */
export function toSteps(payload: RiskQuestionnaire | null): WizardStep[] {
    const steps: WizardStep[] = []
    for (const section of payload?.sections ?? []) {
        if (section.questions?.length) {
            steps.push({
                key: section.key,
                title: section.title,
                helper: section.helper,
                risk: null,
                questions: section.questions,
            })
        }
        for (const group of section.groups ?? []) {
            steps.push({
                key: `${section.key}:${group.key}`,
                title: group.label,
                helper: section.helper,
                risk: group.risk,
                questions: group.questions,
            })
        }
    }
    return steps
}

export function useRiskQuestionnaire(onSaved?: () => void) {
    const [payload, setPayload] = useState<RiskQuestionnaire | null>(null)
    const [answers, setAnswers] = useState<Record<string, string>>({})
    const [step, setStep] = useState(0)
    const [loading, setLoading] = useState(false)
    const [saving, setSaving] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [result, setResult] = useState<RiskProductGroup[] | null>(null)

    const steps = useMemo(() => toSteps(payload), [payload])

    const load = useCallback(async () => {
        setLoading(true)
        setError(null)
        setResult(null)
        try {
            const fetched = await apiClient.getRiskQuestionnaire()
            setPayload(fetched)
            // Taslak yalnızca AYNI sürüm için geri yükleniyor: sorular
            // değiştiyse eski cevaplar başka bir teste verilmiş cevaplardır.
            const draft = readDraft()
            if (draft && draft.version === fetched.version) {
                setAnswers(draft.answers ?? {})
                setStep(draft.step ?? 0)
            } else {
                setAnswers({})
                setStep(0)
            }
        } catch {
            setError(QUESTIONNAIRE_LOAD_ERROR)
            setPayload(null)
        } finally {
            setLoading(false)
        }
    }, [])

    // Her değişiklikte taslağı yaz. Ayrı bir "kaydet" düğmesi, kullanıcıdan
    // ilerlemesini korumak için bir eylem istemek olurdu.
    useEffect(() => {
        if (!payload || Object.keys(answers).length === 0) return
        writeDraft({ version: payload.version, answers, step })
    }, [payload, answers, step])

    const answer = useCallback((key: string, value: string) => {
        setAnswers((previous) => ({ ...previous, [key]: value }))
    }, [])

    const current = steps[step] ?? null

    /** Bu adımın soruları tamamlandı mı — "İleri" bunu bekliyor. */
    const stepComplete =
        current !== null && current.questions.every((question) => question.key in answers)

    const next = useCallback(() => {
        setStep((value) => Math.min(value + 1, Math.max(steps.length - 1, 0)))
    }, [steps.length])

    const back = useCallback(() => setStep((value) => Math.max(value - 1, 0)), [])

    const allQuestions = useMemo(
        () => steps.flatMap((entry) => entry.questions),
        [steps],
    )

    const complete =
        allQuestions.length > 0 &&
        allQuestions.every((question) => question.key in answers)

    const submit = useCallback(async () => {
        // Eksikken göndermek, sunucudan 422 alıp onu kullanıcıya hata olarak
        // göstermek demek. Tamamlanmamış bir test hata değil.
        if (!complete) return false
        setSaving(true)
        setError(null)
        try {
            const saved = await apiClient.submitRiskAssessment(answers)
            setResult(saved.product_groups ?? [])
            clearDraft()
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
        version: payload?.version ?? null,
        steps,
        current,
        step,
        total: steps.length,
        answers,
        answeredCount: Object.keys(answers).length,
        questionCount: allQuestions.length,
        stepComplete,
        isLastStep: steps.length > 0 && step === steps.length - 1,
        complete,
        loading,
        saving,
        error,
        /** Gönderim sonrası ürün grubu sonucu; henüz gönderilmediyse null. */
        result,
        load,
        answer,
        next,
        back,
        submit,
    }
}
