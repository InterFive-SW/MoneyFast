/**
 * Sohbet oturumlarının tamamı: hidrasyon, gönderme, kalıcılık uyarıları.
 *
 * Neden `ChatContext` içinde değil de burada: `vitest.config.ts` kapsama
 * kapısını bilerek `src/hooks/**`, `src/lib/**` ve `src/api/client.ts` ile
 * sınırlıyor ve kendi yorumunda blanket `src/**`'ın kapıyı anlamsız
 * kılacağını savunuyor. Mantık burada olursa %100 kuralı kapıyı
 * zayıflatmadan karşılanır; provider yalnızca bağlamı dağıtır.
 *
 * Sunucu otoriterdir. Giriş yapmış kullanıcının geçmişi
 * `/api/ai_orchestrator/conversations`'tan gelir; localStorage YALNIZCA
 * anonim kullanıcı içindir ve giriş yapmış kullanıcı için çevrimdışı
 * önbellek olarak bile kullanılmaz — `sub` ile isimlendirmek veriyi
 * tarayıcıdan silmez, yalnızca gizler.
 */

import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ConversationDetail } from '../api/client'
import {
    purgeLegacyChatSessions,
    readAnonSessions,
    trimForRequest,
    writeAnonSessions,
} from '../lib/chatStorage'
import type { ChatMessage, ChatSession, PersistenceStatus } from '../types/chat'

const NEW_SESSION_TITLE = 'Yeni Sohbet'
const TITLE_PREVIEW_CHARS = 30

/** Kaç sohbet başlığı listelenecek. Mesajlar oturum açıldığında yüklenir. */
const SESSION_PAGE_SIZE = 30

export const HISTORY_LOAD_ERROR =
    'Geçmiş sohbetler yüklenemedi. Yeni bir sohbet başlatabilirsiniz.'
export const DELETE_ERROR = 'Sohbet silinemedi.'
export const CONNECTION_ERROR =
    'Üzgünüm, şu anda sunucularıma bağlanamıyorum. Lütfen daha sonra tekrar deneyin.'

/**
 * İki ayrı metin, çünkü iki ayrı durum. İkisini "kaydedilmedi" diye
 * birleştirmek doğru olurdu ama kullanıcının yapabileceği şey farklı:
 * birinde tekrar giriş yapar, diğerinde yapabileceği bir şey yoktur.
 */
export const PERSISTENCE_NOTICE: Partial<Record<PersistenceStatus, string>> = {
    session_expired:
        'Oturumunuz sona erdi. Bu sohbet kaydedilmiyor ve geçmişinize eklenmeyecek. ' +
        'Devam etmek için tekrar giriş yapın.',
    failed:
        'Sohbet kaydedilemedi. Yanıtınız hazır, ancak bu tur geçmişinize eklenmedi — ' +
        'asistan bir sonraki soruda bu turu hatırlamayabilir.',
}

function newId(): string {
    return typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : Date.now().toString()
}

function titleFrom(text: string): string {
    return text.length > TITLE_PREVIEW_CHARS
        ? `${text.substring(0, TITLE_PREVIEW_CHARS)}...`
        : text
}

/** Sunucu satırını, mesajları henüz yüklenmemiş bir oturuma çevirir. */
function toStub(row: {
    thread_id: string
    title: string | null
    updated_at: string
}): ChatSession {
    return {
        id: row.thread_id,
        title: row.title || NEW_SESSION_TITLE,
        messages: [],
        updatedAt: new Date(row.updated_at),
        messagesLoaded: false,
        origin: 'server',
    }
}

function toMessages(detail: ConversationDetail): ChatMessage[] {
    return detail.messages.map((message) => ({
        id: message.id,
        text: message.content,
        sender: message.role === 'user' ? 'user' : 'ai',
        timestamp: new Date(message.created_at),
        disclosures: message.disclosures ?? [],
        // Widget'lar bilerek geri yüklenmiyor: eski bir portföy widget'ı geçmiş
        // bir turun fiyatlarını gösterir, eski bir işlem widget'ı ise süresi
        // dolmuş bir öneri için "Onayla" düğmesi sunar.
    }))
}

