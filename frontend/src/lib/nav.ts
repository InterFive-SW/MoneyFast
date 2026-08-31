/**
 * Kenar çubuğunun ek adres eşleşmesi.
 *
 * Analiz TEK bir sayfa ama menüde iki girişi var: Portföy Analizi ve Risk
 * Analizi. NavLink `to` ile verilen tek adresi eşleştirir, dolayısıyla
 * Senaryo sekmesindeyken (`/analiz/senaryo`) Portföy Analizi sönerdi.
 * `match` bu boşluğu kapatıyor.
 */

/**
 * `pathname`, `prefix` ile başlıyor mu — SEGMENT sınırına saygı duyarak.
 *
 * Düz bir `startsWith`, `/analiz/senaryolar`'ı `/analiz/senaryo`'nun altında
 * sayardı: adres olarak alakasız iki sayfa, menüde aynı anda yanan iki öğe.
 */
export function isMatch(pathname: string, prefix: string): boolean {
    if (pathname === prefix) return true
    return pathname.startsWith(prefix.endsWith('/') ? prefix : `${prefix}/`)
}
