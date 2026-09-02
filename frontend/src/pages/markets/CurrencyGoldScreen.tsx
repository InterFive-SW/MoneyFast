import { useMemo } from 'react'
import { useInstruments } from '../../hooks/useInstruments'
import MarketInstrumentsTable from '../../components/markets/MarketInstrumentsTable'

/**
 * Döviz ve altın.
 *
 * Proje dokümanı analiz edilecek varlıkları adıyla sayıyor: "Kullanıcının
 * hisse, altın ve döviz varlıkları analiz edilir." Üçünden ikisinin
 * enstrümanları sistemde vardı, fiyatlanıyordu ve alınıp satılabiliyordu ama
 * hiçbir ekranda GÖRÜNMÜYORDU: Piyasalar altında Hisseler, Fonlar, Endeksler
 * ve Sektörler vardı, dolayısıyla sembolü ezbere bilmeyen biri altına ya da
 * dolara hiçbir yerden ulaşamıyordu.
 *
 * İki ayrı çağrı, çünkü sunucudaki `market` süzgeci tek bir borsa alıyor ve
 * bunlar iki ayrı borsa (FX ve COMEX). Toplam beş enstrüman -- birleştirmek
 * için sunucuya yeni bir süzgeç eklemek, dört satır uğruna sözleşme
 * genişletmek olurdu.
 */
export default function CurrencyGoldScreen() {
  const fx = useInstruments(50, 'FX')
  const gold = useInstruments(50, 'COMEX')

  const instruments = useMemo(
    // Altın önce: dokümanın sıralaması da öyle ve tek satır olduğu için
    // dövizin arasında kaybolmuyor.
    () => [...gold.instruments, ...fx.instruments],
    [gold.instruments, fx.instruments],
  )

  if (fx.loading || gold.loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500" />
      </div>
    )
  }

  return (
    <div>
      <p className="mb-6 rounded-lg border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-400">
        Ons altın ve döviz pariteleri. Fiyatlar hisselerle aynı akıştan gelir ve
        aynı gecikmeyi taşır; kendi para birimlerinde gösterilir.
      </p>

      {instruments.length === 0 ? (
        /* Boşsa boş görünür. İzleme listesindeki kuralın aynısı: veri
           yokluğunu doldurmak, olmayan bir enstrümanı varmış gibi
           göstermek olurdu. */
        <p className="rounded-lg border border-white/10 bg-slate-900/50 px-4 py-8 text-center text-sm text-slate-400">
          Döviz ve altın verisi şu anda yüklenemedi.
        </p>
      ) : (
        <MarketInstrumentsTable
          instruments={instruments}
          columnSet="getiri"
          showMarketTabs={false}
        />
      )}
    </div>
  )
}