export function useChatSessions() {
    const [sessions, setSessions] = useState<ChatSession[]>([])
    const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
    const [isTyping, setIsTyping] = useState(false)
    const [currentThought, setCurrentThought] = useState<string | undefined>()
    const [justAnsweredId, setJustAnsweredId] = useState<string | null>(null)
    const [activeContext, setActiveContext] = useState<string | null>(null)
    const [notice, setNotice] = useState<string | null>(null)
    const [isAuthenticated, setIsAuthenticated] = useState(false)
    /**
     * Hidrasyon bitene kadar diske yazma.
     *
     * Bu bayrak olmadan, mount anında `sessions` henüz `[]` iken yazma
     * effect'i çalışıyor ve `writeAnonSessions([])` anahtarı siliyordu —
     * yani anonim kullanıcının kayıtlı sohbetleri, okunmadan önce her sayfa
     * açılışında yok oluyordu.
     */
    const [hydrated, setHydrated] = useState(false)

    const dismissContext = useCallback(() => setActiveContext(null), [])
    const dismissNotice = useCallback(() => setNotice(null), [])

    const activeSession = sessions.find((session) => session.id === activeSessionId)
    const messages = activeSession ? activeSession.messages : []

    const patchSession = useCallback(
        (sessionId: string, patch: (session: ChatSession) => ChatSession) => {
            setSessions((prev) =>
                prev.map((session) => (session.id === sessionId ? patch(session) : session)),
            )
        },
        [],
    )

    const openSession = useCallback(async (threadId: string) => {
        setActiveSessionId(threadId)
        setActiveContext(null)
        try {
            const detail = await api.getConversation(threadId)
            setActiveContext(detail.context_topic ?? null)
            setSessions((prev) =>
                prev.map((session) =>
                    session.id === threadId
                        ? { ...session, messages: toMessages(detail), messagesLoaded: true }
                        : session,
                ),
            )
        } catch {
            // Başlık listede kalır ve tekrar tıklanabilir. Oturumu listeden
            // düşürmek, var olan bir sohbeti yokmuş gibi göstermek olurdu.
            setNotice(HISTORY_LOAD_ERROR)
        }
    }, [])

    // ---- Hidrasyon -------------------------------------------------------
    useEffect(() => {
        let cancelled = false

        void (async () => {
            // Koşulsuz, herkes için, her açılışta. Eski anahtarı kimin yazdığı
            // bilinemez, dolayısıyla güvenli tek okuma hiç okumamaktır.
            purgeLegacyChatSessions()

            const mode = await api.ensureFreshSession()
            if (cancelled) return
            setIsAuthenticated(mode === 'authenticated')

            if (mode !== 'authenticated') {
                setSessions(readAnonSessions())
                setHydrated(true)
                return
            }

            try {
                const { items } = await api.getConversations({ limit: SESSION_PAGE_SIZE })
                if (cancelled) return
                setSessions(items.map(toStub))
                if (items.length > 0) await openSession(items[0].thread_id)
            } catch {
                if (cancelled) return
                // localStorage'a DÜŞÜLMEZ. Düşmek, ortak tarayıcıdaki
                // sızıntıyı geri getiren şeyin ta kendisi.
                setNotice(HISTORY_LOAD_ERROR)
            } finally {
                if (!cancelled) setHydrated(true)
            }
        })()

        return () => {
            cancelled = true
        }
    }, [openSession])

    // Anonim oturumlar diske yazılır; giriş yapmış kullanıcınınki asla.
    useEffect(() => {
        if (hydrated && !isAuthenticated) writeAnonSessions(sessions)
    }, [sessions, isAuthenticated, hydrated])

    // ---- Oturum yönetimi -------------------------------------------------
    const createNewSession = useCallback(() => {
        const id = newId()
        setSessions((prev) => [
            {
                id,
                title: NEW_SESSION_TITLE,
                messages: [],
                updatedAt: new Date(),
                messagesLoaded: true,
                origin: 'local',
            },
            ...prev,
        ])
        setActiveSessionId(id)
        setActiveContext(null)
    }, [])

    const loadSession = useCallback(
        (sessionId: string) => {
            const session = sessions.find((candidate) => candidate.id === sessionId)
            if (session && !session.messagesLoaded) {
                void openSession(sessionId)
                return
            }
            setActiveSessionId(sessionId)
            setActiveContext(null)
        },
        [sessions, openSession],
    )

    const deleteSession = useCallback(
        async (sessionId: string) => {
            const removed = sessions.find((session) => session.id === sessionId)
            setSessions((prev) => prev.filter((session) => session.id !== sessionId))
            if (activeSessionId === sessionId) {
                setActiveSessionId(null)
                setActiveContext(null)
            }
            // Yalnızca sunucuda karşılığı olan bir sohbet için istek atılır;
            // hiç mesaj gönderilmemiş yerel bir oturumun satırı yoktur ve
            // silmeye çalışmak 404 üretirdi.
            if (!removed || removed.origin !== 'server') return
            try {
                await api.deleteConversation(sessionId)
            } catch {
                // İyimser silmeyi geri al: kullanıcıya gitti dediğimiz bir
                // sohbetin bir sonraki açılışta geri gelmesi daha kötü.
                setSessions((prev) =>
                    [...prev, removed].sort(
                        (a, b) => b.updatedAt.getTime() - a.updatedAt.getTime(),
                    ),
                )
                setNotice(DELETE_ERROR)
            }
        },
        [sessions, activeSessionId],
    )

    const renameSession = useCallback(
        async (sessionId: string, title: string) => {
            const previous = sessions.find((session) => session.id === sessionId)
            patchSession(sessionId, (session) => ({ ...session, title }))
            if (!previous || previous.origin !== 'server') return
            try {
                await api.renameConversation(sessionId, title)
            } catch {
                patchSession(sessionId, (session) => ({ ...session, title: previous.title }))
            }
        },
        [sessions, patchSession],
    )

    // ---- Gönderme --------------------------------------------------------
    const handleSendMessage = useCallback(
        async (text: string) => {
            let sessionId = activeSessionId
            let priorTurns: ReturnType<typeof trimForRequest> = []

            const existing = sessions.find((session) => session.id === sessionId)
            if (!sessionId || !existing) {
                sessionId = newId()
                setSessions((prev) => [
                    {
                        id: sessionId as string,
                        title: titleFrom(text),
                        messages: [],
                        updatedAt: new Date(),
                        messagesLoaded: true,
                        origin: 'local',
                    },
                    ...prev,
                ])
                setActiveSessionId(sessionId)
            } else {
                priorTurns = trimForRequest(existing.messages)
            }

            const userMessage: ChatMessage = {
                id: newId(),
                text,
                sender: 'user',
                timestamp: new Date(),
            }
            patchSession(sessionId, (session) => ({
                ...session,
                title: session.messages.length === 0 ? titleFrom(text) : session.title,
                updatedAt: new Date(),
                messages: [...session.messages, userMessage],
            }))

            setIsTyping(true)
            setCurrentThought(undefined)
            setNotice(null)

            // Süresi dolmuş bir token sohbet uçlarında 401 değil 200-anonim
            // üretiyor, dolayısıyla `authedFetch`'in yenileme makinesi bu
            // yolda hiç çalışmıyor. Turdan ÖNCE tazelemek, oturumun sessizce
            // düşmesini engelleyen şey.
            const mode = await api.ensureFreshSession()
            setIsAuthenticated(mode === 'authenticated')

            const requestBody = {
                user_message: text,
                thread_id: sessionId,
                conversation_history: priorTurns,
            }

            try {
                let data: any = null
                let persistence: PersistenceStatus | null = null

                const streamed = await api.streamChat(requestBody, {
                    onStage: (label) => setCurrentThought(label),
                    onDone: (payload) => {
                        data = payload
                    },
                    onSaved: (payload) => {
                        persistence = payload.persistence as PersistenceStatus
                    },
                })
                if (!streamed || !data) {
                    data = await api.post<any>('/api/ai_orchestrator/chat', requestBody)
                    persistence = data.persistence ?? null
                }

                setCurrentThought(undefined)
                setIsTyping(false)
                setActiveContext(data.context_topic ?? null)

                const answer: ChatMessage = {
                    id: data.id || newId(),
                    text: data.final_output || data.text || 'Yanıt alınamadı.',
                    sender: 'ai',
                    timestamp: new Date(),
                    widget: data.widget,
                    disclosures: data.disclosures ?? [],
                }
                setJustAnsweredId(answer.id)
                patchSession(sessionId, (session) => ({
                    ...session,
                    updatedAt: new Date(),
                    // Sunucu satırı bu turda oluştu; artık silme ve yeniden
                    // adlandırma isteklerinin gideceği bir yer var.
                    origin: persistence === 'saved' ? 'server' : session.origin,
                    messages: [...session.messages, answer],
                }))

                if (persistence) setNotice(PERSISTENCE_NOTICE[persistence] ?? null)
            } catch {
                setCurrentThought(undefined)
                setIsTyping(false)
                patchSession(sessionId, (session) => ({
                    ...session,
                    updatedAt: new Date(),
                    messages: [
                        ...session.messages,
                        {
                            id: newId(),
                            text: CONNECTION_ERROR,
                            sender: 'ai',
                            timestamp: new Date(),
                        },
                    ],
                }))
            }
        },
        [activeSessionId, sessions, patchSession],
    )

    return {
        sessions,
        activeSessionId,
        messages,
        isTyping,
        currentThought,
        justAnsweredId,
        activeContext,
        notice,
        dismissContext,
        dismissNotice,
        handleSendMessage,
        createNewSession,
        loadSession,
        deleteSession,
        renameSession,
    }
}
