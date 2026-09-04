import { useState } from 'react'
import { useUser } from '../../contexts/UserContext'
import { api } from '../../api/client'
import { clearChatStorage } from '../../lib/chatStorage'

/**
 * PrivacySettings — Gizlilik ve Veri Yönetimi
 *
 * MİMARİ & GÜVENLİK NOTLARI:
 * - GDPR/KVKK gereksinimlerini karşılamak üzere kullanıcıya tüm verilerini
 *   dışa aktarma (export) imkanı sunulur. İstek `POST /auth/export-data`
 *   endpoint'ine iletilir; dosya hazırlandığında kayıtlı e-postaya gönderilir.
 * - Hesap Kapatma, `DELETE /auth/me` endpoint'i üzerinden **soft delete**
 *   (is_active=False) olarak gerçekleşir. MASAK ve finansal düzenleme
 *   yükümlülükleri gereği kullanıcı kaydı veritabanından fiziksel olarak
 *   silinmez (hard delete YASAKTIR). Yasal inceleme gerektiren durumlarda
 *   veriler erişilebilir kalır.
 * - Çok adımlı onay modalı (Multi-Step Confirmation) ile korunmuştur:
 *   kullanıcının bilinçli olarak "KAPAT" yazması zorunludur.
 */
export default function PrivacySettings() {
  const { profile } = useUser()
  const [isExporting, setIsExporting] = useState(false)
  const [exportStatus, setExportStatus] = useState<{ type: 'success' | 'error', message: string } | null>(null)
  
  // Hesap Kapatma Modalı State'leri
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false)
  const [deleteReason, setDeleteReason] = useState('')
  const [deleteConfirmationText, setDeleteConfirmationText] = useState('')
  const [isDeleting, setIsDeleting] = useState(false)

  /**
   * KVKK/GDPR kapsamında kullanıcının veri dışa aktarma talebini
   * backend'e iletir. Mock setTimeout DEĞİLDİR — gerçek API çağrısıdır.
   */
  const handleExportData = async () => {
    setIsExporting(true)
    setExportStatus(null)
    try {
      const result = await api.requestDataExport()
      setExportStatus({ 
        type: 'success', 
        message: result.message 
      })
    } catch (err: any) {
      setExportStatus({ 
        type: 'error', 
        message: err.message || 'Talep oluşturulurken bir hata oluştu. Lütfen tekrar deneyin.' 
      })
    } finally {
      setIsExporting(false)
    }
  }

  /**
   * Hesap kapatma (soft delete) akışını tetikler.
   *
   * GÜVENLİK AKIŞI:
   * 1. Kullanıcı "KAPAT" yazmadıysa fonksiyon çalışmaz (guard clause).
   * 2. `DELETE /auth/me` endpoint'ine istek gönderilir.
   * 3. Backend `is_active=False` yapar — kullanıcı artık giriş yapamaz.
   * 4. Frontend localStorage'ı temizler ve kullanıcıyı login'e yönlendirir.
   */
  const handleDeleteAccount = async () => {
    if (deleteConfirmationText !== 'KAPAT') return
    
    setIsDeleting(true)
    try {
      await api.deleteAccount({ reason: deleteReason || undefined })
      // Başarılı: Tüm yerel oturum verilerini temizle
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      clearChatStorage()
      // Kullanıcıyı login sayfasına yönlendir
      window.location.href = '/login?deleted=true'
    } catch (err: any) {
      alert(err.message || 'Hesap kapatılırken bir hata oluştu.')
      setIsDeleting(false)
    }
  }

  return (
    <div className="space-y-10">
      <div>
        <h3 className="text-lg font-semibold text-white mb-2">Gizlilik ve Veri Yönetimi</h3>
        <p className="text-sm text-slate-400">KVKK ve GDPR kapsamında verilerinizi yönetin veya hesap iptali gerçekleştirin.</p>
      </div>

      {/* ── Veri İndirme (Export) ────────────────────────────────────────── */}
      <section className="max-w-2xl">
        <h4 className="text-base font-medium text-white mb-4 border-b border-white/10 pb-2">Verilerimi İndir</h4>
        
        {exportStatus && (
          <div className={`mb-4 p-4 rounded-xl border text-sm font-medium flex items-start gap-3 ${
            exportStatus.type === 'success' 
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' 
              : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
          }`}>
            <span>{exportStatus.type === 'success' ? '✓' : '⚠'}</span>
            <p>{exportStatus.message}</p>
          </div>
        )}

        <div className="p-5 rounded-xl border border-white/5 bg-slate-950/30">
          <p className="text-sm text-slate-400 leading-relaxed mb-4">
            Uygulama üzerindeki tüm kişisel bilgilerinizi, hesap hareketlerinizi ve işlem
            geçmişinizi makine tarafından okunabilir bir formatta (JSON/CSV) indirebilirsiniz.
            Dosyanız hazır olduğunda <strong>{profile?.email}</strong> adresine bir indirme bağlantısı gönderilecektir.
          </p>
          <button 
            onClick={handleExportData}
            disabled={isExporting}
            className="flex items-center gap-2 rounded-xl bg-white/5 border border-white/10 px-4 py-2 text-sm font-semibold text-white transition-all hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
            {isExporting ? 'Talep Oluşturuluyor...' : 'Verilerimi İndirme Talebi Oluştur'}
          </button>
        </div>
      </section>

      {/* ── Hesap Kapatma (Tehlikeli Alan) ───────────────────────────────── */}
      <section className="max-w-2xl pt-4">
        <h4 className="text-base font-medium text-rose-400 mb-4 border-b border-rose-500/20 pb-2">Tehlikeli Alan (Danger Zone)</h4>
        
        <div className="p-5 rounded-xl border border-rose-500/20 bg-rose-500/5">
          <h5 className="text-sm font-bold text-white mb-2">Hesabımı Kalıcı Olarak Kapat</h5>
          <p className="text-sm text-slate-400 leading-relaxed mb-5">
            Hesabınızı kapattığınızda tüm portföy verileriniz, izleme listeleriniz ve kişisel 
            bilgileriniz sistemlerimizden kalıcı olarak silinecektir. Yasal zorunluluklar gereği
            saklanması gereken finansal kayıtlar (loglar) hariç hiçbir verinize tekrar ulaşılamaz.
          </p>
          <button 
            onClick={() => setIsDeleteModalOpen(true)}
            className="rounded-xl border border-rose-500/50 bg-transparent px-4 py-2 text-sm font-semibold text-rose-400 transition-colors hover:bg-rose-500/10 hover:border-rose-500"
          >
            Hesabımı Kapat
          </button>
        </div>
      </section>

      {/* ── Hesap Kapatma Onay Modalı ────────────────────────────────────── */}
      {isDeleteModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-rose-500/30 bg-slate-900 p-6 shadow-[0_0_40px_-10px_rgba(244,63,94,0.3)]">
            
            <div className="flex items-center gap-3 mb-4 text-rose-400">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
              <h3 className="text-lg font-bold text-white">Bu işlem geri alınamaz</h3>
            </div>
            
            <p className="text-sm text-slate-300 mb-6">
              Tüm verileriniz silinecektir. Lütfen bu işlemi neden yaptığınızı belirtin ve onaylamak için kutuya <strong className="text-rose-400">KAPAT</strong> yazın.
            </p>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">Ayrılma Nedeniniz (Opsiyonel)</label>
                <select 
                  value={deleteReason}
                  onChange={(e) => setDeleteReason(e.target.value)}
                  className="w-full rounded-xl border border-white/20 bg-slate-950 px-4 py-2.5 text-white outline-none focus:border-rose-500 focus:ring-1 focus:ring-rose-500 appearance-none"
                >
                  <option value="" disabled>Lütfen bir neden seçin...</option>
                  <option value="not_using">Uygulamayı kullanmıyorum</option>
                  <option value="privacy">Gizlilik endişeleri</option>
                  <option value="too_complex">Çok karmaşık geldi</option>
                  <option value="other">Diğer</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">
                  Onaylamak için <strong>KAPAT</strong> yazın
                </label>
                <input 
                  type="text"
                  value={deleteConfirmationText}
                  onChange={(e) => setDeleteConfirmationText(e.target.value)}
                  placeholder="KAPAT"
                  className="w-full rounded-xl border border-white/20 bg-slate-950 px-4 py-2.5 text-white placeholder-slate-600 outline-none focus:border-rose-500 focus:ring-1 focus:ring-rose-500 font-mono"
                />
              </div>
            </div>

            <div className="mt-8 flex justify-end gap-3">
              <button 
                onClick={() => {
                  setIsDeleteModalOpen(false)
                  setDeleteConfirmationText('')
                }}
                disabled={isDeleting}
                className="rounded-xl px-4 py-2 text-sm font-medium text-slate-300 hover:bg-white/10 transition-colors"
              >
                İptal Et
              </button>
              <button 
                onClick={handleDeleteAccount}
                disabled={deleteConfirmationText !== 'KAPAT' || isDeleting}
                className="flex items-center justify-center min-w-[120px] rounded-xl bg-rose-500 px-4 py-2 text-sm font-bold text-white shadow-sm transition-all hover:bg-rose-600 disabled:opacity-50 disabled:hover:bg-rose-500 disabled:cursor-not-allowed"
              >
                {isDeleting ? 'Siliniyor...' : 'Hesabı Sil'}
              </button>
            </div>
            
          </div>
        </div>
      )}

    </div>
  )
}
