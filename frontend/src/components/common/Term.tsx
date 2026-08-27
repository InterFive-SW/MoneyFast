import { useEffect, useId, useRef, useState } from 'react'
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

export default function Term({ termKey, align = 'left' }: TermProps) {
    const entry = lookupTerm(termKey)
    const [open, setOpen] = useState(false)
    const wrapperRef = useRef<HTMLSpanElement>(null)
    const panelId = useId()

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
        return () => {
            document.removeEventListener('keydown', onKey)
            document.removeEventListener('mousedown', onClickOutside)
        }
    }, [open])

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
                    className={`absolute bottom-full z-30 mb-2 w-72 rounded-xl border border-white/10 bg-slate-900 p-3 text-left shadow-2xl ${
                        align === 'right' ? 'right-0' : 'left-0'
                    }`}
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
