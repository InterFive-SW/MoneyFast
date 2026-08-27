import { useState, FormEvent } from 'react'
import { useUser } from '../contexts/UserContext'
import { api } from '../api/client'

export default function Settings() {
  const { profile, refetch } = useUser()
  const [activeTab, setActiveTab] = useState<'profile' | 'security' | 'notifications'>('profile')
  
  // Profile state
  const [email, setEmail] = useState(profile?.email || '')
  const [phone, setPhone] = useState(profile?.phoneNumber || '')
  
  // Security state
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  
  // Notifications state
  const [wantsEmail, setWantsEmail] = useState(profile?.wantsEmailNotifications ?? true)
  
  // Status messages
  const [status, setStatus] = useState<{ type: 'success' | 'error', message: string } | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const handleProfileSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setStatus(null)
    
    try {
      await api.put('/api/auth/me', {
        email,
        phone_number: phone || undefined,
        wants_email_notifications: wantsEmail
      })
      await refetch()
      setStatus({ type: 'success', message: 'Profil bilgileriniz başarıyla güncellendi.' })
    } catch (err: any) {
      setStatus({ type: 'error', message: err.response?.data?.detail || 'Bir hata oluştu.' })
    } finally {
      setIsLoading(false)
    }
  }

  const handlePasswordSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setStatus(null)
    
    try {
      await api.post('/api/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword
      })
      setStatus({ type: 'success', message: 'Şifreniz başarıyla değiştirildi.' })
      setCurrentPassword('')
      setNewPassword('')
    } catch (err: any) {
      setStatus({ type: 'error', message: err.response?.data?.detail || 'Şifre değiştirilirken hata oluştu.' })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="p-6 sm:p-8 min-h-screen">
      <div className="mb-8">
        <h2 className="text-2xl font-bold tracking-tight text-white">Ayarlar</h2>
        <p className="mt-1 text-sm text-slate-400">
          Hesap bilgilerinizi, güvenlik tercihlerinizi ve bildirimlerinizi yönetin.
        </p>
      </div>

      <div className="flex flex-col lg:flex-row gap-8">
        {/* Sol Menü - Tabs */}
        <div className="w-full lg:w-64 flex-shrink-0">
          <div className="rounded-2xl bg-slate-900/50 p-2 backdrop-blur-xl border border-white/10 shadow-[0_4px_24px_-8px_rgba(0,0,0,0.2)]">
            <nav className="flex flex-col gap-1">
              <button
                onClick={() => setActiveTab('profile')}
                className={`text-left px-4 py-3 rounded-xl text-sm font-medium transition-all ${
                  activeTab === 'profile' 
                    ? 'bg-brandBlue text-white shadow-sm shadow-brandBlue/30' 
                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                }`}
              >
                Profil & İletişim
              </button>
              <button
                onClick={() => setActiveTab('security')}
                className={`text-left px-4 py-3 rounded-xl text-sm font-medium transition-all ${
                  activeTab === 'security' 
                    ? 'bg-brandBlue text-white shadow-sm shadow-brandBlue/30' 
                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                }`}
              >
                Güvenlik
              </button>
              <button
                onClick={() => setActiveTab('notifications')}
                className={`text-left px-4 py-3 rounded-xl text-sm font-medium transition-all ${
                  activeTab === 'notifications' 
                    ? 'bg-brandBlue text-white shadow-sm shadow-brandBlue/30' 
                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                }`}
              >
                Bildirimler
              </button>
            </nav>
          </div>
        </div>

        {/* Sağ İçerik */}
        <div className="flex-1">
          <div className="rounded-2xl bg-slate-900/50 p-6 sm:p-8 backdrop-blur-xl border border-white/10 shadow-[0_4px_24px_-8px_rgba(0,0,0,0.2)]">
            
            {status && (
              <div className={`mb-6 p-4 rounded-xl border text-sm font-medium ${
                status.type === 'success' 
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' 
                  : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
              }`}>
                {status.message}
              </div>
            )}

            {/* PROFIL TABI */}
            {activeTab === 'profile' && (
              <div>
                <h3 className="text-lg font-semibold text-white mb-6">Profil Bilgileri</h3>
                <form onSubmit={handleProfileSubmit} className="space-y-5 max-w-xl">
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">Ad</label>
                      <input 
                        type="text" 
                        value={profile?.firstName || ''} 
                        disabled 
                        className="w-full rounded-xl border border-white/10 bg-slate-950/50 px-4 py-2.5 text-slate-300 opacity-70 cursor-not-allowed"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">Soyad</label>
                      <input 
                        type="text" 
                        value={profile?.lastName || ''} 
                        disabled 
                        className="w-full rounded-xl border border-white/10 bg-slate-950/50 px-4 py-2.5 text-slate-300 opacity-70 cursor-not-allowed"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">T.C. Kimlik No</label>
                    <input 
                      type="text" 
                      value={profile?.tcNo || ''} 
                      disabled 
                      className="w-full rounded-xl border border-white/10 bg-slate-950/50 px-4 py-2.5 text-slate-300 opacity-70 cursor-not-allowed"
                    />
                    <p className="mt-1.5 text-xs text-slate-500">Kimlik bilgileri güvenlik sebebiyle değiştirilemez.</p>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">E-posta Adresi</label>
                    <input 
                      type="email" 
                      required
                      value={email}
                      onChange={e => setEmail(e.target.value)}
                      className="w-full rounded-xl border border-white/20 bg-slate-950 px-4 py-2.5 text-white placeholder-slate-500 outline-none focus:border-brandBlue focus:ring-1 focus:ring-brandBlue transition-all"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">Telefon Numarası</label>
                    <input 
                      type="tel" 
                      value={phone}
                      onChange={e => setPhone(e.target.value)}
                      placeholder="+905551234567"
                      className="w-full rounded-xl border border-white/20 bg-slate-950 px-4 py-2.5 text-white placeholder-slate-500 outline-none focus:border-brandBlue focus:ring-1 focus:ring-brandBlue transition-all"
                    />
                  </div>

                  <div className="pt-4 border-t border-white/10">
                    <button 
                      type="submit" 
                      disabled={isLoading}
                      className="rounded-xl bg-brandBlue px-6 py-2.5 text-sm font-semibold text-white shadow-sm shadow-brandBlue/30 transition hover:bg-brandBlue/80 disabled:opacity-50"
                    >
                      {isLoading ? 'Kaydediliyor...' : 'Değişiklikleri Kaydet'}
                    </button>
                  </div>
                </form>
              </div>
            )}

            {/* GÜVENLİK TABI */}
            {activeTab === 'security' && (
              <div>
                <h3 className="text-lg font-semibold text-white mb-6">Şifre Değiştir</h3>
                <form onSubmit={handlePasswordSubmit} className="space-y-5 max-w-xl">
                  
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">Mevcut Şifre</label>
                    <input 
                      type="password" 
                      required
                      value={currentPassword}
                      onChange={e => setCurrentPassword(e.target.value)}
                      className="w-full rounded-xl border border-white/20 bg-slate-950 px-4 py-2.5 text-white outline-none focus:border-brandBlue focus:ring-1 focus:ring-brandBlue transition-all"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">Yeni Şifre</label>
                    <input 
                      type="password" 
                      required
                      value={newPassword}
                      onChange={e => setNewPassword(e.target.value)}
                      className="w-full rounded-xl border border-white/20 bg-slate-950 px-4 py-2.5 text-white outline-none focus:border-brandBlue focus:ring-1 focus:ring-brandBlue transition-all"
                    />
                    <p className="mt-1.5 text-xs text-slate-500">En az 8 karakter, 1 büyük harf ve 1 rakam içermelidir.</p>
                  </div>

                  <div className="pt-4 border-t border-white/10">
                    <button 
                      type="submit" 
                      disabled={isLoading}
                      className="rounded-xl bg-brandBlue px-6 py-2.5 text-sm font-semibold text-white shadow-sm shadow-brandBlue/30 transition hover:bg-brandBlue/80 disabled:opacity-50"
                    >
                      {isLoading ? 'Güncelleniyor...' : 'Şifreyi Güncelle'}
                    </button>
                  </div>
                </form>
              </div>
            )}

            {/* BİLDİRİMLER TABI */}
            {activeTab === 'notifications' && (
              <div>
                <h3 className="text-lg font-semibold text-white mb-6">Bildirim Tercihleri</h3>
                <form onSubmit={handleProfileSubmit} className="space-y-5 max-w-xl">
                  
                  <div className="flex items-center justify-between p-4 rounded-xl border border-white/10 bg-slate-950/50">
                    <div>
                      <h4 className="text-sm font-medium text-white">E-posta Bildirimleri</h4>
                      <p className="mt-1 text-xs text-slate-400">Piyasa özetleri, işlem makbuzları ve güvenlik uyarıları hakkında e-posta alın.</p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input 
                        type="checkbox" 
                        className="sr-only peer" 
                        checked={wantsEmail}
                        onChange={(e) => setWantsEmail(e.target.checked)}
                      />
                      <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brandBlue"></div>
                    </label>
                  </div>

                  <div className="pt-4 border-t border-white/10">
                    <button 
                      type="submit" 
                      disabled={isLoading}
                      className="rounded-xl bg-brandBlue px-6 py-2.5 text-sm font-semibold text-white shadow-sm shadow-brandBlue/30 transition hover:bg-brandBlue/80 disabled:opacity-50"
                    >
                      {isLoading ? 'Kaydediliyor...' : 'Tercihleri Kaydet'}
                    </button>
                  </div>
                </form>
              </div>
            )}
            
          </div>
        </div>
      </div>
    </div>
  )
}
