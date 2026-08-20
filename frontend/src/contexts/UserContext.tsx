/**
 * UserContext — Oturum Açmış Kullanıcı Bilgisi React Context'i
 *
 * JWT doğrulamasından geçmiş kullanıcının profil bilgilerini uygulama
 * genelinde paylaşan merkezi Context altyapısıdır. Kullanıcı adı,
 * baş harfler (avatar) ve TC kimlik no bilgilerini tek bir noktada
 * yönetir; bileşenler prop-drilling olmaksızın bu verilere erişir.
 *
 * Kullanım:
 *   const { profile, isLoading } = useUser()
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react'
import { api } from '../api/client'

// ─── Tip Tanımlamaları ────────────────────────────────────────────────────────

/** Backend `/api/auth/me` endpoint'inden dönen kullanıcı profil yapısı */
interface MeResponse {
  first_name: string
  last_name:  string
  tc_no:      string
  email:      string
  phone_number?: string
}

/** Uygulama genelinde kullanılan normalize edilmiş kullanıcı profili */
export interface UserProfile {
  /** Kullanıcının adı (backend'den veya fallback) */
  firstName: string
  /** Kullanıcının soyadı */
  lastName:  string
  /** Ad + soyad birleşimi */
  fullName:  string
  /** T.C. Kimlik numarası (JWT sub claim'inden) */
  tcNo:      string
  /** Avatar için ad ve soyadın baş harfleri — en fazla 2 karakter */
  initials:  string
}

/** Context değer yapısı */
interface UserContextValue {
  /** Kullanıcı profili — yükleme tamamlanana kadar null */
  profile:   UserProfile | null
  /** Profil verisi yüklenirken true */
  isLoading: boolean
  /** Profil verisini yeniden çeken fonksiyon */
  refetch:   () => void
}

// ─── Varsayılan (Fallback) Profil ─────────────────────────────────────────────

/** JWT decode veya /me isteği başarısız olduğunda kullanılacak profil */
const FALLBACK_PROFILE: UserProfile = {
  firstName: 'Kullanıcı',
  lastName:  '',
  fullName:  'Kullanıcı',
  tcNo:      '',
  initials:  'KL',
}

// ─── JWT Decode Yardımcısı ────────────────────────────────────────────────────

/**
 * JWT token'ının payload segmentini doğrulamadan decode eder.
 * İmza doğrulaması sunucu tarafında yapıldığından burada yalnızca
 * UI için gerekli veriye erişim sağlanmaktadır.
 *
 * @returns Decode edilmiş payload nesnesi veya null
 */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const [, payloadB64] = token.split('.')
    if (!payloadB64) return null
    // Base64Url → Base64 dönüşümü
    const base64 = payloadB64.replace(/-/g, '+').replace(/_/g, '/')
    const json   = atob(base64)
    return JSON.parse(json) as Record<string, unknown>
  } catch {
    return null
  }
}

/**
 * JWT'nin `exp` (expiration) claim'ini kontrol eder.
 * Süresi dolmuşsa true döner.
 */
function isTokenExpired(token: string): boolean {
  const payload = decodeJwtPayload(token)
  if (!payload?.exp || typeof payload.exp !== 'number') return true
  return payload.exp * 1000 < Date.now()
}

// ─── Profil Oluşturma Yardımcısı ──────────────────────────────────────────────

/**
 * Backend yanıtını normalize ederek UI'a hazır `UserProfile` üretir.
 * Boş veya eksik alanlara şık fallback değerler atanır.
 */
function buildProfile(data: Partial<MeResponse>, tcNo: string): UserProfile {
  const firstName = (data.first_name ?? '').trim() || 'Kullanıcı'
  const lastName  = (data.last_name  ?? '').trim()
  const fullName  = [firstName, lastName].filter(Boolean).join(' ')
  // firstName yukarıda her zaman 'Kullanıcı' fallback'iyle garanti dolu olduğundan
  // initials asla boş olamaz — bu yüzden || 'KL' testle asla ulaşılamaz (defensive kod).
  /* v8 ignore next */
  const initials  = [firstName[0], lastName[0]].filter(Boolean).join('').toUpperCase() || 'KL'

  return { firstName, lastName, fullName, tcNo, initials }
}

// ─── Context Kurulumu ─────────────────────────────────────────────────────────

const UserContext = createContext<UserContextValue | null>(null)

// ─── Provider Bileşeni ────────────────────────────────────────────────────────

interface UserProviderProps {
  children: ReactNode
}

/**
 * UserProvider
 *
 * Uygulama kök bileşenine (App.tsx veya main.tsx) sarılmalıdır.
 * Mount'ta localStorage'daki token'ı okur; geçerliyse `/api/auth/me`
 * üzerinden profil bilgilerini çeker.arak profil bilgisini Context'e yazar.
 */
export function UserProvider({ children }: UserProviderProps) {
  const [profile,   setProfile]   = useState<UserProfile | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const fetchProfile = useCallback(async () => {
    setIsLoading(true)

    const token = localStorage.getItem('access_token')
    if (!token || isTokenExpired(token)) {
      // Token yoksa veya süresi dolmuşsa fallback ile devam et
      setProfile(FALLBACK_PROFILE)
      setIsLoading(false)
      return
    }

    // JWT'den tc_no'yu çıkar (sub claim)
    const payload = decodeJwtPayload(token)
    const tcNo    = typeof payload?.sub === 'string' ? payload.sub : ''

    try {
      const data = await api.get<MeResponse>('/api/auth/me')
      setProfile(buildProfile(data, tcNo))
    } catch {
      // /me isteği başarısız olursa (sunucu erişilemez vb.) fallback kullan
      setProfile(buildProfile({}, tcNo))
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchProfile()
  }, [fetchProfile])

  return (
    <UserContext.Provider value={{ profile, isLoading, refetch: fetchProfile }}>
      {children}
    </UserContext.Provider>
  )
}

// ─── Tüketici Hook ────────────────────────────────────────────────────────────

/**
 * Oturum açmış kullanıcının profil bilgisine ve yükleme durumuna
 * erişmek için kullanılan bileşen hook'u.
 *
 * @throws `UserProvider` kapsayıcısı dışında kullanılırsa hata fırlatır.
 */
export function useUser(): UserContextValue {
  const ctx = useContext(UserContext)
  if (!ctx) {
    throw new Error('useUser, UserProvider bileşeni kapsayıcısı dışında kullanılamaz.')
  }
  return ctx
}
