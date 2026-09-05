import { useState } from 'react'
import FundsTable from '../../components/markets/FundsTable'
import FundFilterPanel, {
  EMPTY_FUND_FILTERS,
  type FundFilters,
} from '../../components/markets/FundFilterPanel'
import { useFunds } from '../../hooks/useFunds'

/**
 * Fonlar ekranı — TEFAS.
 *
 * `MOCK_FUNDS` ve "Örnek veri" uyarısı KALKTI: arkasında artık gerçek veri
 * var (bkz. `docs/TEFAS_INTEGRATION.md`).
 *
 * Karşılaştırma grafiği de kalktı: tamamen sentetik bir seriden
 * (`comparisonSeries.ts`, seed'li rastgele yürüyüş) besleniyordu. Gerçek NAV
 * serisi fon başına ayrı bir istek ve bütçeyle doluyor; tek tek fonun kendi
 * grafiği detay sayfasında.
 */
export default function FundsScreen() {
  const [filters, setFilters] = useState<FundFilters>(EMPTY_FUND_FILTERS)
  const { funds, founders, umbrellas, loading, error, empty } = useFunds(filters)

  return (
    <div>
      <FundFilterPanel
        filters={filters}
        onChange={setFilters}
        founders={founders}
        umbrellas={umbrellas}
      />

      {loading && <p className="py-10 text-center text-sm text-slate-400">Fonlar yükleniyor…</p>}

      {/* Ulaşılamayan bir uç, ölçülmüş bir boşluk DEĞİL. */}
      {!loading && error && <p className="py-10 text-center text-sm text-rose-400">{error}</p>}

      {/* Hiç fon yazılmamış olmak ile süzgece uyan fon olmaması ayrı şeyler. */}
      {empty && (
        <p className="py-10 text-center text-sm text-slate-400">
          Fon verisi henüz alınmadı. Toplayıcı günde bir kez çalışıyor.
        </p>
      )}

      {!loading && !error && !empty && (
        <div className="mb-6">
          <FundsTable funds={funds} />
        </div>
      )}
    </div>
  )
}
