import { useEffect, useState } from 'react'
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { apiClient } from '../../api/client'
import { paddedDomain } from '../../lib/chartFormat'
import { formatCompact, formatMoney } from '../../lib/money'
import { formatDate } from '../../lib/datetime'

/**
 * Bir fonun NAV grafiği.
 *
 * Buradaki karşılaştırma grafiği tamamen SENTETİKTİ: `comparisonSeries.ts`
 * seed'li bir rastgele yürüyüş üretiyordu ve fon kodundan başka hiçbir şeyi
 * gerçek veriye bağlı değildi. Bu grafik `market.fund_prices` okuyor.
 *
 * Mum değil ÇİZGİ: fon fiyatı günde bir kez yayımlanıyor, yani bir günün
 * açılış/yüksek/düşük değeri YOK. Mum çizmek o üç değeri uydurmak olurdu --
 * hisse grafiğinde mum doğru, burada değil.
 */
export default function FundPriceChart({ code }: { code: string }) {
  const [points, setPoints] = useState<{ date: string; price: number }[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    apiClient
      .getFundPrices(code)
      .then((response) => {
        if (!cancelled) setPoints(response.points ?? [])
      })
      .catch(() => {
        if (!cancelled) setError('Fiyat serisi yüklenemedi.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [code])

  const data = points.map((point) => ({
    label: formatDate(point.date, { day: '2-digit', month: 'short' }),
    value: point.price,
  }))
  const domain = paddedDomain(data.map((row) => row.value))
  const span = domain[1] - domain[0]

  return (
    <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
      <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
        Fiyat Grafiği
        <span className="ml-2 normal-case tracking-normal text-slate-500">(₺)</span>
      </h3>

      {loading && <p className="py-8 text-center text-xs text-slate-500">Yükleniyor…</p>}
      {!loading && error && <p className="py-8 text-center text-xs text-rose-400">{error}</p>}
      {!loading && !error && data.length === 0 && (
        <p className="py-8 text-center text-xs text-slate-400">
          Bu fon için fiyat serisi henüz alınmadı.
        </p>
      )}

      {!loading && !error && data.length > 0 && (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10, fill: '#94a3b8' }}
                tickLine={false}
                axisLine={false}
                minTickGap={32}
              />
              <YAxis
                tick={{ fontSize: 10, fill: '#94a3b8' }}
                tickLine={false}
                axisLine={false}
                width={64}
                domain={domain}
                /* Hassasiyet aralıktan: bir fon fiyatı 3,35 ile 3,41
                   arasında geziniyor ve büyüklüğe dayalı bir kural beş
                   etiketin beşini de "3" yazardı. */
                tickFormatter={(value: number) => formatCompact(value, span)}
              />
              <Tooltip
                formatter={(value: unknown) => formatMoney(Number(value))}
                contentStyle={{
                  background: '#0f172a', border: '1px solid #1e293b',
                  borderRadius: 8, fontSize: 12,
                }}
              />
              <Line type="monotone" dataKey="value" stroke="#4B7BE5" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
