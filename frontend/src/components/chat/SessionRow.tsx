import { useState } from 'react'
import type { ChatSession } from '../../types/chat'

/**
 * Geçmiş listesindeki bir satır.
 *
 * Silme artık SUNUCU tarafında yıkıcı — eskiden yalnızca yerel bir diziyi
 * süzüyordu ve satır veritabanında yaşamaya devam ediyordu. Tek ve korumasız
 * bir tıklamayla ateşlenen çöp kutusu ikonu bu yüzden satır içi onay
 * istiyor: geri alınamayan bir işlem için modal açmaya gerek yok, ama
 * kazayla tıklanabilir de olmamalı.
 */
interface SessionRowProps {
    session: ChatSession
    isActive: boolean
    onSelect: () => void
    onDelete: () => void
    onRename: (title: string) => void
}

export default function SessionRow({
    session,
    isActive,
    onSelect,
    onDelete,
    onRename,
}: SessionRowProps) {
    const [confirming, setConfirming] = useState(false)
    const [draft, setDraft] = useState<string | null>(null)

    if (draft !== null) {
        const commit = () => {
            const title = draft.trim()
            if (title && title !== session.title) onRename(title)
            setDraft(null)
        }
        return (
            <div className="p-2">
                <input
                    autoFocus
                    value={draft}
                    maxLength={120}
                    onChange={(event) => setDraft(event.target.value)}
                    onBlur={commit}
                    onKeyDown={(event) => {
                        if (event.key === 'Enter') commit()
                        if (event.key === 'Escape') setDraft(null)
                    }}
                    aria-label="Sohbet adı"
                    className="w-full rounded border border-brandBlue/50 bg-slate-800 px-2 py-1 text-sm text-white outline-none"
                />
            </div>
        )
    }

    if (confirming) {
        return (
            <div className="flex items-center justify-between gap-2 rounded-lg bg-red-500/10 p-2 text-sm">
                <span className="truncate text-slate-300">Silinsin mi?</span>
                <span className="flex shrink-0 gap-2">
                    <button
                        type="button"
                        onClick={() => { setConfirming(false); onDelete() }}
                        className="font-medium text-red-400 hover:text-red-300"
                    >
                        Sil
                    </button>
                    <button
                        type="button"
                        onClick={() => setConfirming(false)}
                        className="text-slate-400 hover:text-slate-200"
                    >
                        Vazgeç
                    </button>
                </span>
            </div>
        )
    }

    return (
        <div
            className={`group flex items-center justify-between rounded-lg p-2 transition-colors ${
                isActive ? 'bg-brandBlue/20 text-brandBlue' : 'text-slate-300 hover:bg-white/5'
            }`}
        >
            <button
                type="button"
                onClick={onSelect}
                className="flex min-w-0 flex-1 items-center gap-2 text-left"
            >
                <svg className="h-4 w-4 shrink-0 opacity-70" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
                    />
                </svg>
                <span className="truncate text-sm font-medium">{session.title}</span>
            </button>
            <span className="flex shrink-0 gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                <button
                    type="button"
                    onClick={() => setDraft(session.title)}
                    title="Yeniden adlandır"
                    aria-label="Yeniden adlandır"
                    className="p-1 text-slate-400 hover:text-slate-200"
                >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                        />
                    </svg>
                </button>
                <button
                    type="button"
                    onClick={() => setConfirming(true)}
                    title="Sohbeti sil"
                    aria-label="Sohbeti sil"
                    className="p-1 text-slate-400 hover:text-red-500"
                >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                        />
                    </svg>
                </button>
            </span>
        </div>
    )
}
