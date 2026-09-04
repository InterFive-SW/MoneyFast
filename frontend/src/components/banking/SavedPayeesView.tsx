import { useCallback, useEffect, useState } from 'react'

import { apiClient, type SavedPayee } from '../../api/client'

/**
 * Kayıtlı İşlemlerim.
 *
 * Bu ekran bir "faturalarım" listesi DEĞİL: fatura kullanıcıya değil abone
 * numarasına bağlı. Burada duran şey numaranın kendisi — sıkıcı olan kısım o,
 * saklamaya değer olan da o. Bir sonraki ödemede tekrar yazılmasın diye.
 */
export default function SavedPayeesView() {
  const [payees, setPayees] = useState<SavedPayee[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setPayees((await apiClient.getSavedPayees()).payees)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Kayıtlı işlemler alınamadı.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const remove = async (id: string) => {
    try {
      await apiClient.deleteSavedPayee(id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Kayıt silinemedi.')
    }
  }

  if (loading) return <p className="text-sm text-slate-400">Yükleniyor…</p>

  return (
    <div className="w-full max-w-3xl space-y-4">
      <h2 className="text-lg font-semibold text-white">Kayıtlı İşlemlerim</h2>
      {error && <p className="text-sm text-rose-400">{error}</p>}

      {payees.length === 0 ? (
        <p className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm text-slate-400">
          Henüz kayıtlı işleminiz yok. Bir fatura ödedikten sonra kaydetmeyi
          seçerseniz burada görünür.
        </p>
      ) : (
        <ul className="divide-y divide-slate-800 rounded-xl border border-slate-800 bg-slate-900">
          {payees.map((payee) => (
            <li key={payee.id} className="flex items-center justify-between p-4">
              <div>
                <p className="text-sm font-medium text-white">{payee.label}</p>
                <p className="font-mono text-xs text-slate-400">
                  {payee.institution} · {payee.subscriber_no}
                </p>
              </div>
              <button
                onClick={() => remove(payee.id)}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
              >
                Sil
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
