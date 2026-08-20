/**
 * ProtectedRoute — JWT Korumalı Rota Bileşeni
 *
 * Kurumsal kimlik doğrulama katmanı olarak görev yapar. Korumalı rota
 * ağacına erişmeden önce aşağıdaki iki koşulu sırasıyla doğrular:
 *
 *  1. localStorage'da `access_token` varlığı
 *  2. Token'ın `exp` claim'i üzerinden süresi dolmamış olması
 *
 * Herhangi bir koşul sağlanmazsa, kullanıcı `/login` sayfasına anında
 * yönlendirilir ve tarayıcı geçmişi temizlenerek geri dönüş engellenir.
 * Koşullar sağlanırsa iç içe geçmiş çocuk rota bileşenleri render edilir.
 *
 * Kullanım (App.tsx):
 *   <Route element={<ProtectedRoute />}>
 *     <Route element={<DashboardLayout />}>
 *       <Route path="dashboard" element={<Dashboard />} />
 *     </Route>
 *   </Route>
 */

import { Navigate, Outlet } from 'react-router-dom'

// ─── JWT Yardımcı Fonksiyonları ───────────────────────────────────────────────

/**
 * JWT token'ının payload segmentini Base64Url formatından decode eder.
 * İmza doğrulaması kasıtlı olarak yapılmaz — bu sorumluluk backend'e aittir.
 * Frontend yalnızca UI kararları için payload verilerini okur.
 */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const segments = token.split('.')
    if (segments.length !== 3) return null

    // Base64Url → standart Base64 dönüşümü
    const base64 = segments[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(base64)) as Record<string, unknown>
  } catch {
    // Hatalı biçimli token — geçersiz kabul et
    return null
  }
}

/**
 * Token'ın `exp` (expiration) claim değerini Unix timestamp olarak okur
 * ve geçerli zamana göre süresi dolmuşsa `true` döner.
 *
 * `exp` claim eksikse veya okunabilir değilse token geçersiz kabul edilir.
 */
function isTokenExpired(token: string): boolean {
  const payload = decodeJwtPayload(token)
  if (!payload) return true

  const exp = payload['exp']
  if (typeof exp !== 'number') return true

  // `exp` saniye cinsinden; Date.now() milisaniye cinsinden
  return exp * 1000 < Date.now()
}

// ─── Erişim Kontrol Fonksiyonu ────────────────────────────────────────────────

/**
 * Oturumun geçerli olup olmadığını tek noktadan kontrol eder.
 * İleride refresh token, session ID veya fingerprint kontrolü
 * bu fonksiyon genişletilerek eklenebilir.
 */
function isSessionValid(): boolean {
  const token = localStorage.getItem('access_token')
  if (!token) return false
  return !isTokenExpired(token)
}

// ─── Bileşen ──────────────────────────────────────────────────────────────────

/**
 * Korumalı Rota Sarmalayıcısı
 *
 * Oturum geçerliyse `<Outlet />` aracılığıyla çocuk rotaları render eder.
 * Geçersizse kullanıcıyı `/login`'e yönlendirir; `replace` prop'u ile
 * tarayıcı geçmişine bu yönlendirme eklenmez ve kullanıcı "geri" düğmesiyle
 * korumalı sayfaya dönemez.
 */
export default function ProtectedRoute() {
  if (!isSessionValid()) {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}
