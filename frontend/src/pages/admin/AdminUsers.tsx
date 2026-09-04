import { useCallback, useEffect, useState } from 'react'

import { adminApi, type AdminAccount, type AdminSubscription, type AdminUserRow } from '../../api/adminClient'
import { formatMoney } from '../../lib/money'

/**
 * Customer accounts, and the two adjustments an operator can make.
 *
 * Both go through the ledger on the backend, so a credit here appears in the
 * customer's own statement rather than only in their balance. The point of the
 * screen is to make that possible without anyone opening psql.
 */
/** Hesap türü etiketleri. Operatörün "hangi hesap" sorusunun cevabı. */
const ACCOUNT_LABELS: Record<string, string> = {
  vadesiz: 'Vadesiz',
  vadeli: 'Vadeli',
  yatirim: 'Yatırım',
}

export default function AdminUsers() {
  const [rows, setRows] = useState<AdminUserRow[]>([])
  const [selected, setSelected] = useState<AdminUserRow | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const [cashAmount, setCashAmount] = useState('')
  const [accounts, setAccounts] = useState<AdminAccount[]>([])
  const [targetAccountId, setTargetAccountId] = useState('')
  const [subscriptions, setSubscriptions] = useState<AdminSubscription[]>([])
  const [subInstitution, setSubInstitution] = useState('')
  const [subNumber, setSubNumber] = useState('')
  const [symbol, setSymbol] = useState('')
  const [quantity, setQuantity] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setRows(await adminApi.users())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Müşteriler alınamadı.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  // The chosen customer's accounts and subscriber numbers. Loaded on
  // selection rather than with the list: an operator looks at one customer at
  // a time, and fetching them for everyone would be a request per row.
  useEffect(() => {
    if (!selected) { setAccounts([]); setSubscriptions([]); return }
    let cancelled = false
    void (async () => {
      try {
        const [accountRows, subs] = await Promise.all([
          adminApi.accounts(selected.id),
          adminApi.subscriptions(selected.id),
        ])
        if (cancelled) return
        setAccounts(accountRows)
        setSubscriptions(subs)
        // Default to the deposit account, which is what an operator means by
        // "add money" unless they say otherwise.
        setTargetAccountId(
          accountRows.find(a => a.account_type === 'vadesiz')?.id ?? accountRows[0]?.id ?? '',
        )
      } catch {
        if (!cancelled) { setAccounts([]); setSubscriptions([]) }
      }
    })()
    return () => { cancelled = true }
  }, [selected])

  const run = async (action: () => Promise<{ message: string }>) => {
    setError(null); setNotice(null)
    try {
      const result = await action()
      setNotice(result.message)
      await load()
      // The selected row is a snapshot; refresh it so the panel does not show
      // a balance the list has already moved past.
      setSelected((current) =>
        current ? (rows.find((r) => r.id === current.id) ?? current) : current)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'İşlem uygulanamadı.')
    }
  }

  if (loading) return <p className="text-sm text-slate-400">Yükleniyor…</p>

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-white">Müşteriler</h1>
      {error && <p className="text-sm text-rose-400">{error}</p>}
      {notice && <p className="text-sm text-emerald-400">{notice}</p>}

      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="p-3">TC</th><th className="p-3">Ad Soyad</th>
              <th className="p-3 text-right">Nakit</th>
              <th className="p-3 text-right">Portföy</th>
              <th className="p-3 text-right">Pozisyon</th>
              <th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-slate-800">
                <td className="p-3 font-mono text-slate-300">{row.tc_no}</td>
                <td className="p-3 text-white">{row.full_name}</td>
                <td className="p-3 text-right tabular-nums text-slate-200">
                  {formatMoney(row.cash_balance, row.currency_code)}
                </td>
                <td className="p-3 text-right tabular-nums text-slate-200">
                  {formatMoney(row.portfolio_value, row.currency_code)}
                </td>
                <td className="p-3 text-right tabular-nums text-slate-400">{row.position_count}</td>
                <td className="p-3 text-right">
                  <button
                    onClick={() => { setSelected(row); setNotice(null); setError(null) }}
                    className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
                  >
                    Düzenle
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <h2 className="font-semibold text-white">
            {selected.full_name} <span className="font-mono text-xs text-slate-500">{selected.tc_no}</span>
          </h2>

          <div className="mt-4 grid gap-6 md:grid-cols-2">
            <div>
              <p className="text-xs font-semibold uppercase text-slate-500">Bakiye</p>
              <p className="mt-1 text-xs text-slate-500">
                Pozitif yatırır, negatif çeker. Hangi hesaba gideceğini seçin —
                yatırım hesabı da buradan yüklenir.
              </p>
              <div className="mt-2 flex gap-2">
                <select
                  value={targetAccountId}
                  onChange={(e) => setTargetAccountId(e.target.value)}
                  className="rounded-lg border border-slate-700 bg-slate-800 p-2 text-sm text-white"
                >
                  {accounts.map(acc => (
                    <option key={acc.id} value={acc.id}>
                      {ACCOUNT_LABELS[acc.account_type] ?? acc.account_type}
                      {' · '}
                      {acc.balance.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}
                    </option>
                  ))}
                </select>
                <input
                  value={cashAmount} onChange={(e) => setCashAmount(e.target.value)}
                  placeholder="örn. 2500 veya -500"
                  className="flex-1 rounded-lg border border-slate-700 bg-slate-800 p-2 text-sm text-white"
                />
                <button
                  onClick={() => run(() => adminApi.adjustCash(
                    selected.id, Number(cashAmount), targetAccountId,
                  ))}
                  disabled={cashAmount.trim() === '' || Number.isNaN(Number(cashAmount))}
                  className="rounded-lg bg-brandBlue px-4 text-sm font-semibold text-white disabled:opacity-50"
                >
                  Uygula
                </button>
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold uppercase text-slate-500">Pozisyon</p>
              <p className="mt-1 text-xs text-slate-500">
                Pozitif ekler, negatif çıkarır. Güncel piyasa fiyatından maliyetlenir.
              </p>
              <div className="mt-2 flex gap-2">
                <input
                  value={symbol} onChange={(e) => setSymbol(e.target.value)}
                  placeholder="THYAO"
                  className="w-28 rounded-lg border border-slate-700 bg-slate-800 p-2 text-sm text-white"
                />
                <input
                  value={quantity} onChange={(e) => setQuantity(e.target.value)}
                  placeholder="adet"
                  className="flex-1 rounded-lg border border-slate-700 bg-slate-800 p-2 text-sm text-white"
                />
                <button
                  onClick={() => run(() => adminApi.adjustPosition(selected.id, symbol.trim(), Number(quantity)))}
                  disabled={symbol.trim() === '' || quantity.trim() === '' || Number.isNaN(Number(quantity))}
                  className="rounded-lg bg-brandBlue px-4 text-sm font-semibold text-white disabled:opacity-50"
                >
                  Uygula
                </button>
              </div>
            </div>
          </div>

          <div className="mt-6 border-t border-slate-800 pt-5">
            <p className="text-xs font-semibold uppercase text-slate-500">
              Abone numaraları
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Atanan numara müşterinin Kayıtlı İşlemler'ine düşer; demo
              sırasında buradan okuyup ödeyebilirsiniz.
            </p>
            {subscriptions.length > 0 && (
              <ul className="mt-3 space-y-1">
                {subscriptions.map(sub => (
                  <li key={sub.id} className="font-mono text-xs text-slate-300">
                    {sub.institution} · {sub.subscriber_no}
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-3 flex gap-2">
              <input
                value={subInstitution} onChange={(e) => setSubInstitution(e.target.value)}
                placeholder="Kurum"
                className="w-40 rounded-lg border border-slate-700 bg-slate-800 p-2 text-sm text-white"
              />
              <input
                value={subNumber} onChange={(e) => setSubNumber(e.target.value)}
                placeholder="Abone No"
                className="flex-1 rounded-lg border border-slate-700 bg-slate-800 p-2 text-sm text-white"
              />
              <button
                onClick={() => run(async () => {
                  await adminApi.assignSubscription({
                    user_id: selected.id,
                    institution: subInstitution.trim(),
                    subscriber_no: subNumber.trim(),
                  })
                  setSubscriptions(await adminApi.subscriptions(selected.id))
                  setSubInstitution(''); setSubNumber('')
                  return { message: 'Abone numarası atandı.' }
                })}
                disabled={subInstitution.trim() === '' || subNumber.trim() === ''}
                className="rounded-lg bg-brandBlue px-4 text-sm font-semibold text-white disabled:opacity-50"
              >
                Ata
              </button>
            </div>
          </div>

          <button
            onClick={() => setSelected(null)}
            className="mt-5 text-xs text-slate-400 hover:text-slate-200"
          >
            Kapat
          </button>
        </div>
      )}
    </div>
  )
}
