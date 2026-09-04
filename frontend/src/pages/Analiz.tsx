import { Outlet, useOutletContext } from 'react-router-dom'
import AnalizSubNav from '../components/analiz/AnalizSubNav'
import AnalysisSummaryBar from '../components/analiz/AnalysisSummaryBar'
import { useAnalysisData } from '../hooks/useAnalysisData'
import type { AnalysisData } from '../hooks/useAnalysisData'

/**
 * Analiz — ince kabuk sayfa.
 *
 * `Portföy Analizi` ve `Risk Analizi` ayrı navigasyon öğeleriydi ve ikisi de
 * aynı portföyü ölçüyordu: toplam değer, kâr/zarar, oynaklık ve max düşüş
 * ikisinde de vardı. Ayrı durdukları için birbirleriyle çeliştikleri
 * görünmüyordu. Tek çatı, tek veri çağrısı, tek dönem seçici.
 *
 * `/banking` ve `/investment` ile aynı desen: ortak üst bölüm burada, her
 * bölümün içeriği `pages/analiz/*` altındaki alt rotalarda.
 */
export default function Analiz() {
    const data = useAnalysisData()

    return (
        <div className="min-h-screen p-6 sm:p-8">
            <div className="mb-6">
                <h1 className="text-2xl font-bold tracking-tight text-white">Analiz</h1>
                <p className="mt-1 text-sm text-slate-400">
                    Portföyünüzün dağılımı, performansı ve ölçülen riski.
                </p>
            </div>

            <AnalysisSummaryBar
                analysis={data.analysis}
                risk={data.risk}
                lookback={data.lookback}
                onLookbackChange={data.setLookback}
            />

            <AnalizSubNav />

            {data.loading && (
                <div className="flex min-h-[30vh] items-center justify-center">
                    <div className="h-10 w-10 animate-spin rounded-full border-4 border-white/10 border-t-brandBlue" />
                </div>
            )}

            {!data.loading && data.error && (
                <div className="mb-6 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
                    {data.error}
                </div>
            )}

            {/* Hata olsa bile alt rota çizilir: iki uçtan biri döndüyse o
                sekmenin gösterecek verisi vardır ve saklamak, kullanıcıya
                olmayan bir kesinti bildirmek olurdu. */}
            {!data.loading && <Outlet context={data} />}
        </div>
    )
}

/** Alt sekmelerin ortak veriye eriştiği yer. */
export function useAnalysis(): AnalysisData {
    return useOutletContext<AnalysisData>()
}
