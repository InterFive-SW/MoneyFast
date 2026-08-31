import {
    Area, CartesianGrid, Cell, ComposedChart, Legend, Line, Pie, PieChart,
    ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { toNumber, seriesName } from '../../lib/chartFormat'
import { benchmarkName, toComparisonSeries } from '../../lib/riskFormat'
import { formatMoney } from '../../lib/money'
import { formatDateTime } from '../../lib/datetime'
import { useAnalysis } from '../Analiz'

/**
 * Analiz > Genel Bakış — ne kadarım var ve nasıl gitti.
 *
 * Eski `pages/Analytics.tsx`'in içeriği. Başlık ve dört özet kartı buradan
 * çıktı: ikisi de artık her sekmede duran özet şeritte ve orada bir kez
 * gösteriliyor.
 */
const SLICE_COLORS = [
    '#0ea5e9', '#10b981', '#f59e0b', '#8b5cf6',
    '#ef4444', '#14b8a6', '#f472b6', '#a3e635',
]

function pct(value: number | null | undefined): string {
    if (value == null) return '—'
    return `%${value.toLocaleString('tr-TR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}`
}

export default function GenelBakis() {
    const { analysis } = useAnalysis()

    if (!analysis) {
        return (
            <p className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">
                Portföy analizi bu sefer alınamadı.
            </p>
        )
    }

    const currency = analysis.base_currency ?? 'TRY'
    const tl = (value: number | null | undefined) => formatMoney(value ?? 0, currency)
    const series = toComparisonSeries(analysis.trend, analysis.benchmark)
    const indexName = benchmarkName(analysis.benchmark?.symbol)

    return (
        <>
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
                                    data={(analysis.allocation ?? []).map((slice) => ({ ...slice }))}
                                    dataKey="value"
                                    nameKey="label"
                                    innerRadius={60}
                                    outerRadius={100}
                                    paddingAngle={2}
                                >
                                    {(analysis.allocation ?? []).map((slice, index) => (
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
                        {(analysis.allocation ?? []).slice(0, 6).map((slice, index) => (
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
                        {(analysis.sectors ?? []).map((slice, index) => (
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
                        {(analysis.sectors ?? []).length === 0 && (
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
                        <span>Getiri: <span className="tabular-nums text-white">{pct(analysis.performance.total_return_percent)}</span></span>
                        <span>
                            Volatilite:{' '}
                            <span className="tabular-nums text-white">
                                {analysis.performance.annualised_volatility != null
                                    ? `%${(analysis.performance.annualised_volatility * 100).toFixed(1)}`
                                    : '—'}
                            </span>
                        </span>
                        <span>Max düşüş: <span className="tabular-nums text-white">{pct(analysis.performance.max_drawdown_percent)}</span></span>
                    </div>
                </div>

                <div className="h-[300px]">
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={series}>
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
                                formatter={(value, name) => [
                                    tl(toNumber(value)),
                                    name === 'benchmark' ? indexName : 'Portföy değeri',
                                ]}
                                contentStyle={{ borderRadius: '12px', border: 'none', fontSize: '12px' }}
                            />
                            <Area type="monotone" dataKey="value" name="Portföy" stroke="#10b981" strokeWidth={2} fill="url(#trendFill)" />
                            {/* Endeks, portföyün İLK değerine ölçekli: ikisi aynı
                                noktadan başlar ve sonraki ayrışma tamamen göreli
                                performanstır. İkisini 100'e normalize etmek aynı
                                bilgiyi verirdi ama portföyün TL büyüklüğünü
                                ekrandan silerdi. `connectNulls` KAPALI: endeksin
                                işlem görmediği günü yatay çizmek, olmayan bir
                                hareketsizliği göstermek olur. */}
                            {indexName && (
                                <Line
                                    type="monotone"
                                    dataKey="benchmark"
                                    name={indexName}
                                    stroke="#94a3b8"
                                    strokeWidth={1.5}
                                    strokeDasharray="4 3"
                                    dot={false}
                                    connectNulls={false}
                                />
                            )}
                            {indexName && (
                                <Legend
                                    verticalAlign="top"
                                    height={28}
                                    iconType="plainline"
                                    wrapperStyle={{ fontSize: 11, color: '#94a3b8' }}
                                />
                            )}
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {!analysis.performance.is_statistically_reliable && (
                    <p className="mt-3 text-xs text-amber-300/80">
                        Gözlem sayısı ({analysis.performance.observations}) istatistiksel olarak
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
                        { label: 'Onaylanan işlem', value: String(analysis.activity.confirmed_count) },
                        { label: 'Alış', value: String(analysis.activity.buy_count) },
                        { label: 'Satış', value: String(analysis.activity.sell_count) },
                        { label: 'Toplam hacim', value: tl(analysis.activity.total_traded_value) },
                    ].map((item) => (
                        <div key={item.label}>
                            <div className="text-[11px] uppercase tracking-wider text-slate-400">{item.label}</div>
                            <div className="mt-1 text-lg font-bold tabular-nums text-white">{item.value}</div>
                        </div>
                    ))}
                </div>
                {analysis.activity.last_transaction_at && (
                    <p className="mt-3 text-xs text-slate-400">
                        Son işlem: {formatDateTime(analysis.activity.last_transaction_at)}
                    </p>
                )}
            </div>

            {/* Uyarılar — hesabın neyi kapsamadığı, gizlenmeden */}
            {(analysis.warnings ?? []).length > 0 && (
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                        Yöntem notları
                    </div>
                    <ul className="flex flex-col gap-1">
                        {(analysis.warnings ?? []).map((warning) => (
                            <li key={warning} className="text-xs leading-relaxed text-slate-400">• {warning}</li>
                        ))}
                    </ul>
                </div>
            )}
        </>
    )
}
