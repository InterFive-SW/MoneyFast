import { useState } from 'react'
import { apiClient } from '../../api/client'

type TradeAction = 'Alış' | 'Satış'
type Step = 'form' | 'submitting' | 'success' | 'error'

interface TradeModalProps {
  symbol: string
  price: number
  onClose: () => void
}

/** Panelin varsayılan yatırım hesabı; backend tek demo hesabı bu numarayla tutar. */
const DEFAULT_ACCOUNT_ID = 'TR-DEMO-0001'

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('tr-TR', {
    style: 'currency',
    currency: 'TRY',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)
}

export default function TradeModal({ symbol, price, onClose }: TradeModalProps) {
  const [action, setAction] = useState<TradeAction>('Alış')
  const [quantity, setQuantity] = useState(1)
  const [limitEnabled, setLimitEnabled] = useState(false)
  const [limitPrice, setLimitPrice] = useState(price)
  const [step, setStep] = useState<Step>('form')
  const [confirmMessage, setConfirmMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')

  const effectivePrice = limitEnabled ? limitPrice : price
  const estimatedTotal = quantity * effectivePrice

  async function handleConfirm() {
    setStep('submitting')
    setErrorMessage('')
    try {
      // İki adım: önce öneri hazırlanır (hiçbir emir iletilmez), sonra
      // kullanıcının bu tıklamasıyla onaylanır. Sohbetteki akışla aynı yol.
      // Kimin adına öneri hazırlandığı sunucuda token'dan doğrulanıyor;
      // gövdedeki değerin onunla aynı olması gerekiyor, bu yüzden uydurulmuş
      // bir sabit yerine oturumdaki gerçek kimlik okunuyor.
      const me = await apiClient.getCurrentUser()

      const proposal = await apiClient.stageTransaction({
        user_id: me.id,
        transaction_type: action === 'Alış' ? 'BUY' : 'SELL',
        source_account_id: DEFAULT_ACCOUNT_ID,
        // Aynı emrin çift gönderilmesini backend bu anahtarla eler.
        idempotency_key: `ui-${symbol}-${Date.now()}`,
        instrument: { symbol },
        quantity,
        order_type: limitEnabled ? 'LIMIT' : 'MARKET',
        limit_price: limitEnabled ? limitPrice : null,
        // Sözleşmede varsayılanı olan alanlar; açıkça gönderilir ki emrin
        // geçerlilik süresi sunucu tarafında sessizce belirlenmesin.
        time_in_force: 'DAY',
        assumptions: [],
      })

      if (proposal.status !== 'PENDING_USER_CONFIRMATION') {
        // Backend'in gerekçesi kullanıcının görmesi gereken şey; yerine genel
        // bir hata yazmak reddin sebebini gizlerdi.
        setErrorMessage(
          proposal.blockers?.join(' ') || 'Bu emir doğrulanamadı, lütfen bilgileri kontrol edin.',
        )
        setStep('error')
        return
      }

      const confirmed = await apiClient.confirmProposal(proposal.proposal_id)
      setConfirmMessage(confirmed.message ?? 'Emir onaylandı.')
      setStep('success')
    } catch (error) {
      console.error('Trade order failed', error)
      setErrorMessage(
        localStorage.getItem('access_token')
          ? 'Emir iletilemedi, lütfen tekrar deneyin.'
          : 'Emir vermek için oturum açmanız gerekiyor.',
      )
      setStep('error')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-xl p-4">
      <div className="w-full max-w-sm rounded-[2.5rem] bg-slate-900/50 backdrop-blur-xl border border-white/10 p-6 shadow-2xl">
        {step === 'success' ? (
          <div className="flex flex-col items-center text-center gap-3 py-4">
            <div className="w-12 h-12 rounded-full bg-emerald-100 flex items-center justify-center">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6 text-emerald-600">
                <path d="M20 6 9 17l-5-5" />
              </svg>
            </div>
            <h3 className="font-bold text-white">Emriniz İletildi</h3>
            <p className="text-sm text-slate-400">{confirmMessage}</p>
            <p className="text-xs text-slate-400">
              (Mock akış — gerçek bir işlem gerçekleşmedi, veritabanı bağlandığında güncellenecek.)
            </p>
            <button
              onClick={onClose}
              className="mt-2 w-full rounded-xl bg-emerald-500 text-white py-2.5 text-sm font-semibold shadow-sm shadow-emerald-500/30 hover:bg-emerald-600 transition-colors"
            >
              Kapat
            </button>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">Varlık</h3>
                <p className="font-bold text-white text-lg">{symbol}</p>
              </div>
              <button onClick={onClose} className="text-slate-400 hover:text-slate-300 transition-colors">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p className="tabular-nums text-2xl font-bold text-white mb-4">{formatCurrency(price)}</p>

            <div className="flex gap-2 mb-4">
              <button
                onClick={() => setAction('Alış')}
                className={`flex-1 rounded-xl py-2.5 text-sm font-semibold transition-colors ${
                  action === 'Alış'
                    ? 'bg-emerald-500 text-white shadow-sm shadow-emerald-500/30'
                    : 'bg-slate-100 text-slate-400 hover:bg-slate-700'
                }`}
              >
                Al
              </button>
              <button
                onClick={() => setAction('Satış')}
                className={`flex-1 rounded-xl py-2.5 text-sm font-semibold transition-colors ${
                  action === 'Satış'
                    ? 'bg-rose-500 text-white shadow-sm shadow-rose-500/30'
                    : 'bg-slate-100 text-slate-400 hover:bg-slate-700'
                }`}
              >
                Sat
              </button>
            </div>

            <label className="block text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-1.5">Adet</label>
            <input
              type="number"
              min={1}
              value={quantity}
              onChange={(e) => setQuantity(Math.max(1, Number(e.target.value)))}
              className="w-full rounded-xl border border-white/10 bg-slate-800 text-white placeholder:text-slate-400 px-3 py-2.5 text-sm tabular-nums mb-4 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
            />

            <div className="flex items-center justify-between mb-4">
              <span className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">Limit Emri</span>
              <button
                onClick={() => setLimitEnabled((v) => !v)}
                className={`w-10 h-6 rounded-full transition-colors relative ${limitEnabled ? 'bg-emerald-500' : 'bg-slate-700'}`}
              >
                <span
                  className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                    limitEnabled ? 'translate-x-4' : 'translate-x-0.5'
                  }`}
                />
              </button>
            </div>

            {limitEnabled && (
              <>
                <label className="block text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-1.5">Limit Fiyat</label>
                <input
                  type="number"
                  min={0}
                  step={0.01}
                  value={limitPrice}
                  onChange={(e) => setLimitPrice(Number(e.target.value))}
                  className="w-full rounded-xl border border-white/10 bg-slate-800 text-white placeholder:text-slate-400 px-3 py-2.5 text-sm tabular-nums mb-4 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                />
              </>
            )}

            <div className="flex items-center justify-between mb-4 px-1">
              <span className="text-xs text-slate-400">Tahmini Tutar</span>
              <span className="tabular-nums text-sm font-semibold text-slate-200">{formatCurrency(estimatedTotal)}</span>
            </div>

            {step === 'error' && <p className="text-sm text-rose-500 mb-3">{errorMessage}</p>}

            <button
              onClick={handleConfirm}
              disabled={step === 'submitting'}
              className="w-full rounded-xl bg-slate-950 text-white py-2.5 text-sm font-semibold hover:bg-slate-800 transition-colors disabled:opacity-60"
            >
              {step === 'submitting' ? 'Gönderiliyor...' : 'ONAYLA'}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
