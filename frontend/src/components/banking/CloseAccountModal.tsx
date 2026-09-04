import { useState } from 'react'
import type { BankAccount } from '../../data/mockBankingData'

interface Props {
  isOpen: boolean
  onClose: () => void
  account: BankAccount | null
  /** Backend'e gider ve reddedilirse Türkçe gerekçesiyle fırlatır. */
  onConfirm: (accountId: string) => Promise<void>
}

/**
 * Hesap kapatma onayı.
 *
 * Bir dönem burada "bakiyeniz toplam varlıklarınızdan düşülecektir (Mock
 * gereği)" yazıyordu: kapatma yalnızca ekranda oluyordu ve para görünüşte yok
 * oluyordu. Kapatmak parayı yok etmek değil -- backend bakiyesi olan hesabı
 * reddediyor, düğme de bunu ÖNCEDEN söylüyor.
 */
export default function CloseAccountModal({ isOpen, onClose, account, onConfirm }: Props) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (!isOpen || !account) return null

  const funded = account.balance > 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
      <div className="bg-slate-900 border border-rose-500/20 rounded-2xl w-full max-w-md shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-rose-500/10 bg-rose-500/5">
          <h3 className="text-lg font-semibold text-rose-400 flex items-center gap-2">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            Hesap Kapatma Onayı
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          <p className="text-slate-300 mb-6">
            <strong className="text-white">{account.name}</strong> ({account.accountNumber}) numaralı hesabınızı kapatmak istediğinize emin misiniz?
            Bu işlem geri alınamaz.
          </p>
          
          <div className="bg-rose-500/10 rounded-xl p-4 border border-rose-500/20 mb-6">
            <div className="flex justify-between items-center">
              <span className="text-sm text-rose-200">Hesap Bakiyesi</span>
              <span className="text-lg font-bold text-white">
                {account.balance.toLocaleString('tr-TR', { style: 'currency', currency: account.currency })}
              </span>
            </div>
            {funded && (
              <p className="text-xs text-rose-300 mt-2">
                Bakiyesi olan hesap kapatılamaz. Önce bakiyeyi başka bir hesabınıza aktarın.
              </p>
            )}
          </div>

          {error && (
            <p className="mb-4 text-sm text-rose-300">{error}</p>
          )}

          <div className="flex gap-3">
            <button 
              onClick={onClose}
              className="flex-1 bg-white/5 hover:bg-white/10 text-white font-medium py-3 rounded-xl transition-colors"
            >
              İptal Et
            </button>
            <button
              disabled={funded || busy}
              onClick={async () => {
                setError(null)
                setBusy(true)
                try {
                  await onConfirm(account.id)
                  onClose()
                } catch (caught) {
                  // Backend'in gerekçesi Türkçe ve burada gösteriliyor:
                  // sessizce kapanan bir kip, kullanıcıya hesabın kapandığını
                  // söylerdi.
                  setError(caught instanceof Error ? caught.message : 'Hesap kapatılamadı.')
                } finally {
                  setBusy(false)
                }
              }}
              className="flex-1 bg-rose-500 hover:bg-rose-600 disabled:cursor-not-allowed disabled:bg-rose-500/30 disabled:text-white/50 text-white font-medium py-3 rounded-xl transition-colors shadow-lg shadow-rose-500/20"
            >
              {busy ? 'Kapatılıyor…' : 'Hesabı Kapat'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
