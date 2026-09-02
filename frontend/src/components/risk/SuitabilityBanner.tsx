import { useState } from 'react'
import { useSuitabilityPrompt } from '../../hooks/useSuitabilityPrompt'
import QuestionnaireModal from './QuestionnaireModal'

/**
 * Uygulamanın üstünde duran "uygunluk testini doldurun" daveti.
 *
 * SERT KAPI DEĞİL. Testi bir route guard'ın arkasına koymak, kullanıcıyı
 * kendi portföyünden ve ölçümünden mahrum bırakırdı; bu, doldurma ihtimalini
 * artırmıyor, yalnızca ürünü kullanılamaz kılıyor. Şerit ısrarlı ama
 * engelleyici değil: "Sonra" demek onu o oturum için kapatıyor.
 *
 * Durum makinesi `hooks/useSuitabilityPrompt` içinde: kapsama kapısı orayı
 * sayıyor, buradaki JSX'i saymıyor.
 */
export default function SuitabilityBanner() {
    const prompt = useSuitabilityPrompt()
    const [open, setOpen] = useState(false)

    if (!prompt.visible) return null

    return (
        <>
            <div className="border-b border-amber-400/20 bg-amber-400/5 px-4 py-2.5 sm:px-6">
                <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-2">
                    <p className="min-w-0 flex-1 text-sm text-amber-100/90">
                        <span className="font-semibold">Uygunluk testi</span>
                        {prompt.neverTaken ? (
                            <> — hangi ürün gruplarının size sunulabileceğini belirler.
                            Yaklaşık iki dakika sürüyor.</>
                        ) : (
                            <> güncellendi. Yeni sürüm, ürün grubu bazında bilgi ve
                            tecrübenizi de soruyor.</>
                        )}
                    </p>
                    <div className="flex shrink-0 items-center gap-2">
                        <button
                            type="button"
                            onClick={() => setOpen(true)}
                            className="rounded-lg bg-amber-400/90 px-3 py-1.5 text-xs font-semibold text-slate-950 transition-colors hover:bg-amber-300"
                        >
                            {prompt.neverTaken ? 'Teste başla' : 'Testi güncelle'}
                        </button>
                        <button
                            type="button"
                            onClick={prompt.dismiss}
                            className="rounded-lg px-2.5 py-1.5 text-xs text-amber-100/70 transition-colors hover:text-amber-100"
                        >
                            Sonra
                        </button>
                    </div>
                </div>
            </div>

            <QuestionnaireModal
                open={open}
                onClose={() => setOpen(false)}
                onSaved={prompt.markCompleted}
            />
        </>
    )
}
