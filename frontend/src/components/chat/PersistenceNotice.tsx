/**
 * Bir turun kaydedilmediğini söyleyen bant.
 *
 * Sunucu-otoriter geçmişte "kaydedilmedi", "asistan bunu hatırlamayacak"
 * demek. Bunu sessizce geçmek, kullanıcının ekranda gördüğü bir turu modelin
 * bir sonraki soruda bilmemesini açıklanamaz bir davranışa çevirir.
 *
 * Metni buradan gelmiyor: sebebi ayırt eden `useChatSessions` ve iki durum
 * için iki ayrı cümle var (oturum düşmesi / yazma hatası).
 */
interface PersistenceNoticeProps {
    message: string | null
    onDismiss: () => void
}

export default function PersistenceNotice({ message, onDismiss }: PersistenceNoticeProps) {
    if (!message) return null

    return (
        <div
            role="status"
            className="mx-4 mb-2 flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-200"
        >
            <svg className="mt-0.5 h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01M5.07 19h13.86a2 2 0 001.74-3L13.74 4a2 2 0 00-3.48 0L3.33 16a2 2 0 001.74 3z"
                />
            </svg>
            <p className="flex-1 leading-relaxed">{message}</p>
            <button
                type="button"
                onClick={onDismiss}
                aria-label="Uyarıyı kapat"
                className="shrink-0 rounded p-0.5 text-amber-300/70 transition-colors hover:text-amber-100"
            >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
            </button>
        </div>
    )
}
