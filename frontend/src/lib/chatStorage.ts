/**
 * Sohbet geçmişinin istemci tarafı — yalnızca ANONİM kullanıcı için.
 *
 * Giriş yapmış kullanıcının geçmişi sunucudadır ve buradan hiç okunmaz.
 * Bunun sebebi tercih değil gizlilik: eski `moneyfast_chat_sessions`
 * anahtarı kullanıcıya göre isimlendirilmemişti ve çıkışta silinmiyordu,
 * dolayısıyla ortak bir tarayıcıda ikinci kullanıcı birincinin sohbetlerini
 * görüyordu.
 *
 * `sub` ile isimlendirmek bunu ÇÖZMEZ, yalnızca gizler: veri hâlâ
 * tarayıcıda durur ve devtools'tan okunur. Bu yüzden giriş yapmış kullanıcı
 * için çevrimdışı önbellek de tutulmuyor — ağ hatasında kullanıcı boş bir
 * liste ve bir uyarı görür, başkasının sohbetlerini değil.
 */

import type { ChatMessage, ChatSession } from '../types/chat'
import { reviveCitations } from './researchCitations'

/** Silinir, asla okunmaz. Kimin yazdığı bilinemez. */
export const LEGACY_KEY = 'moneyfast_chat_sessions'

/** Tek bir anonim kimlik var, isimlendirme tiyatro olurdu. */
export const ANON_KEY = 'moneyfast_chat_anon_v1'

/**
 * Bandwidth hygiene, NOT policy.
 *
 * The backend re-trims authoritatively in
 * `ai_orchestrator.service.trim_history` and ITS numbers are the ones that
 * decide what the model sees. These exist so an anonymous caller does not
 * POST an entire local session on every turn. Keep them in step with the
 * backend or leave them looser — never tighter, or the client silently
 * narrows a window the server was willing to grant.
 */
const REQUEST_MAX_MESSAGES = 20
const REQUEST_MAX_CHARS = 2000

/**
 * Drop the legacy key. Called unconditionally on every boot, for every user,
 * signed in or not: we cannot tell who wrote it, so the only safe read is
 * none at all. This one line is the whole fix for the leak.
 */
export function purgeLegacyChatSessions(): void {
    localStorage.removeItem(LEGACY_KEY)
}

function reviveMessage(raw: unknown): ChatMessage {
    const message = (raw && typeof raw === 'object' ? raw : {}) as Record<
        string,
        unknown
    >
    const sender = message.sender === 'user' || message.sender === 'ai'
        ? message.sender
        : 'ai'
    const timestamp = new Date(
        typeof message.timestamp === 'string' || message.timestamp instanceof Date
            ? (message.timestamp as string | Date)
            : Date.now(),
    )

    // Citations only belong on assistant bubbles. User rows never acquire them,
    // and anything stored is revalidated — localStorage is an untrusted boundary.
    const citations =
        sender === 'ai' ? reviveCitations(message.citations) : undefined

    return {
        id: typeof message.id === 'string' ? message.id : String(message.id ?? ''),
        text: typeof message.text === 'string' ? message.text : '',
        sender,
        timestamp: Number.isNaN(timestamp.getTime()) ? new Date(0) : timestamp,
        disclosures: Array.isArray(message.disclosures)
            ? message.disclosures.filter((d): d is string => typeof d === 'string')
            : [],
        ...(citations && citations.length > 0 ? { citations } : {}),
        // Widgets are never restored from anon storage (same policy as server).
    }
}

function reviveSession(raw: any): ChatSession {
    return {
        ...raw,
        updatedAt: new Date(raw.updatedAt),
        messages: (raw.messages ?? []).map(reviveMessage),
    }
}

/**
 * Anonymous sessions, newest first. Any parse failure yields an empty list:
 * a corrupt store must not take the chat down with it, and there is nothing
 * here worth recovering by hand.
 */
export function readAnonSessions(): ChatSession[] {
    try {
        const stored = localStorage.getItem(ANON_KEY)
        if (!stored) return []
        const parsed = JSON.parse(stored)
        if (!Array.isArray(parsed)) return []
        return parsed.map(reviveSession)
    } catch {
        return []
    }
}

export function writeAnonSessions(sessions: ChatSession[]): void {
    if (sessions.length === 0) {
        localStorage.removeItem(ANON_KEY)
        return
    }
    localStorage.setItem(ANON_KEY, JSON.stringify(sessions))
}

/** Logout, session expiry, and signing in as someone else all land here. */
export function clearChatStorage(): void {
    localStorage.removeItem(LEGACY_KEY)
    localStorage.removeItem(ANON_KEY)
}

/** Messages → the wire shape, bounded. See REQUEST_MAX_* above. */
export function trimForRequest(
    messages: ChatMessage[],
): Array<{ role: 'user' | 'assistant'; content: string }> {
    return messages.slice(-REQUEST_MAX_MESSAGES).map((message) => ({
        role: message.sender === 'user' ? ('user' as const) : ('assistant' as const),
        content: message.text.slice(0, REQUEST_MAX_CHARS),
    }))
}
