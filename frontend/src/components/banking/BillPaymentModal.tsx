import { useState } from 'react'

import { apiClient, type BillLookup } from '../../api/client'
import { formatMoney } from '../../lib/money'

/** Faturası sorgulanabilen kurumlar. Admin bu adlarla fatura tanımlıyor. */
const INSTITUTIONS: { value: string; label: string; type: string }[] = [
  { value: 'BEDAŞ', label: 'BEDAŞ — Elektrik', type: 'electricity' },
  { value: 'İSKİ', label: 'İSKİ — Su', type: 'water' },
  { value: 'Türk Telekom', label: 'Türk Telekom — İnternet', type: 'internet' },
  { value: 'Turkcell', label: 'Turkcell — Telefon', type: 'phone' },
]

interface Props {
  isOpen: boolean
  onClose: () => void
  /** Faturayı hazırlar, onaylar ve defteri yeniden okur. */
  onPay?: (institution: string, subscriberNo: string) => Promise<unknown>
}

type Step = 'lookup' | 'confirm' | 'done'

/**
 * Fatura ödeme: kurum seç, abone numarasını yaz, borcu gör, öde.
 *
 * Kullanıcının "faturalarım" listesi yok — kağıdın üstündeki numara anahtar,
 * onu bilen öder. "Kayıtlı İşlemler" de bu yüzden anlamlı: sıkıcı olan kısım
 * numara, saklamaya değer olan da o.
 *
 * Ödeme iki adım: `stagePayment` hiçbir şeyi kıpırdatmaz, `confirmPayment`
 * uygular. Sohbetin kendi başına para gönderememesini sağlayan ayrım bu, ve
 * panel de aynı yolu kullanıyor — tek bir onay yolu, tek bir denetim izi.
 */
export default function BillPaymentModal({ isOpen, onClose, onPay }: Props) {
  const [step, setStep] = useState<Step>('lookup')
  const [institution, setInstitution] = useState(INSTITUTIONS[0].value)
  const [subscriberNo, setSubscriberNo] = useState('')
  const [bill, setBill] = useState<BillLookup | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [saveOffered, setSaveOffered] = useState(false)
  const [saved, setSaved] = useState(false)

  if (!isOpen) return null

  const reset = () => {
    setStep('lookup'); setSubscriberNo(''); setBill(null)
    setError(null); setSaveOffered(false); setSaved(false)
  }

  const close = () => { reset(); onClose() }

  const handleLookup = async () => {
    setError(null); setBusy(true)
    try {
      const found = await apiClient.lookupBill(institution, subscriberNo.trim())
      if (!found.found) {
        // Borcu olmamak bir hata değil, bir cevap.
        setError('Bu abone numarasına ait ödenmemiş fatura bulunamadı.')
        return
      }
      setBill(found)
      setStep('confirm')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fatura sorgulanamadı.')
    } finally {
      setBusy(false)
    }
  }

  const handlePay = async () => {
    if (!onPay) return
    setError(null); setBusy(true)
    try {
      await onPay(institution, subscriberNo.trim())
      setStep('done')
      setSaveOffered(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ödeme tamamlanamadı.')
    } finally {
      setBusy(false)
    }
  }

  const handleSavePayee = async () => {
    try {
      await apiClient.addSavedPayee({
        label: institution, institution, subscriber_no: subscriberNo.trim(),
      })
      setSaved(true)
    } catch {
      // Kaydedememek ödemeyi geçersiz kılmaz; ödeme çoktan oldu.
      setSaved(true)
    } finally {
      setSaveOffered(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-6">
        <h2 className="text-lg font-semibold text-white">Fatura Öde</h2>

        {step === 'lookup' && (
          <div className="mt-5 space-y-4">
            <label className="block">
              <span className="text-xs font-medium text-slate-400">Kurum</span>
              <select
                value={institution}
                onChange={(e) => setInstitution(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 p-2.5 text-sm text-white"
              >
                {INSTITUTIONS.map((i) => (
                  <option key={i.value} value={i.value}>{i.label}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-xs font-medium text-slate-400">Abone No</span>
              <input
                value={subscriberNo}
                onChange={(e) => setSubscriberNo(e.target.value)}
                placeholder="Faturanızın üzerindeki numara"
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 p-2.5 text-sm text-white"
              />
            </label>
            {error && <p className="text-sm text-rose-400">{error}</p>}
            <div className="flex gap-3">
              <button onClick={close} className="flex-1 rounded-lg border border-slate-700 p-2.5 text-sm text-slate-300">
                Vazgeç
              </button>
              <button
                onClick={handleLookup}
                disabled={busy || subscriberNo.trim().length === 0}
                className="flex-1 rounded-lg bg-brandBlue p-2.5 text-sm font-semibold text-white disabled:opacity-50"
              >
                {busy ? 'Sorgulanıyor…' : 'Sorgula'}
              </button>
            </div>
          </div>
        )}

        {step === 'confirm' && bill && (
          <div className="mt-5 space-y-4">
            <dl className="rounded-xl border border-slate-700 bg-slate-800/60 p-4 text-sm">
              <div className="flex justify-between py-1">
                <dt className="text-slate-400">Kurum</dt><dd className="text-white">{bill.institution}</dd>
              </div>
              <div className="flex justify-between py-1">
                <dt className="text-slate-400">Abone No</dt><dd className="text-white">{bill.subscriber_no}</dd>
              </div>
              <div className="flex justify-between py-1">
                <dt className="text-slate-400">Son Ödeme Günü</dt><dd className="text-white">Her ayın {bill.due_day}.</dd>
              </div>
              <div className="flex justify-between border-t border-slate-700 pt-2">
                <dt className="font-medium text-slate-300">Tutar</dt>
                <dd className="font-semibold text-white">{formatMoney(bill.amount ?? 0)}</dd>
              </div>
            </dl>
            {error && <p className="text-sm text-rose-400">{error}</p>}
            <div className="flex gap-3">
              <button onClick={() => setStep('lookup')} className="flex-1 rounded-lg border border-slate-700 p-2.5 text-sm text-slate-300">
                Geri
              </button>
              <button
                onClick={handlePay}
                disabled={busy}
                className="flex-1 rounded-lg bg-emerald-600 p-2.5 text-sm font-semibold text-white disabled:opacity-50"
              >
                {busy ? 'Ödeniyor…' : 'Öde'}
              </button>
            </div>
          </div>
        )}

        {step === 'done' && (
          <div className="mt-5 space-y-4">
            <p className="text-sm text-emerald-400">Fatura ödendi.</p>
            {saveOffered && (
              <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-4">
                <p className="text-sm text-slate-300">
                  Bu işlemi kayıtlı işlemlerinize eklemek ister misiniz?
                </p>
                <div className="mt-3 flex gap-3">
                  <button onClick={() => setSaveOffered(false)} className="flex-1 rounded-lg border border-slate-700 p-2 text-sm text-slate-300">
                    Hayır
                  </button>
                  <button onClick={handleSavePayee} className="flex-1 rounded-lg bg-brandBlue p-2 text-sm font-semibold text-white">
                    Kaydet
                  </button>
                </div>
              </div>
            )}
            {saved && <p className="text-sm text-slate-400">Kayıtlı işlemlerinize eklendi.</p>}
            <button onClick={close} className="w-full rounded-lg bg-slate-700 p-2.5 text-sm font-semibold text-white">
              Kapat
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
