import { useCallback, useEffect, useState } from 'react'
import { apiClient } from '../api/client'
import type { ChatDocument } from '../api/client'

/**
 * Sohbete yüklenen belgeler: listele, yükle, sil.
 *
 * Mantık burada, bileşende değil: kapsama kapısı (`vitest.config.ts`)
 * `src/hooks/**` altını sayıyor, JSX'i saymıyor.
 */

export const UPLOAD_ERROR = 'Belge yüklenemedi.'
export const DELETE_ERROR = 'Belge silinemedi.'
export const LOAD_ERROR = 'Belgeler yüklenemedi.'

/** Kabul edilen uzantılar sunucudan gelene kadarki geçici liste.
 *
 *  Yalnızca dosya seçicinin ilk açılışı için: doğru liste sunucudan geliyor
 *  ve bu ikisinin ayrışması, seçilebilen ama reddedilen bir dosya demek. */
const FALLBACK_ACCEPTED = ['.pdf', '.xlsx', '.xls', '.csv', '.pptx', '.txt']

export interface ChatDocumentsState {
    documents: ChatDocument[]
    accepted: string[]
    maxBytes: number
    /** Yükleme sürerken doğru; aynı anda ikinci bir dosya seçilmesin diye. */
    uploading: boolean
    error: string | null
    upload: (file: File, threadId?: string) => Promise<boolean>
    remove: (id: string) => Promise<void>
    reload: () => Promise<void>
    dismissError: () => void
}

export function useChatDocuments(): ChatDocumentsState {
    const [documents, setDocuments] = useState<ChatDocument[]>([])
    const [accepted, setAccepted] = useState<string[]>(FALLBACK_ACCEPTED)
    const [maxBytes, setMaxBytes] = useState(0)
    const [uploading, setUploading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const reload = useCallback(async () => {
        try {
            const body = await apiClient.getChatDocuments()
            setDocuments(body.documents)
            if (body.accepted?.length) setAccepted(body.accepted)
            setMaxBytes(body.max_bytes)
        } catch {
            setError(LOAD_ERROR)
        }
    }, [])

    useEffect(() => { void reload() }, [reload])

    const upload = useCallback(
        async (file: File, threadId?: string) => {
            setUploading(true)
            setError(null)
            try {
                const created = await apiClient.uploadChatDocument(file, threadId)
                // Başa ekleniyor: liste yeniden eskiye ve yeni yüklenen
                // dosyanın görünmesi için listeyi yeniden çekmek gerekmiyor.
                setDocuments((prev) => [created, ...prev])
                return true
            } catch (e) {
                // Sunucunun mesajı KORUNUYOR: "bu dosya türü okunamıyor" ile
                // "dosya çok büyük" farklı şeyler ve kullanıcının yapacağı şey
                // de farklı.
                setError(e instanceof Error ? e.message : UPLOAD_ERROR)
                return false
            } finally {
                setUploading(false)
            }
        },
        [],
    )

    const remove = useCallback(async (id: string) => {
        // İyimser DEĞİL: silme başarısız olursa belge hâlâ aranabilir
        // durumdadır ve listeden düşürmek, kullanıcıya sildiğini söylemek
        // olurdu.
        try {
            await apiClient.deleteChatDocument(id)
            setDocuments((prev) => prev.filter((doc) => doc.id !== id))
        } catch (e) {
            setError(e instanceof Error ? e.message : DELETE_ERROR)
        }
    }, [])

    const dismissError = useCallback(() => setError(null), [])

    return {
        documents, accepted, maxBytes, uploading, error,
        upload, remove, reload, dismissError,
    }
}

/** Dosya boyutunu okunabilir yazar. */
export function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
