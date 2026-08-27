import { useEffect } from 'react'
import { useRiskQuestionnaire } from '../../hooks/useRiskQuestionnaire'

/**
 * Risk tolerans anketi — tek soru, tek ekran.
 *
 * Altı soruyu tek bir forma dizmek insanların okumadan tıklamasına yol açar,
 * ve bu cevaplar sonra kendi portföyleriyle karşılaştırılıyor. Sıralı akış
 * daha uzun sürmüyor, sadece her sorunun okunmasını sağlıyor.
 *
 * Durum makinesi `hooks/useRiskQuestionnaire` içinde: kapsama kapısı orayı
 * sayıyor, buradaki JSX'i saymıyor.
 */
interface QuestionnaireModalProps {
    open: boolean
    onClose: () => void
    /** Anket kaydedildiğinde profil yeniden çekilsin diye. */
    onSaved: () => void
}

export default function QuestionnaireModal({
    open,
    onClose,
    onSaved,
}: QuestionnaireModalProps) {
    const survey = useRiskQuestionnaire(onSaved)
    const { load } = survey

    useEffect(() => {
        if (open) void load()
    }, [open, load])

    useEffect(() => {
        if (!open) return
        const onKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape') onClose()
        }
        document.addEventListener('keydown', onKey)
        return () => document.removeEventListener('keydown', onKey)
    }, [open, onClose])

    if (!open) return null

    const progress = survey.total > 0 ? (survey.answeredCount / survey.total) * 100 : 0

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4">
            <div
                role="dialog"
                aria-modal="true"
                aria-label="Risk tolerans anketi"
                className="w-full max-w-lg rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl"
            >
                <div className="mb-4 flex items-start justify-between gap-4">
                    <div>
                        <h2 className="text-lg font-semibold text-white">
                            Risk tolerans anketi
                        </h2>
                        <p className="mt-1 text-xs leading-relaxed text-slate-400">
                            Cevaplarınız bir uygunluk kararı için değil, ölçülen portföy
                            riskinizle karşılaştırmak için kullanılır. İstediğiniz zaman
                            değiştirebilirsiniz.
                        </p>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Anketi kapat"
                        className="shrink-0 rounded p-1 text-slate-500 transition-colors hover:text-slate-200"
                    >
                        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                <div className="mb-5 h-1 w-full overflow-hidden rounded-full bg-white/10">
                    <div
                        className="h-full rounded-full bg-brandBlue transition-all"
                        style={{ width: `${progress}%` }}
                    />
                </div>

                {survey.loading && (
                    <p className="py-8 text-center text-sm text-slate-400">Anket yükleniyor…</p>
                )}

                {survey.error && (
                    <p className="mb-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
                        {survey.error}
                    </p>
                )}

                {survey.current && (
                    <div>
                        <p className="text-xs font-medium text-slate-500">
                            Soru {survey.index + 1} / {survey.total}
                        </p>
                        <h3 className="mt-2 text-base font-medium leading-relaxed text-white">
                            {survey.current.prompt}
                        </h3>
                        {survey.current.helper && (
                            <p className="mt-1 text-xs leading-relaxed text-slate-500">
                                {survey.current.helper}
                            </p>
                        )}

                        <div className="mt-4 flex flex-col gap-2">
                            {survey.current.options.map((option) => {
                                const chosen = survey.answers[survey.current!.key] === option.value
                                return (
                                    <button
                                        key={option.value}
                                        type="button"
                                        onClick={() => survey.answer(survey.current!.key, option.value)}
                                        className={`rounded-xl border px-4 py-3 text-left text-sm transition-colors ${
                                            chosen
                                                ? 'border-brandBlue bg-brandBlue/10 text-white'
                                                : 'border-white/10 text-slate-300 hover:border-white/25 hover:bg-white/5'
                                        }`}
                                    >
                                        {option.label}
                                    </button>
                                )
                            })}
                        </div>
                    </div>
                )}

                <div className="mt-6 flex items-center justify-between gap-3">
                    <button
                        type="button"
                        onClick={survey.back}
                        disabled={survey.index === 0}
                        className="rounded-lg px-3 py-2 text-sm font-medium text-slate-400 transition-colors hover:text-slate-200 disabled:opacity-40"
                    >
                        Geri
                    </button>
                    <button
                        type="button"
                        // Eksikken açık bir düğme, sunucudan 422 alıp onu
                        // kullanıcıya hata diye göstermek demek.
                        disabled={!survey.complete || survey.saving}
                        onClick={() => {
                            void survey.submit().then((ok) => {
                                if (ok) onClose()
                            })
                        }}
                        className="rounded-lg bg-brandBlue px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                        {survey.saving ? 'Kaydediliyor…' : 'Tamamla'}
                    </button>
                </div>
            </div>
        </div>
    )
}
