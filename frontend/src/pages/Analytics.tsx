import { useEffect, useState } from 'react'
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
} from 'recharts'
import { apiClient, type PortfolioAnalysis } from '../api/client'
import { toNumber, seriesName } from '../lib/chartFormat'

/**
 * Portföy Analizi — dağılım, performans trendi ve gerçekleşen işlemler.
 *
 * Tek çağrı (`/api/analytics/portfolio`), çünkü User Story bu ekrana 2 saniye
 * yükleme bütçesi koyuyor; dağılım, trend ve performansı ayrı ayrı istemek
 * aynı pozisyon listesini üç kez okumak olurdu.
 *
 * Hesaplar backend'de `investment` ve `risk` modüllerinin okuduğu kaynaklardan
 * türetiliyor, yeniden yazılmıyor — bu yüzden bu ekranla gösterge paneli
 * portföyün değeri konusunda çelişemez.
 */

const SLICE_COLORS = [
  '#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ef4444',
  '#14b8a6', '#f97316', '#6366f1', '#84cc16', '#ec4899',
]

function tl(value: number | null | undefined): string {
  if (value == null) return '—'
  return value.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₺'
}

function pct(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

export default function Analytics() {
  const [data, setData] = useState<PortfolioAnalysis | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    apiClient
      .getPortfolioAnalysis()
      .then(setData)
      .catch((err) => {
        console.error('Failed to load portfolio analysis', err)
        // User Story 7.1: rapor üretilemezse kullanıcıya söylenir, boş bir
        // ekran bırakılmaz.
        setError('Analiz oluşturulamadı, lütfen tekrar deneyin.')
      })
  }, [])

  if (error) {
    return (
      <div className="p-6 sm:p-8 min-h-screen">
        <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
          {error}
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  const gainLoss = data.unrealised_pnl ?? 0

  return (
    <div className="p-6 sm:p-8 min-h-screen">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-white">Portföy Analizi</h1>
        <p className="mt-1 text-sm text-slate-400">
          Varlık dağılımı, performans trendi ve gerçekleşen işlemler.
          {data.as_of && (
            <> Veriler {new Date(data.as_of).toLocaleString('tr-TR')} itibarıyla
            {data.is_delayed ? ` (${data.delay_minutes} dk gecikmeli).` : '.'}</>
          )}
        </p>
      </div>

      {/* Özet kartları */}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          { label: 'Toplam Değer', value: tl(data.total_value), tone: 'text-white' },
          { label: 'Nakit', value: tl(data.cash), tone: 'text-white' },
          { label: 'Yatırımda', value: tl(data.invested), tone: 'text-white' },
          {
            label: 'Gerçekleşmemiş K/Z',
            value: `${tl(gainLoss)} (${pct(data.unrealised_pnl_percent)})`,
            tone: gainLoss < 0 ? 'text-rose-500' : 'text-emerald-500',
          },
        ].map((card) => (
          <div key={card.label} className="rounded-2xl border border-white/10 bg-slate-900/50 p-4 backdrop-blur-xl">
            <div className="text-[11px] uppercase tracking-wider text-slate-400">{card.label}</div>
            <div className={`mt-1 text-lg font-bold tabular-nums ${card.tone}`}>{card.value}</div>
          </div>
        ))}
      </div>

      <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Varlık dağılımı — BR-02: dilimler her zaman %100 toplar */}
        <div className="rounded-[2rem] border border-white/10 bg-slate-900/50 p-5 backdrop-blur-xl">
          <h3 className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            Varlık Dağılımı
          </h3>
          <div className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={(data.allocation ?? []).map((slice) => ({ ...slice }))}
                  dataKey="value"
                  nameKey="label"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                >
                  {(data.allocation ?? []).map((slice, index) => (
                    <Cell key={slice.label} fill={SLICE_COLORS[index % SLICE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value, name) => [tl(toNumber(value)), seriesName(name)]}
                  contentStyle={{ borderRadius: '12px', border: 'none', fontSize: '12px' }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex flex-col gap-1">
            {(data.allocation ?? []).slice(0, 6).map((slice, index) => (
              <div key={slice.label} className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-2 text-slate-300">
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ background: SLICE_COLORS[index % SLICE_COLORS.length] }}
                  />
                  {slice.label}
                </span>
                <span className="tabular-nums text-slate-400">%{slice.percentage.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Sektör dağılımı */}
        <div className="rounded-[2rem] border border-white/10 bg-slate-900/50 p-5 backdrop-blur-xl">
          <h3 className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            Sektör Dağılımı
          </h3>
          <div className="flex flex-col gap-3">
            {(data.sectors ?? []).map((slice, index) => (
              <div key={slice.label}>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="text-slate-300">{slice.label}</span>
                  <span className="tabular-nums text-slate-400">
                    {tl(slice.value)} · %{slice.percentage.toFixed(2)}
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-white/5">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${slice.percentage}%`,
                      background: SLICE_COLORS[index % SLICE_COLORS.length],
                    }}
                  />
                </div>
              </div>
            ))}
            {(data.sectors ?? []).length === 0 && (
              <p className="text-sm text-slate-400">Sektör bilgisi bulunan pozisyon yok.</p>
            )}
          </div>
        </div>
      </div>

      {/* Performans trendi */}
      <div className="mb-6 rounded-[2rem] border border-white/10 bg-slate-900/50 p-5 backdrop-blur-xl">
        <div className="mb-4 flex items-baseline justify-between">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            Performans Trendi
          </h3>
          <div className="flex gap-4 text-xs text-slate-400">
            <span>Getiri: <span className="tabular-nums text-white">{pct(data.performance.total_return_percent)}</span></span>
            <span>
              Volatilite:{' '}
              <span className="tabular-nums text-white">
                {data.performance.annualised_volatility != null
                  ? `%${(data.performance.annualised_volatility * 100).toFixed(1)}`
                  : '—'}
              </span>
            </span>
            <span>Max düşüş: <span className="tabular-nums text-white">{pct(data.performance.max_drawdown_percent)}</span></span>
          </div>
        </div>

        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={(data.trend ?? []).map((p) => ({ date: p.date.slice(0, 10), value: p.value }))}>
              <defs>
                <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(226,232,240,0.08)" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} minTickGap={40} />
              <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={70}
                tickFormatter={(v) => `${Math.round(Number(v) / 1000)}k`} />
              <Tooltip
                formatter={(value) => [tl(toNumber(value)), 'Portföy değeri']}
                contentStyle={{ borderRadius: '12px', border: 'none', fontSize: '12px' }}
              />
              <Area type="monotone" dataKey="value" stroke="#10b981" strokeWidth={2} fill="url(#trendFill)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {!data.performance.is_statistically_reliable && (
          <p className="mt-3 text-xs text-amber-300/80">
            Gözlem sayısı ({data.performance.observations}) istatistiksel olarak
            güvenilir bir volatilite ölçümü için düşük.
          </p>
        )}
      </div>

      {/* Gerçekleşen işlemler */}
      <div className="mb-6 rounded-[2rem] border border-white/10 bg-slate-900/50 p-5 backdrop-blur-xl">
        <h3 className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Gerçekleşen İşlemler
        </h3>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[
            { label: 'Onaylanan işlem', value: String(data.activity.confirmed_count) },
            { label: 'Alış', value: String(data.activity.buy_count) },
            { label: 'Satış', value: String(data.activity.sell_count) },
            { label: 'Toplam hacim', value: tl(data.activity.total_traded_value) },
          ].map((item) => (
            <div key={item.label}>
              <div className="text-[11px] uppercase tracking-wider text-slate-400">{item.label}</div>
              <div className="mt-1 text-lg font-bold tabular-nums text-white">{item.value}</div>
            </div>
          ))}
        </div>
        {data.activity.last_transaction_at && (
          <p className="mt-3 text-xs text-slate-400">
            Son işlem: {new Date(data.activity.last_transaction_at).toLocaleString('tr-TR')}
          </p>
        )}
      </div>

      {/* Uyarılar — hesabın neyi kapsamadığı, gizlenmeden */}
      {(data.warnings ?? []).length > 0 && (
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            Yöntem notları
          </div>
          <ul className="flex flex-col gap-1">
            {(data.warnings ?? []).map((warning) => (
              <li key={warning} className="text-xs leading-relaxed text-slate-400">• {warning}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
