import { useState, useEffect } from 'react'
import { useUser } from '../../contexts/UserContext'
import { api } from '../../api/client'

/**
 * Bildirim Tercihleri Yönetimi
 *
 * MİMARİ & GÜVENLİK NOTLARI:
 * - Backend'den gelen PostgreSQL JSONB kolonuna bağlı çalışır.
 * - Kullanıcı her bir kategori ve kanal için bildirim ayarlarını bu matris
 *   üzerinden değiştirir.
 * - "Güvenlik > E-posta" zorunlu bir bildirimdir (disabled/checked bırakılır)
 *   çünkü yasal bildirimler ve kritik uyarılar her zaman iletilmek zorundadır.
 * - "Kaydet" butonu aracılığıyla tüm JSON yapısı backend'e tek seferde
 *   gönderilir, bu da transaction yükünü ve HTTP trafiğini azaltır.
 */
export default function NotificationSettings() {
  const { profile, refetch } = useUser()
  const [preferences, setPreferences] = useState<Record<string, Record<string, boolean>>>({})
  const [isLoading, setIsLoading] = useState(false)
  const [status, setStatus] = useState<{ type: 'success' | 'error', message: string } | null>(null)

  // Context'ten gelen verileri yerel state'e kopyala
  useEffect(() => {
    if (profile?.notificationPreferences) {
      setPreferences(profile.notificationPreferences)
    }
  }, [profile])

  const categories = [
    { id: 'security', label: 'Güvenlik', description: 'Şifre sıfırlama, yeni cihaz girişleri' },
    { id: 'transactions', label: 'Hesap Hareketleri', description: 'Para transferleri, işlem onayları' },
    { id: 'market', label: 'Piyasalar', description: 'Fiyat alarmları, piyasa bültenleri' },
    { id: 'reports', label: 'Raporlar', description: 'Haftalık ve aylık portföy özetleri' },
    { id: 'marketing', label: 'Pazarlama', description: 'Yeni özellikler, kampanyalar' },
  ]
  const channels = ['email', 'sms', 'push']

  const handleToggle = (categoryId: string, channelId: string) => {
    // Güvenlik e-postaları kapatılamaz
    if (categoryId === 'security' && channelId === 'email') return

    setPreferences(prev => ({
      ...prev,
      [categoryId]: {
        ...prev[categoryId],
        [channelId]: !(prev[categoryId]?.[channelId] ?? false)
      }
    }))
  }

  const handleSave = async () => {
    setIsLoading(true)
    setStatus(null)

    try {
      await api.updateProfile({ notification_preferences: preferences })
      await refetch()
      setStatus({ type: 'success', message: 'Bildirim tercihleriniz başarıyla güncellendi.' })
      setTimeout(() => setStatus(null), 3000)
    } catch (err: any) {
      setStatus({ type: 'error', message: err.response?.data?.detail || err.message || 'Tercihler güncellenirken bir hata oluştu.' })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div>
      <div className="mb-8">
        <h3 className="text-lg font-semibold text-white mb-2">Bildirim Tercihleri</h3>
        <p className="text-sm text-slate-400">Hesabınızla ilgili gelişmeleri hangi kanallardan almak istediğinizi yönetin.</p>
      </div>
      
      {/* Kullanıcı Geribildirim Uyarıları */}
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

      {/* Premium Dark Mode, Glassmorphism Table */}
      <div className="max-w-3xl overflow-hidden rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-xl">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-white/10 bg-white/5">
              <th className="p-4 text-sm font-medium text-slate-300 w-1/2">Kategori</th>
              <th className="p-4 text-sm font-medium text-center text-slate-300">E-posta</th>
              <th className="p-4 text-sm font-medium text-center text-slate-300">SMS</th>
              <th className="p-4 text-sm font-medium text-center text-slate-300">Push</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {categories.map((cat) => (
              <tr key={cat.id} className="transition-colors hover:bg-white/[0.02]">
                <td className="p-4">
                  <div className="font-medium text-white text-sm mb-0.5">{cat.label}</div>
                  <div className="text-xs text-slate-400">{cat.description}</div>
                </td>
                {channels.map((chan) => {
                  const isSmsOrPush = chan === 'sms' || chan === 'push'
                  const isChecked = isSmsOrPush ? false : (preferences[cat.id]?.[chan] ?? false)
                  const isRequired = cat.id === 'security' && chan === 'email'
                  const isDisabled = isRequired || isSmsOrPush || isLoading

                  return (
                    <td key={chan} className="p-4 text-center">
                      <label className={`relative inline-flex items-center justify-center flex-shrink-0 ${isDisabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}>
                        <input 
                          type="checkbox" 
                          className="sr-only peer" 
                          checked={isChecked || isRequired}
                          disabled={isDisabled}
                          onChange={() => handleToggle(cat.id, chan)}
                        />
                        <div className="w-9 h-5 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500"></div>
                      </label>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-8 flex justify-end max-w-3xl">
        <button
          onClick={handleSave}
          disabled={isLoading}
          className="px-6 py-2.5 rounded-xl text-sm font-medium bg-emerald-500 hover:bg-emerald-400 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {isLoading ? (
            <>
              <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <span>Kaydediliyor...</span>
            </>
          ) : (
            'Tercihleri Kaydet'
          )}
        </button>
      </div>
    </div>
  )
}
