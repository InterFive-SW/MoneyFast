import Term from '../common/Term'
import { formatDate } from '../../lib/datetime'

/**
 * Ölçüm ile kullanıcının kendi beyanının yan yana durduğu kart.
 *
 * Ürünün bu iki şeyi aynı cümlede kullanmasına izin verilen tek yer. Doğru
 * tarafta kalmasının sebebi: iki yarı da olgu. Biri fiyat geçmişinden
 * hesaplanıyor, diğeri kullanıcının kendi cevabı. Kart hiçbir yerde ne
 * yapılması gerektiğini söylemiyor.
 *
 * Karşılaştırma ETİKET üzerinden: ölçülen puan ters (100 = sakin), anketin
 * ham puanı değil. İki sayıyı yan yana koymak er ya da geç ters okunurdu.
 *
 * Anket doldurulmamışken kart kapanmıyor, bir çağrıya dönüşüyor — yumuşak
 * kapı: ölçüm gösterilir, karşılaştırma bekler.
 */
interface Suitability {
    measured_level?: string | null
    declared_tolerance?: string | null
    alignment?: string
    statement?: string
}

interface Declared {
    tolerance_level: string
    investment_horizon: string
    assessed_at: string
}

interface SuitabilityCardProps {
    suitability: Suitability | null | undefined
    declared: Declared | null | undefined
    onStart: () => void
}

const LEVEL_COLOR: Record<string, string> = {
    Düşük: 'text-emerald-400 bg-emerald-500/10',
    Orta: 'text-amber-400 bg-amber-500/10',
    Yüksek: 'text-rose-400 bg-rose-500/10',
}

function Pill({ label, level }: { label: string; level: string | null | undefined }) {
    return (
        <div className="flex-1 rounded-xl bg-white/5 p-4">
            <p className="text-xs font-medium text-slate-400">{label}</p>
            <p
                className={`mt-2 inline-block rounded-full px-3 py-1 text-sm font-semibold ${
                    LEVEL_COLOR[level ?? ''] ?? 'bg-white/5 text-slate-500'
                }`}
            >
                {level ?? 'ölçülemedi'}
            </p>
        </div>
    )
}

export default function SuitabilityCard({
    suitability,
    declared,
    onStart,
}: SuitabilityCardProps) {
    const shell =
        'flex flex-col rounded-2xl border border-white/10 bg-slate-900/50 p-6 shadow-2xl backdrop-blur-xl'

    if (!declared) {
        return (
            <div className={shell}>
                <h3 className="text-base font-semibold text-white">
                    Uygunluk testini doldurun
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-400">
                    Portföyünüzün riskini ölçebiliyoruz, ama bu riskin sizin için ne ifade
                    ettiğini yalnızca siz söyleyebilirsiniz. Test, ölçülen seviyenin yanına
                    kendi beyanınızı koyuyor ve hangi ürün gruplarının size sunulabileceğini
                    belirliyor.
                </p>
                {/* Bu metin eskiden "bu bir uygunluk değerlendirmesi DEĞİLDİR"
                    diyordu ve v1 için doğruydu: o anket yalnızca tolerans
                    ölçüyordu. v2 bir uygunluk testi ve ürün grubu kararı
                    üretiyor -- eski cümle olduğu yerde bırakılsaydı ekran,
                    yaptığı şeyin tersini söylüyor olurdu. */}
                <p className="mt-2 text-xs leading-relaxed text-slate-500">
                    Sonuç yalnızca sizin beyanınıza dayanır ve yatırım tavsiyesi değildir.
                    Cevaplarınızı istediğiniz zaman güncelleyebilirsiniz.
                </p>
                <div className="mt-4">
                    <button
                        type="button"
                        onClick={onStart}
                        className="rounded-lg bg-brandBlue px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-600"
                    >
                        Teste başla
                    </button>
                </div>
            </div>
        )
    }

    return (
        <div className={shell}>
            <div className="mb-4 flex items-start justify-between gap-4">
                <h3 className="flex items-center gap-2 text-base font-semibold text-white">
                    Ölçüm ve beyanınız
                    <Term termKey="risk_score" />
                </h3>
                <button
                    type="button"
                    onClick={onStart}
                    className="shrink-0 text-xs font-medium text-brandBlue transition-colors hover:text-blue-400"
                >
                    Testi güncelle
                </button>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row">
                <Pill label="Ölçülen portföy riski" level={suitability?.measured_level} />
                <Pill label="Beyan ettiğiniz tolerans" level={suitability?.declared_tolerance} />
            </div>

            {suitability?.statement && (
                <p className="mt-4 text-sm leading-relaxed text-slate-200">
                    {suitability.statement}
                </p>
            )}

            <p className="mt-3 border-t border-white/10 pt-3 text-xs leading-relaxed text-slate-500">
                Yatırım vadeniz: {declared.investment_horizon}. Anketi{' '}
                {formatDate(declared.assessed_at)} tarihinde
                doldurdunuz.
            </p>
        </div>
    )
}
