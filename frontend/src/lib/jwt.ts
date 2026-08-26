/**
 * JWT payload okuma — yalnızca UI kararları için.
 *
 * İmza BURADA DOĞRULANMAZ ve doğrulanamaz: imzalama anahtarı sunucuda.
 * Buradan çıkan hiçbir şey yetkilendirme kararı vermez; her istek zaten
 * token'ı sunucuya taşıyor ve reddi sunucu veriyor. Bu fonksiyonların tek
 * işi "token'ın süresi dolmuş mu, şimdi yenilemeli miyim" gibi soruları
 * bir ağ gidiş-dönüşü harcamadan yanıtlamak.
 *
 * `UserContext` ve `ProtectedRoute` bunların ayrı ayrı kopyalarını
 * tutuyordu; üç kopyanın ikisi `exp` yokluğunu farklı ele alıyordu.
 */

/** Decoded payload, or null when the token is absent or unparseable. */
export function decodeJwtPayload(token: string | null): Record<string, unknown> | null {
    if (!token) return null
    try {
        const [, payloadB64] = token.split('.')
        if (!payloadB64) return null
        // Base64Url → Base64.
        const base64 = payloadB64.replace(/-/g, '+').replace(/_/g, '/')
        return JSON.parse(atob(base64)) as Record<string, unknown>
    } catch {
        return null
    }
}

/**
 * A token with no readable `exp` counts as expired.
 *
 * The safe direction: treating it as valid means the app believes it has a
 * session it cannot prove, and the user finds out when a write fails.
 */
export function isTokenExpired(token: string | null): boolean {
    const payload = decodeJwtPayload(token)
    if (!payload || typeof payload.exp !== 'number') return true
    return payload.exp * 1000 < Date.now()
}

/**
 * True while the token is still valid but close enough to expiry that a
 * request started now could arrive after it. Refreshing early costs one call;
 * not refreshing costs the turn.
 */
export function isTokenExpiringSoon(token: string | null, withinSeconds = 60): boolean {
    const payload = decodeJwtPayload(token)
    if (!payload || typeof payload.exp !== 'number') return true
    return payload.exp * 1000 < Date.now() + withinSeconds * 1000
}

/** The `sub` claim — the user's TC number in this system. */
export function tokenSubject(token: string | null): string {
    const payload = decodeJwtPayload(token)
    return typeof payload?.sub === 'string' ? payload.sub : ''
}
