/**
 * Tarih ve saat — tek yer, tek saat dilimi.
 *
 * `toLocaleTimeString('tr-TR')` saat dilimi VERİLMEZSE tarayıcının kendi
 * dilimini kullanır. Uygulama UTC saatli bir kapta çalıştığında ekrandaki her
 * saat UTC yazıyordu: BIST 10:00'da açılıyor ama arayüz 07:00 diyordu.
 *
 * Kullanıcı Türkiye'de ve piyasa Türkiye'de. Diliml sabit `Europe/Istanbul`
 * -- tarayıcıya bırakmak, aynı ekranın nerede açıldığına göre farklı saat
 * göstermesi demek ve bir borsa saatinde bu bir hata.
 *
 * `lib/money.ts` ile aynı desen: yedi ayrı `formatCurrency` kopyasının yerini
 * bir tane aldı, yedi ayrı tarih biçimlendirmesinin yerini de bu alıyor.
 */

/** Uygulamanın saati. */
export const APP_TIME_ZONE = 'Europe/Istanbul'

const LOCALE = 'tr-TR'

/** `Date`'e çevrilebilen her şey, ya da null. */
function parse(value: Date | string | number | null | undefined): Date | null {
    if (value === null || value === undefined) return null
    const date = value instanceof Date ? value : new Date(value)
    return Number.isNaN(date.getTime()) ? null : date
}

/** `14:32` */
export function formatTime(value: Date | string | number | null | undefined): string {
    const date = parse(value)
    if (!date) return '—'
    return date.toLocaleTimeString(LOCALE, {
        hour: '2-digit',
        minute: '2-digit',
        timeZone: APP_TIME_ZONE,
    })
}

/** `31 Ağu 2026` */
export function formatDate(
    value: Date | string | number | null | undefined,
    options: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short', year: 'numeric' },
): string {
    const date = parse(value)
    if (!date) return '—'
    return date.toLocaleDateString(LOCALE, { ...options, timeZone: APP_TIME_ZONE })
}

/** `31 Ağustos 2026 Pazartesi` — başlıktaki uzun biçim. */
export function formatLongDate(value: Date | string | number | null | undefined): string {
    return formatDate(value, {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
        weekday: 'long',
    })
}

/** `31 Ağu 2026 14:32` */
export function formatDateTime(value: Date | string | number | null | undefined): string {
    const date = parse(value)
    if (!date) return '—'
    return `${formatDate(date)} ${formatTime(date)}`
}

/**
 * Türkiye saatiyle "şimdi"nin gün başlangıcına kalan süre, milisaniye.
 *
 * Başlıktaki tarih gece yarısı kendini tazeliyor ve o gece yarısı ANKARA'nın
 * gece yarısı olmalı: tarayıcının kendi diliminde hesaplanan bir zamanlayıcı,
 * tarihi üç saat erken ya da geç çevirirdi.
 */
export function msUntilLocalMidnight(now: Date = new Date()): number {
    // Aynı anın Istanbul duvar saati. `formatToParts` ile parça parça okumak
    // da olurdu ama her parça için ulaşılamayan bir "yoksa sıfır" dalı
    // bırakırdı -- hiçbir girdinin geçemeyeceği bir dal, hiçbir şeyin
    // doğrulamadığı bir davranış iddiasıdır.
    const local = new Date(now.toLocaleString('en-US', { timeZone: APP_TIME_ZONE }))
    const midnight = new Date(local)
    midnight.setHours(24, 0, 0, 0)
    return midnight.getTime() - local.getTime()
}
