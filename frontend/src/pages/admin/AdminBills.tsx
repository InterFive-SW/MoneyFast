import { useCallback, useEffect, useState } from 'react'

import { adminApi, type AdminBill } from '../../api/adminClient'
import { formatMoney } from '../../lib/money'

const TYPES = [
  { value: 'electricity', label: 'Elektrik' },
  { value: 'water', label: 'Su' },
  { value: 'internet', label: 'İnternet' },
  { value: 'phone', label: 'Telefon' },
]

/**
 * Issuing bills for customers to find.
 *
 * A bill is issued against a SUBSCRIBER NUMBER, not a customer: whoever knows
 * the number pays it, which is how the paper works and what makes the saved
 * payee on the customer's side worth having.
 */
export default function AdminBills() {
  const [bills, setBills] = useState<AdminBill[]>([])
  const [error, setError] = useState<string | null>(null)
  const [institution, setInstitution] = useState('')
  const [holderName, setHolderName] = useState('')
  const [billType, setBillType] = useState(TYPES[0].value)
  const [subscriberNo, setSubscriberNo] = useState('')
  const [amount, setAmount] = useState('')
  const [dueDay, setDueDay] = useState('15')

  const load = useCallback(async () => {
    try {
      setBills((await adminApi.bills()).bills)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Faturalar alınamadı.')
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const issue = async () => {
    setError(null)
    try {
      await adminApi.issueBill({
        institution: institution.trim(), bill_type: billType,
        subscriber_no: subscriberNo.trim(), amount: Number(amount),
        due_day: Number(dueDay),
        // Left blank, the backend takes the name of whoever the subscriber
        // number is assigned to -- usually who the bill was meant for anyway.
        holder_name: holderName.trim() || undefined,
      })
      setSubscriberNo(''); setAmount(''); setHolderName('')
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fatura tanımlanamadı.')
    }
  }

  const withdraw = async (id: string) => {
    setError(null)
    try {
      await adminApi.withdrawBill(id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fatura geri çekilemedi.')
    }
  }

  const ready =
    institution.trim() !== '' && subscriberNo.trim() !== '' &&
    amount.trim() !== '' && !Number.isNaN(Number(amount))

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-white">Faturalar</h1>
      {error && <p className="text-sm text-rose-400">{error}</p>}

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h2 className="font-semibold text-white">Yeni Fatura Tanımla</h2>
        <p className="mt-1 text-xs text-slate-500">
          Fatura abone numarasına kesilir, kişiye değil. Numara bir müşteriye
          atanmışsa adı otomatik gelir.
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-6">
          <input
            value={holderName} onChange={(e) => setHolderName(e.target.value)}
            placeholder="Fatura sahibi (ops.)"
            className="rounded-lg border border-slate-700 bg-slate-800 p-2 text-sm text-white"
          />
          <input
            value={institution} onChange={(e) => setInstitution(e.target.value)}
            placeholder="Kurum (BEDAŞ)"
            className="rounded-lg border border-slate-700 bg-slate-800 p-2 text-sm text-white"
          />
          <select
            value={billType} onChange={(e) => setBillType(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-800 p-2 text-sm text-white"
          >
            {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
          <input
            value={subscriberNo} onChange={(e) => setSubscriberNo(e.target.value)}
            placeholder="Abone No"
            className="rounded-lg border border-slate-700 bg-slate-800 p-2 text-sm text-white"
          />
          <input
            value={amount} onChange={(e) => setAmount(e.target.value)}
            placeholder="Tutar"
            className="rounded-lg border border-slate-700 bg-slate-800 p-2 text-sm text-white"
          />
          <div className="flex gap-2">
            <input
              value={dueDay} onChange={(e) => setDueDay(e.target.value)}
              placeholder="Gün"
              className="w-20 rounded-lg border border-slate-700 bg-slate-800 p-2 text-sm text-white"
            />
            <button
              onClick={issue} disabled={!ready}
              className="flex-1 rounded-lg bg-brandBlue px-4 text-sm font-semibold text-white disabled:opacity-50"
            >
              Tanımla
            </button>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="p-3">Kurum</th><th className="p-3">Abone No</th>
              <th className="p-3">Fatura Sahibi</th><th className="p-3">Atanan Müşteri</th>
              <th className="p-3 text-right">Tutar</th><th className="p-3">Son Gün</th>
              <th className="p-3">Durum</th><th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {bills.length === 0 && (
              <tr><td colSpan={8} className="p-4 text-slate-500">Henüz fatura tanımlanmadı.</td></tr>
            )}
            {bills.map((bill) => (
              <tr key={bill.id} className="border-t border-slate-800">
                <td className="p-3 text-white">{bill.institution}</td>
                <td className="p-3 font-mono text-slate-300">{bill.subscriber_no}</td>
                <td className="p-3 text-slate-300">{bill.holder_name ?? '—'}</td>
                <td className="p-3 text-slate-300">
                  {bill.assigned_to ?? <span className="text-slate-600">atanmamış</span>}
                </td>
                <td className="p-3 text-right tabular-nums text-slate-200">
                  {formatMoney(bill.amount)}
                </td>
                <td className="p-3 text-slate-400">Her ayın {bill.due_day}.</td>
                <td className="p-3">
                  <span className={bill.status === 'paid' ? 'text-emerald-400' : 'text-amber-400'}>
                    {bill.status === 'paid' ? 'Ödendi' : 'Bekliyor'}
                  </span>
                  {bill.paid_by_name && (
                    <p className="text-xs text-slate-500">{bill.paid_by_name}</p>
                  )}
                </td>
                <td className="p-3 text-right">
                  {bill.status !== 'paid' && (
                    <button
                      onClick={() => withdraw(bill.id)}
                      className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
                    >
                      Geri Çek
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
