import RiskHistoryPanel from '../../components/risk/RiskHistoryPanel'
import SimulationPanel from '../../components/risk/SimulationPanel'
import { useAnalysis } from '../Analiz'

/**
 * Analiz > Senaryo & Geçmiş — değiştirsem ne olur, nereden geldim.
 *
 * İkisi de zaman üzerine sorular ve Risk sekmesinin altında, metrik
 * kartlarının arasına sıkışmış duruyorlardı. Burada kendi başlarına
 * duruyorlar; Risk sekmesi de "şu an ne" sorusuna odaklanıyor.
 */
export default function Senaryo() {
    const { lookback } = useAnalysis()

    return (
        <div className="flex flex-col gap-6">
            <SimulationPanel lookback={lookback} />
            <RiskHistoryPanel />
        </div>
    )
}
