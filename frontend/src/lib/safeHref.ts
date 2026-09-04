/**
 * Bir bağlantının açılmasına izin verilip verilmeyeceği.
 *
 * `Markdown.tsx` bunu bedavaya alıyor: `react-markdown`'ın kendi
 * `defaultUrlTransform`'u güvenli olmayan şemaları düşürüyor, ve düzyazı
 * içindeki atıfların bugüne kadar güvenli olmasının sebebi bu. Kaynak
 * listesi ise `<a>` etiketini KENDİSİ kuruyor ve o korumayı almıyor.
 *
 * Adres üçüncü taraf metni: `rag.documents.source_url` KAP'tan ve RSS
 * beslemelerinden geliyor. `javascript:` ile başlayan bir adres, tıklanınca
 * sayfanın kendi bağlamında kod çalıştırır.
 */
export function isSafeHref(url: string | null | undefined): boolean {
    if (!url) return false
    try {
        const scheme = new URL(url, window.location.origin).protocol
        return scheme === 'http:' || scheme === 'https:'
    } catch {
        // Ayrıştırılamayan bir adres açılabilir bir adres değildir.
        return false
    }
}
