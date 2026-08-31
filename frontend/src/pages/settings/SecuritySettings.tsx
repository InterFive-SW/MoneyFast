import { useState, FormEvent, useMemo, useEffect } from 'react'
import { api } from '../../api/client'
import { useUser } from '../../contexts/UserContext'

/**
 * SecuritySettings — Güvenlik ve Doğrulama Ayarları Bileşeni
 *
 * MİMARİ & GÜVENLİK NOTLARI:
 * - Parola değişikliği doğrudan /api/auth/change-password uç noktasına iletilir.
 * - İşlem Onay Limiti backend'deki `transaction_limit` kolonuna kalıcı olarak kaydedilir.
 * - 2FA (TOTP/Authenticator) ve Aktif Oturum Yönetimi ciddi güvenlik mühendisliği
 *   gerektiren alanlardır (QR kodu üretme, secret saklama, yedek kod oluşturma,
 *   token blacklist, cihaz parmak izi vb.). Bu bileşenler şu an "Yakında" etiketi
 *   ile devre dışı bırakılmıştır; ileride güvenlik ekibinin onayı ile aktifleştirilecektir.
 */
export default function SecuritySettings() {
  const { profile, refetch } = useUser()

  // Parola State
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newPasswordConfirm, setNewPasswordConfirm] = useState('')
  const [isChangingPassword, setIsChangingPassword] = useState(false)
  const [passwordStatus, setPasswordStatus] = useState<{ type: 'success' | 'error', message: string } | null>(null)

  // İşlem Limiti — Backend'deki transaction_limit kolonundan başlatılır
  const [transactionLimit, setTransactionLimit] = useState(profile?.transactionLimit ?? 50000)
  const [isLimitLoading, setIsLimitLoading] = useState(false)
  const [limitStatus, setLimitStatus] = useState<{ type: 'success' | 'error', message: string } | null>(null)
  const isLimitDirty = transactionLimit !== (profile?.transactionLimit ?? 50000)

  // Context'ten gelen veri güncellendiğinde senkronize ol
  useEffect(() => {
    if (profile) {
      setTransactionLimit(profile.transactionLimit)
    }
  }, [profile])

  // Şifre Gücü Hesaplama
  const passwordStrength = useMemo(() => {
    if (!newPassword) return 0
    let score = 0
    if (newPassword.length > 7) score += 1
    if (/[A-Z]/.test(newPassword)) score += 1
    if (/[0-9]/.test(newPassword)) score += 1
    if (/[^A-Za-z0-9]/.test(newPassword)) score += 1
    return score // 0'dan 4'e kadar
  }, [newPassword])

  const strengthLabels = ['Çok Zayıf', 'Zayıf', 'Orta', 'Güçlü', 'Çok Güçlü']
  const strengthColors = ['bg-rose-500', 'bg-orange-500', 'bg-amber-400', 'bg-emerald-400', 'bg-emerald-600']

  const handlePasswordSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setPasswordStatus(null)

    if (newPassword !== newPasswordConfirm) {
      setPasswordStatus({ type: 'error', message: 'Yeni şifreler eşleşmiyor.' })
      return
    }

    if (passwordStrength < 2) {
      setPasswordStatus({ type: 'error', message: 'Lütfen daha güçlü bir şifre belirleyin.' })
      return
    }

    setIsChangingPassword(true)
    try {
      // Merkezi API istemcisi üzerinden güvenli şifre değiştirme isteği
      await api.changePassword({
        current_password: currentPassword,
        new_password: newPassword
      })
      setPasswordStatus({ type: 'success', message: 'Şifreniz başarıyla değiştirildi.' })
      setCurrentPassword('')
      setNewPassword('')
      setNewPasswordConfirm('')
    } catch (err: any) {
      setPasswordStatus({ type: 'error', message: err.response?.data?.detail || err.message || 'Şifre değiştirilirken bir hata oluştu.' })
    } finally {
      setIsChangingPassword(false)
    }
  }

  const handleLimitSave = async () => {
    setIsLimitLoading(true)
    setLimitStatus(null)
    try {
      await api.updateProfile({ transaction_limit: transactionLimit })
      await refetch()
      setLimitStatus({ type: 'success', message: 'İşlem onay limitiniz başarıyla güncellendi.' })
      setTimeout(() => setLimitStatus(null), 3000)
    } catch (err: any) {
      setLimitStatus({ type: 'error', message: err.message || 'Limit güncellenirken bir hata oluştu.' })
    } finally {
      setIsLimitLoading(false)
    }
  }

  return (
    <div className="space-y-10">
      <div>
        <h3 className="text-lg font-semibold text-white mb-2">Güvenlik Merkezi</h3>
        <p className="text-sm text-slate-400">Hesabınızı korumak için güvenlik önlemlerini yapılandırın.</p>
      </div>

      {/* Şifre Değiştirme */}
      <section>
        <h4 className="text-base font-medium text-white mb-4 border-b border-white/10 pb-2">Şifre Değiştir</h4>
        
        {passwordStatus && (
          <div className={`mb-6 p-4 rounded-xl border text-sm font-medium flex items-start gap-3 ${
            passwordStatus.type === 'success' 
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' 
              : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
          }`}>
            <span>{passwordStatus.type === 'success' ? '✓' : '⚠'}</span>
            <p>{passwordStatus.message}</p>
          </div>
        )}

        <form onSubmit={handlePasswordSubmit} className="max-w-xl space-y-4">
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

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">Yeni Şifre</label>
              <input 
                type="password" 
                required
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
                className="w-full rounded-xl border border-white/20 bg-slate-950 px-4 py-2.5 text-white outline-none focus:border-brandBlue focus:ring-1 focus:ring-brandBlue transition-all"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">Yeni Şifre (Tekrar)</label>
              <input 
                type="password" 
                required
                value={newPasswordConfirm}
                onChange={e => setNewPasswordConfirm(e.target.value)}
                className="w-full rounded-xl border border-white/20 bg-slate-950 px-4 py-2.5 text-white outline-none focus:border-brandBlue focus:ring-1 focus:ring-brandBlue transition-all"
              />
            </div>
          </div>

          {newPassword && (
            <div className="pt-2">
              <div className="flex justify-between items-center mb-1.5">
                <span className="text-xs font-medium text-slate-400">Şifre Gücü</span>
                <span className={`text-xs font-semibold ${strengthColors[passwordStrength].replace('bg-', 'text-')}`}>
                  {strengthLabels[passwordStrength]}
                </span>
              </div>
              <div className="flex gap-1 h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                {[0, 1, 2, 3].map(index => (
                  <div 
                    key={index} 
                    className={`h-full flex-1 transition-all duration-300 ${index < passwordStrength ? strengthColors[passwordStrength] : 'bg-transparent'}`}
                  />
                ))}
              </div>
            </div>
          )}

          <div className="pt-2">
            <button 
              type="submit" 
              disabled={isChangingPassword || !currentPassword || !newPassword || !newPasswordConfirm}
              className="rounded-xl bg-brandBlue px-6 py-2.5 text-sm font-semibold text-white shadow-sm shadow-brandBlue/30 transition-all hover:bg-brandBlue/90 disabled:opacity-50 disabled:hover:bg-brandBlue disabled:cursor-not-allowed"
            >
              {isChangingPassword ? 'Güncelleniyor...' : 'Şifreyi Güncelle'}
            </button>
          </div>
        </form>
      </section>

      {/* İki Faktörlü Doğrulama (2FA) — DEVRE DIŞI */}
      <section>
        <h4 className="text-base font-medium text-white mb-4 border-b border-white/10 pb-2 flex justify-between items-end">
          <span>İki Faktörlü Doğrulama (2FA)</span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/10 px-3 py-1 text-[10px] font-bold text-amber-400 border border-amber-500/20 uppercase tracking-wider">
            Yakında
          </span>
        </h4>
        <div className="flex items-center justify-between p-5 rounded-xl border border-white/5 bg-white/5 max-w-xl opacity-50 cursor-not-allowed">
          <div>
            <h5 className="text-sm font-semibold text-white">Authenticator Uygulaması (Önerilen)</h5>
            <p className="mt-1 text-xs text-slate-400 max-w-sm">
              Giriş yaparken Google Authenticator veya Authy gibi bir uygulama ile tek kullanımlık şifre (TOTP) üretin.
            </p>
          </div>
          <label className="relative inline-flex items-center ml-4 flex-shrink-0 cursor-not-allowed">
            <input 
              type="checkbox" 
              className="sr-only peer" 
              checked={false}
              disabled
            />
            <div className="w-11 h-6 bg-slate-700 rounded-full peer after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all"></div>
          </label>
        </div>
      </section>

      {/* İşlem Onay Limiti — Backend'e bağlı */}
      <section>
        <h4 className="text-base font-medium text-white mb-4 border-b border-white/10 pb-2">İşlem Onay Limiti</h4>
        
        {limitStatus && (
          <div className={`mb-4 p-4 rounded-xl border text-sm font-medium flex items-start gap-3 max-w-xl ${
            limitStatus.type === 'success' 
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' 
              : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
          }`}>
            <span>{limitStatus.type === 'success' ? '✓' : '⚠'}</span>
            <p>{limitStatus.message}</p>
          </div>
        )}

        <div className="p-5 rounded-xl border border-white/5 bg-white/5 max-w-xl">
          <label className="block text-sm font-medium text-white mb-2">Ek Doğrulama Gereken Transfer Tutarı</label>
          <p className="text-xs text-slate-400 mb-4">
            Belirlediğiniz tutarın üzerindeki para transferlerinde SMS veya 2FA kodu onayı istenecektir.
          </p>
          <div className="flex items-center gap-4">
            <input 
              type="range" 
              min="0" 
              max="250000" 
              step="5000" 
              value={transactionLimit}
              onChange={(e) => setTransactionLimit(Number(e.target.value))}
              className="w-full accent-brandBlue"
            />
            <div className="font-mono text-sm font-semibold text-brandBlue whitespace-nowrap bg-brandBlue/10 px-3 py-1.5 rounded-lg border border-brandBlue/20">
              {transactionLimit === 0 ? 'Her İşlemde' : `${transactionLimit.toLocaleString('tr-TR')} ₺`}
            </div>
          </div>

          {isLimitDirty && (
            <div className="mt-4 flex justify-end">
              <button 
                onClick={handleLimitSave}
                disabled={isLimitLoading}
                className="rounded-xl bg-brandBlue px-5 py-2 text-sm font-semibold text-white shadow-sm shadow-brandBlue/30 transition-all hover:bg-brandBlue/90 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLimitLoading ? 'Kaydediliyor...' : 'Limiti Kaydet'}
              </button>
            </div>
          )}
        </div>
      </section>

      {/* Aktif Oturumlar — DEVRE DIŞI */}
      <section>
        <h4 className="text-base font-medium text-white mb-4 border-b border-white/10 pb-2 flex justify-between items-end">
          <span>Aktif Oturumlar</span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/10 px-3 py-1 text-[10px] font-bold text-amber-400 border border-amber-500/20 uppercase tracking-wider">
            Yakında
          </span>
        </h4>
        <div className="p-5 rounded-xl border border-white/5 bg-white/5 max-w-2xl opacity-50 cursor-not-allowed">
          <p className="text-sm text-slate-400">
            Oturum yönetimi özelliği, güvenlik altyapısı tamamlandığında aktif olacaktır.
            Bu özellik ile hangi cihazlardan giriş yaptığınızı görebilir ve diğer oturumlarınızı sonlandırabilirsiniz.
          </p>
        </div>
      </section>

    </div>
  )
}
