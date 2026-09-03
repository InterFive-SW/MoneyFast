import { useState, useEffect } from 'react'
import { DASHBOARD_TEMPLATES } from '../../data/templates'
import { api } from '../../api/client'
import { useUser } from '../../contexts/UserContext'

/**
 * AppearanceSettings — Görünüm ve Bölgesel Ayarlar
 *
 * MİMARİ & KALICILIK NOTLARI:
 * - Proje kuralı ("Tema değiştirme seçeneği KESİNLİKLE OLMAYACAKTIR") gereği,
 *   bu bileşen sadece desteklenen bölge/format/dil ayarlarını içerir.
 * - Tema kalıcı olarak "Premium Dark Mode" ile kilitlenmiştir.
 * - Tüm tercihler backend'deki `user_preferences` JSONB kolonunda saklanır.
 *   Yeni bir tercih eklemek migration gerektirmez; JSON anahtarı eklenir.
 * - `handleSave` gerçek `api.updateProfile({ user_preferences: ... })` çağrısı
 *   yapar; mock setTimeout DEĞİLDİR.
 */
export default function AppearanceSettings() {
  const { profile, updateUserPreferences } = useUser()

  // Backend'den gelen tercihlerle başlat, fallback olarak varsayılanları kullan
  const [currency, setCurrency] = useState(profile?.userPreferences?.currency ?? 'TRY')
  const [language, setLanguage] = useState(profile?.userPreferences?.language ?? 'tr')
  const [defaultTemplate, setDefaultTemplate] = useState(profile?.userPreferences?.default_template ?? 'balanced')
  
  const [isLoading, setIsLoading] = useState(false)
  const [status, setStatus] = useState<{ type: 'success' | 'error', message: string } | null>(null)

  // Context'ten gelen veri güncellendiğinde yerel state'leri senkronize et
  useEffect(() => {
    if (profile?.userPreferences) {
      setCurrency(profile.userPreferences.currency ?? 'TRY')
      setLanguage(profile.userPreferences.language ?? 'tr')
      setDefaultTemplate(profile.userPreferences.default_template ?? 'balanced')
    }
  }, [profile])

  // isDirty hesaplama — yalnızca değişiklik varsa "Kaydet" aktif olur
  const isDirty = 
    currency !== (profile?.userPreferences?.currency ?? 'TRY') ||
    language !== (profile?.userPreferences?.language ?? 'tr') ||
    defaultTemplate !== (profile?.userPreferences?.default_template ?? 'balanced')

  const handleSave = async () => {
    setIsLoading(true)
    setStatus(null)
    try {
      // Gerçek API çağrısı: backend'deki user_preferences JSONB kolonuna yazar.
      // merge semantiği backend tarafından uygulanır — yalnızca gönderilen
      // anahtarlar güncellenir, diğerleri korunur.
      const updatedPrefs = {
        currency, 
        language, 
        default_template: defaultTemplate 
      };
      
      await api.updateProfile({ user_preferences: updatedPrefs })
      
      // KRİTİK: API isteği başarılı döndükten SONRA global state güncellenir.
      // Böylece `Dashboard.tsx` gibi diğer bileşenler (sayfalar) bu yeni state'i
      // anında okuyarak arayüzü güncelleyebilir (re-render).
      // Ekstra bir network request (`refetch`) atmamak için Context API içindeki 
      // spesifik lokal state mutasyon fonksiyonu çağırılır.
      updateUserPreferences(updatedPrefs)
      
      setStatus({ type: 'success', message: 'Görünüm ayarlarınız başarıyla kaydedildi.' })
      setTimeout(() => setStatus(null), 3000)
    } catch (err: any) {
      setStatus({ type: 'error', message: err.message || 'Ayarlar kaydedilirken hata oluştu.' })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="space-y-10">
      <div>
        <h3 className="text-lg font-semibold text-white mb-2">Görünüm ve Format</h3>
        <p className="text-sm text-slate-400">Platformun dili, varsayılan para birimi ve giriş ekranı şablonu gibi deneyim ayarlarını yönetin.</p>
      </div>

      {status && (
        <div className={`mb-6 p-4 rounded-xl border text-sm font-medium flex items-start gap-3 max-w-2xl ${
          status.type === 'success' 
            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' 
            : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
        }`}>
          <span>{status.type === 'success' ? '✓' : '⚠'}</span>
          <p>{status.message}</p>
        </div>
      )}

      {/* ── Uygulama Teması (KİLİTLİ) ──────────────────────────────────────── */}
      <section className="max-w-2xl">
        <h4 className="text-base font-medium text-white mb-4 border-b border-white/10 pb-2">Uygulama Teması</h4>
        <div className="flex items-center justify-between p-5 rounded-xl border border-white/5 bg-slate-950/50">
          <div>
            <h5 className="text-sm font-semibold text-white">Premium Koyu Tema</h5>
            <p className="mt-1 text-xs text-slate-400">
              Göz yorgunluğunu azaltmak ve grafik okunabilirliğini artırmak için sistemimiz sadece
              kurumsal koyu tema ile hizmet vermektedir.
            </p>
          </div>
          <div className="ml-4 flex-shrink-0">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-brandBlue/10 px-3 py-1 text-xs font-semibold text-brandBlue border border-brandBlue/20">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>
              Sistem Varsayılanı
            </span>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-2xl">
        {/* ── Para Birimi ve Dil ───────────────────────────────────────────── */}
        <section className="space-y-4">
          <h4 className="text-base font-medium text-white mb-4 border-b border-white/10 pb-2">Format Ayarları</h4>
          
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">Varsayılan Para Birimi</label>
            <select 
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              className="w-full rounded-xl border border-white/20 bg-slate-950 px-4 py-2.5 text-white outline-none focus:border-brandBlue focus:ring-1 focus:ring-brandBlue transition-all appearance-none cursor-pointer"
            >
              <option value="TRY">Türk Lirası (₺)</option>
              <option value="USD">Amerikan Doları ($)</option>
              <option value="EUR">Euro (€)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">Uygulama Dili</label>
            <select 
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="w-full rounded-xl border border-white/20 bg-slate-950 px-4 py-2.5 text-white outline-none focus:border-brandBlue focus:ring-1 focus:ring-brandBlue transition-all appearance-none cursor-pointer"
            >
              <option value="tr">Türkçe (TR)</option>
              <option value="en">English (US)</option>
            </select>
          </div>
        </section>

        {/* ── Dashboard Şablonu ────────────────────────────────────────────── */}
        <section className="space-y-4">
          <h4 className="text-base font-medium text-white mb-4 border-b border-white/10 pb-2">Başlangıç Görünümü</h4>
          
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">Dashboard Şablonu</label>
            <div className="space-y-2">
              {DASHBOARD_TEMPLATES.map(template => (
                <label 
                  key={template.id}
                  className={`flex cursor-pointer items-start gap-3 p-3 rounded-xl border transition-all ${
                    defaultTemplate === template.id 
                      ? 'border-brandBlue bg-brandBlue/10' 
                      : 'border-white/10 bg-slate-950/30 hover:bg-white/5 hover:border-white/20'
                  }`}
                >
                  <input 
                    type="radio" 
                    name="dashboardTemplate" 
                    value={template.id}
                    checked={defaultTemplate === template.id}
                    onChange={() => setDefaultTemplate(template.id)}
                    className="mt-1 h-4 w-4 shrink-0 cursor-pointer accent-brandBlue"
                  />
                  <div>
                    <div className="text-sm font-semibold text-white flex items-center gap-2">
                      <span>{template.icon}</span>
                      {template.name}
                    </div>
                    <div className="text-[10px] text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                      {template.description}
                    </div>
                  </div>
                </label>
              ))}
            </div>
          </div>
        </section>
      </div>

      <div className="pt-8 border-t border-white/10 flex justify-end max-w-2xl">
        <button 
          onClick={handleSave}
          disabled={isLoading || !isDirty}
          className="rounded-xl bg-brandBlue px-6 py-2.5 text-sm font-semibold text-white shadow-sm shadow-brandBlue/30 transition-all hover:bg-brandBlue/90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? 'Kaydediliyor...' : 'Tercihleri Kaydet'}
        </button>
      </div>
    </div>
  )
}
