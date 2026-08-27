import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import {
    NOT_MEASURED,
    describeEffectiveN,
    formatPercent,
    toBreakdown,
} from '../../lib/riskFormat'
import type { BreakdownSlice } from '../../lib/riskFormat'
import Term from '../common/Term'

/**
 * Yoğunlaşma kırılımları.
 *
 * Motor sektör, para birimi ve varlık sınıfı ağırlıklarını her istekte
 * hesaplıyordu; sayfa hiçbirini göstermiyordu. Yoğunlaşma puanın %35'ini
 * belirliyor, dolayısıyla "neden bu puan" sorusunun cevabının büyük kısmı
 * buradaydı ve görünmüyordu.
 */
interface RiskConcentrationPanelProps {
    concentration: Record<string, unknown> | undefined
}

/** Aynı palet `AssetAllocationWidget` ile paylaşılıyor. */
const COLORS = ['#0ea5e9', '#8b5cf6', '#10b981', '#f59e0b', '#f43f5e', '#64748b']

function Breakdown({ title, slices }: { title: string; slices: BreakdownSlice[] }) {
    if (slices.length === 0) return null
    return (
        <div className="rounded-xl bg-white/5 p-4">
            <p className="mb-2 text-xs font-medium text-slate-400">{title}</p>
            <div className="h-32">
                <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                        <Pie
                            data={slices}
                            dataKey="weight"
                            nameKey="label"
                            innerRadius={28}
                            outerRadius={52}
                            paddingAngle={2}
                        >
                            {slices.map((slice, index) => (
                                <Cell key={slice.label} fill={COLORS[index % COLORS.length]} />
                            ))}
                        </Pie>
                        <Tooltip
                            contentStyle={{
                                background: '#0f172a',
                                border: '1px solid rgba(255,255,255,0.1)',
                                borderRadius: 8,
                                fontSize: 12,
                            }}
                            formatter={(value: unknown) => formatPercent(Number(value), 1)}
                        />
                    </PieChart>
                </ResponsiveContainer>
            </div>
            <ul className="mt-2 flex flex-col gap-1">
                {slices.slice(0, 4).map((slice, index) => (
                    <li key={slice.label} className="flex items-center gap-2 text-xs">
                        <span
                            className="h-2 w-2 shrink-0 rounded-full"
                            style={{ background: COLORS[index % COLORS.length] }}
                        />
                        <span className="flex-1 truncate text-slate-300">{slice.label}</span>
                        <span className="text-slate-400">{slice.percent}</span>
                    </li>
                ))}
            </ul>
        </div>
    )
}

export default function RiskConcentrationPanel({
    concentration,
}: RiskConcentrationPanelProps) {
    if (!concentration) return null

    const effectiveN =
        typeof concentration.effective_n === 'number' ? concentration.effective_n : null
    const top3 =
        typeof concentration.top_3_weight === 'number' ? concentration.top_3_weight : null
    const largest = concentration.largest_position as
        | { symbol?: string; weight?: number }
        | undefined

    return (
        <div className="flex flex-col rounded-2xl border border-white/10 bg-slate-900/50 p-6 shadow-2xl backdrop-blur-xl">
            <h3 className="mb-1 flex items-center gap-2 text-base font-semibold text-white">
                Yoğunlaşma
                <Term termKey="concentration" />
            </h3>
            <p className="mb-4 text-xs text-slate-400">
                Puanın %35’ini belirleyen ölçü: değerin kaç isme dağıldığı.
            </p>

            <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="rounded-xl bg-white/5 p-4">
                    <p className="flex items-center gap-1.5 text-xs font-medium text-slate-400">
                        Etkin dağılım
                        <Term termKey="effective_n" />
                    </p>
                    <p className="mt-1 text-lg font-semibold text-white">
                        {describeEffectiveN(effectiveN)}
                    </p>
                    <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
                        Eşit ağırlıklı kaç pozisyona denk geldiğinin ölçüsü.
                    </p>
                </div>
                <div className="rounded-xl bg-white/5 p-4">
                    <p className="text-xs font-medium text-slate-400">En büyük üç pozisyon</p>
                    <p className="mt-1 text-lg font-semibold text-white">
                        {top3 === null ? NOT_MEASURED : formatPercent(top3, 1)}
                    </p>
                    <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
                        Portföy değerinin bu kadarı üç isimde.
                    </p>
                </div>
                <div className="rounded-xl bg-white/5 p-4">
                    <p className="text-xs font-medium text-slate-400">En büyük pozisyon</p>
                    <p className="mt-1 text-lg font-semibold text-white">
                        {largest?.symbol ?? NOT_MEASURED}
                    </p>
                    <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
                        {typeof largest?.weight === 'number'
                            ? `Portföyün ${formatPercent(largest.weight, 1)}’i.`
                            : 'Ağırlık ölçülemedi.'}
                    </p>
                </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <Breakdown title="Sektör" slices={toBreakdown(concentration.by_sector)} />
                <Breakdown
                    title="Varlık sınıfı"
                    slices={toBreakdown(concentration.by_asset_class)}
                />
                <Breakdown title="Para birimi" slices={toBreakdown(concentration.by_currency)} />
            </div>
        </div>
    )
}
