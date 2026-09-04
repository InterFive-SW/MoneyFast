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
  profile_picture_url?: string
  created_at?: string
  notification_preferences: Record<string, Record<string, boolean>>
  transaction_limit: number
  user_preferences: Record<string, string>
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
  /** E-posta adresi */
  email:     string
  /** Telefon numarası */
  phoneNumber?: string
  /** Profil fotoğrafı URL'si */
  profilePictureUrl?: string
  /** Hesap oluşturma tarihi */
  createdAt?: string
  /** PostgreSQL JSONB kaynaklı detaylı bildirim tercihleri matrisi (Kategori -> Kanal -> Durum) */
  notificationPreferences: Record<string, Record<string, boolean>>
  /** Güvenlik Merkezi → İşlem Onay Limiti (₺). Bu eşiğin üzerindeki
   *  transferlerde ek doğrulama (SMS/2FA) istenir. */
  transactionLimit: number
  /** Görünüm & Format tercihleri (dil, para birimi, dashboard şablonu).
   *  JSONB olarak saklanır; yeni tercih eklemek şema değişikliği gerektirmez. */
  userPreferences: Record<string, string>
}

/** Context değer yapısı */
interface UserContextValue {
  /** Kullanıcı profili — yükleme tamamlanana kadar null */
  profile:   UserProfile | null
  /** Profil verisi yüklenirken true */
  isLoading: boolean
  /** 
   * Profil verisini backend üzerinden yeniden senkronize eden asenkron fonksiyon.
   * KRİTİK: Component'lerin (örn. AppearanceSettings) bu fonksiyonu await edebilmesi 
   * için void yerine Promise<void> dönmelidir. Aksi halde race-condition oluşur ve 
   * UI, global state güncellenmeden önce eski veriyi okuyabilir.
   */
  refetch:   () => Promise<void>
  /**
   * Sadece preferences kısmını local olarak güncelleyen fonksiyon.
   * API isteği atıldıktan hemen sonra çağrılarak ekstra network isteği (refetch) yapmadan
   * UI'ın anlık senkronizasyonu sağlanır.
   */
  updateUserPreferences: (prefs: Partial<Record<string, string>>) => void
}

// ─── Varsayılan (Fallback) Profil ─────────────────────────────────────────────

/** JWT decode veya /me isteği başarısız olduğunda kullanılacak profil */
const FALLBACK_PROFILE: UserProfile = {
  firstName: 'Kullanıcı',
  lastName:  '',
  fullName:  'Kullanıcı',
  tcNo:      '',
  initials:  'KL',
  email:     '',
  profilePictureUrl: '',
  createdAt: new Date().toISOString(),
  notificationPreferences: {
    security: { email: true, push: true, sms: true },
    transactions: { email: true, push: true, sms: false },
    market: { email: false, push: true, sms: false },
    reports: { email: true, push: false, sms: false },
    marketing: { email: false, push: false, sms: false },
  },
  transactionLimit: 50000,
  userPreferences: {
    currency: 'TRY',
    language: 'tr',
    default_template: 'balanced',
  }
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
  const initials  = [firstName[0], lastName[0]].filter(Boolean).join('').toUpperCase() || 'KL'

  return { 
    firstName, 
    lastName, 
    fullName, 
    tcNo, 
    initials,
    email: data.email ?? '',
    phoneNumber: data.phone_number,
    profilePictureUrl: data.profile_picture_url,
    createdAt: data.created_at,
    notificationPreferences: (data.notification_preferences && Object.keys(data.notification_preferences).length > 0) 
      ? data.notification_preferences 
      : {
          security: { email: true, push: true, sms: true },
          transactions: { email: true, push: true, sms: false },
          market: { email: false, push: true, sms: false },
          reports: { email: true, push: false, sms: false },
          marketing: { email: false, push: false, sms: false },
        },
    transactionLimit: data.transaction_limit ?? 50000,
    userPreferences: data.user_preferences ?? {
      currency: 'TRY',
      language: 'tr',
      default_template: 'balanced',
    }
  }
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

  const updateUserPreferences = useCallback((prefs: Partial<Record<string, string>>) => {
    setProfile(prev => {
      if (!prev) return prev
      
      const cleanPrefs: Record<string, string> = {}
      for (const [k, v] of Object.entries(prefs)) {
        if (v !== undefined) {
          cleanPrefs[k] = v
        }
      }
      
      return {
        ...prev,
        userPreferences: {
          ...prev.userPreferences,
          ...cleanPrefs
        }
      }
    })
  }, [])

  return (
    <UserContext.Provider value={{ profile, isLoading, refetch: fetchProfile, updateUserPreferences }}>
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
