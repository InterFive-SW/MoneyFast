import {
    CartesianGrid,
    Line,
    LineChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts'
import { useRiskHistory } from '../../hooks/useRiskHistory'
import { formatDate } from '../../lib/riskFormat'
import Term from '../common/Term'

/**
 * Risk puanının zaman içindeki seyri.
 *
 * Noktalar risk sayfası okundukça birikiyor, geriye dönük ÜRETİLMİYOR. Bu bir
 * kısıt değil bir tercih: geçmiş bir günün puanını bugünün pozisyonlarıyla
 * hesaplamak, o gün sahip olunmayan bir portföyün riskini raporlamak olurdu.
 *
 * Üç durum ayrı: hiç ölçüm yok, tek ölçüm var, gerçek seri var. Tek noktalı
 * bir çizgi "değişim yok" gibi okunur, oysa daha ölçülecek ikinci gün
 * gelmemiştir.
 */
export default function RiskHistoryPanel() {
    const history = useRiskHistory(90)

    const data = history.points
        .filter((point) => typeof point.score === 'number')
        .map((point) => ({
            date: formatDate(point.captured_on) ?? point.captured_on,
            score: point.score as number,
        }))

    const shell =
        'flex flex-col rounded-2xl border border-white/10 bg-slate-900/50 p-6 shadow-2xl backdrop-blur-xl'

    return (
        <div className={shell}>
            <div className="mb-1 flex items-start justify-between gap-3">
                <h3 className="flex items-center gap-2 text-base font-semibold text-white">
                    Risk puanınızın seyri
                    <Term termKey="risk_score" align="right" />
                </h3>
                {history.trend.change !== null && (
                    <span
                        className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${
                            history.trend.change > 0
                                ? 'bg-emerald-500/10 text-emerald-400'
                                : history.trend.change < 0
                                  ? 'bg-rose-500/10 text-rose-400'
                                  : 'bg-white/5 text-slate-400'
                        }`}
                    >
                        {history.trend.change > 0 ? '+' : ''}
                        {history.trend.change.toLocaleString('tr-TR')} puan
                    </span>
                )}
            </div>
            <p className="mb-4 text-xs leading-relaxed text-slate-400">
                Bu sayfayı her açtığınızda o günün ölçümü kaydediliyor. Geçmişe dönük
                puan üretilmez — o gün sahip olmadığınız bir portföyün riskini
                raporlamak olurdu.
            </p>

            {history.error && (
                <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
                    {history.error}
                </p>
            )}

            {!history.error && !history.loading && !history.hasSeries && (
                <p className="rounded-lg bg-white/5 px-3 py-4 text-center text-sm leading-relaxed text-slate-400">
                    {history.points.length === 0
                        ? 'Henüz kayıtlı ölçüm yok. Bugünün ölçümü kaydedildi; ikinci gün geldiğinde burada bir çizgi göreceksiniz.'
                        : 'Şimdilik tek bir ölçüm var. Bir gün daha geçtiğinde seyir çizilecek.'}
                </p>
            )}

            {history.hasSeries && (
                <>
                    <div className="h-48">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={data}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                                <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                                <YAxis domain={[0, 100]} tick={{ fill: '#94a3b8', fontSize: 11 }} />
                                <Tooltip
                                    contentStyle={{
                                        background: '#0f172a',
                                        border: '1px solid rgba(255,255,255,0.1)',
                                        borderRadius: 8,
                                        fontSize: 12,
                                    }}
                                />
                                <Line
                                    type="monotone"
                                    dataKey="score"
                                    stroke="#0ea5e9"
                                    strokeWidth={2}
                                    dot={{ r: 3, fill: '#0ea5e9' }}
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                    <p className="mt-2 text-center text-[11px] text-slate-500">
                        100’e yakın puan daha sakin bir portföy demek. Ölçüm penceresi:{' '}
                        {history.lookback}.
                    </p>
                </>
            )}
        </div>
    )
}
