import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { lookupTerm } from '../../lib/glossary'

/**
 * Bir finansal terimin yanındaki (i) düğmesi ve açıklama kutusu.
 *
 * Neden salt hover değil: hover'ın mobilde karşılığı yok ve klavyeyle gezen
 * kullanıcı açıklamaya hiç ulaşamaz. Bu yüzden gerçek bir `<button>`:
 * tıklamayla, Enter/Space ile ve odakla açılır, Escape ile kapanır. Fareyle
 * üzerine gelmek de açar — ama tek yol o değil.
 *
 * Sözlükte olmayan bir anahtar hiçbir şey çizmez; eksik bir tanım ekranı
 * bozmamalı.
 */
interface TermProps {
    /** `lib/glossary.ts` içindeki anahtar. */
    termKey: string
    /** Kutunun hangi yöne açılacağı. Dar kolonlarda `left` taşmayı önler. */
    align?: 'left' | 'right'
}

/** Panelin yukarı açılabilmesi için tetikleyicinin üstünde gereken boşluk.
 *  Ölçüldü: en uzun sözlük girdisi (risk puanı — başlık, açıklama, örnek ve
 *  üç maddelik ölçek) bu civarda yer kaplıyor. */
const NEEDED_ABOVE = 260

export default function Term({ termKey, align = 'left' }: TermProps) {
    const entry = lookupTerm(termKey)
    const [open, setOpen] = useState(false)
    // Panel varsayılan olarak YUKARI açılıyordu ve dikey taşma için bir
    // seçenek yoktu. Sayfanın üstündeki bir tetikleyicide -- özet şeridindeki
    // gibi -- kutu başlığın arkasına giriyor ve ilk satırları kırpılıyordu.
    // Bileşen on iki yerde kullanılıyor; alttakiler sorunsuz görünüyordu, o
    // yüzden hata aralıklı sanılıyordu.
    const [placeBelow, setPlaceBelow] = useState(false)
    const wrapperRef = useRef<HTMLSpanElement>(null)
    const panelId = useId()

    const measure = useCallback(() => {
        const rect = wrapperRef.current?.getBoundingClientRect()
        if (!rect) return
        setPlaceBelow(rect.top < NEEDED_ABOVE)
    }, [])

    // Açılmadan ÖNCE ölçülüyor: boyayı bir kez yanlış yerde yapıp sonra
    // düzeltmek, kullanıcının gördüğü bir sıçrama olurdu.
    useLayoutEffect(() => {
        if (open) measure()
    }, [open, measure])

    useEffect(() => {
        if (!open) return
        const onKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape') setOpen(false)
        }
        const onClickOutside = (event: MouseEvent) => {
            if (!wrapperRef.current?.contains(event.target as Node)) setOpen(false)
        }
        document.addEventListener('keydown', onKey)
        document.addEventListener('mousedown', onClickOutside)
        // Sayfa kayarsa tetikleyicinin üstündeki boşluk değişir; açık bir
        // panel yeniden ölçülmeli.
        window.addEventListener('scroll', measure, true)
        window.addEventListener('resize', measure)
        return () => {
            document.removeEventListener('keydown', onKey)
            document.removeEventListener('mousedown', onClickOutside)
            window.removeEventListener('scroll', measure, true)
            window.removeEventListener('resize', measure)
        }
    }, [open, measure])

    if (!entry) return null

    return (
        <span
            ref={wrapperRef}
            className="relative inline-flex"
            onMouseEnter={() => setOpen(true)}
            onMouseLeave={() => setOpen(false)}
        >
            <button
                type="button"
                aria-label={`${entry.title} nedir?`}
                aria-expanded={open}
                aria-describedby={open ? panelId : undefined}
                onClick={() => setOpen((value) => !value)}
                onFocus={() => setOpen(true)}
                className="flex h-4 w-4 items-center justify-center rounded-full border border-slate-600 text-[10px] font-semibold leading-none text-slate-400 transition-colors hover:border-brandBlue hover:text-brandBlue focus:outline-none focus:ring-2 focus:ring-brandBlue/50"
            >
                i
            </button>

            {open && (
                <span
                    id={panelId}
                    role="tooltip"
                    className={`absolute z-50 max-h-[60vh] w-72 max-w-[calc(100vw-2rem)] overflow-y-auto rounded-xl border border-white/10 bg-slate-900 p-3 text-left shadow-2xl ${
                        placeBelow ? 'top-full mt-2' : 'bottom-full mb-2'
                    } ${align === 'right' ? 'right-0' : 'left-0'}`}
                >
                    <span className="block text-xs font-semibold text-white">{entry.title}</span>
                    <span className="mt-1 block text-[11px] leading-relaxed text-slate-300">
                        {entry.long}
                    </span>

                    {entry.example && (
                        <span className="mt-2 block rounded-lg bg-white/5 p-2 text-[11px] leading-relaxed text-slate-400">
                            <span className="font-medium text-slate-300">Örnek: </span>
                            {entry.example}
                        </span>
                    )}

                    {entry.anchors && entry.anchors.length > 0 && (
                        <span className="mt-2 block">
                            {/* Ölçek, eşik değil: nerede durulması gerektiğini
                                söylemek tavsiye olur ve bu ürün tavsiye vermiyor. */}
                            <span className="block text-[10px] font-medium uppercase tracking-wide text-slate-500">
                                Ölçek
                            </span>
                            <span className="mt-1 block">
                                {entry.anchors.map((anchor) => (
                                    <span
                                        key={anchor}
                                        className="mt-0.5 block text-[11px] leading-relaxed text-slate-400"
                                    >
                                        · {anchor}
                                    </span>
                                ))}
                            </span>
                        </span>
                    )}
                </span>
            )}
        </span>
    )
}
