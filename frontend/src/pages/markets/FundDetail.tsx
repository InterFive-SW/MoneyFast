import { Link, useParams } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { apiClient, type ApiFund } from '../../api/client'
import { formatCompact, formatMoney } from '../../lib/money'
import { formatDate } from '../../lib/datetime'
import FundPriceChart from '../../components/markets/FundPriceChart'

/**
 * Tek fon sayfası — TEFAS.
 *
 * "Portföy Dağılımı" sekmesi KALDIRILDI. Mock'ta hisse bazında bir donut
 * vardı; TEFAS `dagilimSiraliGetirT` ile varlık SINIFI yüzdeleri veriyor
 * (`dt`, `fb`, `kkstl`, `osks`...) ama sütun etiketleri HAR kaydında yok,
 * yani hangi kodun hangi varlık sınıfı olduğu tahmine kalıyor. Tahmin
 * edilmedi -- bkz. `docs/TEFAS_INTEGRATION.md`.
 *
 * Yerine gerçek NAV grafiği geldi: fonun kendi fiyat serisi.
 */
export default function FundDetail() {
  const { code = '' } = useParams()
  const [fund, setFund] = useState<ApiFund | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    apiClient
      .getFunds({ q: code, limit: 5 })
      .then((response) => {
        if (cancelled) return
        const match = (response.items ?? []).find(
          (row) => row.code.toUpperCase() === code.toUpperCase(),
        )
        setFund(match ?? null)
      })
      .catch(() => {
        if (!cancelled) setError('Fon bilgisi yüklenemedi.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [code])

  if (loading) {
    return <p className="py-10 text-center text-sm text-slate-400">Yükleniyor…</p>
  }
  if (error) {
    return <p className="py-10 text-center text-sm text-rose-400">{error}</p>
  }
  if (!fund) {
    return (
      <div className="py-10 text-center">
        <p className="text-sm text-slate-400">{code.toUpperCase()} kodlu fon bulunamadı.</p>
        <Link to="/investment/fonlar" className="mt-3 inline-block text-sm text-sky-300 hover:underline">
          Fonlar listesine dön
        </Link>
      </div>
    )
  }

  const stats: { label: string; value: string }[] = [
    { label: 'Fiyat', value: fund.price == null ? '—' : formatMoney(fund.price) },
    { label: 'Fon Büyüklüğü', value: fund.size == null ? '—' : `${formatCompact(fund.size)} ₺` },
    { label: 'Yatırımcı Sayısı', value: fund.investorCount == null ? '—' : formatCompact(fund.investorCount) },
    // Fon fiyatı GÜNLÜKTÜR; saat göstermek olmayan bir anlık değeri varmış
    // gibi gösterirdi.
    { label: 'Fiyat Tarihi', value: fund.asOf ? formatDate(fund.asOf) : '—' },
  ]

  return (
    <div className="flex flex-col gap-6">
      <Link to="/investment/fonlar" className="text-sm text-slate-400 hover:text-slate-200">
        ‹ Fonlar listesine dön
      </Link>

      <div className="rounded-[2rem] border border-white/10 bg-slate-900/50 p-6 shadow-2xl">
        <div className="flex flex-wrap items-baseline gap-3">
          <span className="text-2xl font-bold text-white">{fund.code}</span>
          {fund.umbrella && (
            <span className="rounded bg-white/5 px-2 py-0.5 text-[11px] text-slate-300">
              {fund.umbrella}
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-slate-300">{fund.name}</p>
        {fund.founder && <p className="mt-0.5 text-xs text-slate-400">{fund.founder}</p>}
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label} className="rounded-2xl border border-white/10 bg-slate-900/50 p-4">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              {stat.label}
            </div>
            <div className="text-sm font-bold tabular-nums text-white">{stat.value}</div>
          </div>
        ))}
      </div>

      <FundPriceChart code={fund.code} />

      <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
        <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Getiri
        </h3>
        <table className="w-full text-sm">
          <tbody className="divide-y divide-white/5">
            {([
              ['Günlük', fund.returns.daily],
              ['1 Ay', fund.returns.monthly],
              ['3 Ay', fund.returns.threeMonth],
              ['1 Yıl', fund.returns.yearly],
              ['3 Yıl', fund.returns.threeYear],
              ['5 Yıl', fund.returns.fiveYear],
            ] as [string, number | null][]).map(([label, value]) => (
              <tr key={label}>
                <td className="py-2 text-slate-400">{label}</td>
                <td
                  className={`py-2 text-right font-semibold tabular-nums ${
                    value === null
                      ? 'text-slate-500'
                      : value < 0
                        ? 'text-rose-400'
                        : 'text-emerald-400'
                  }`}
                >
                  {/* `NA` ölçülemedi demek: fonun o kadar geçmişi yok.
                      Sıfırla aynı şey değil. */}
                  {value === null ? 'NA' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
