// src/components/chat/widgets/PortfolioWidget.tsx
import { PortfolioWidgetPayload } from '../../../types/chat';
import { BASE_CURRENCY, formatMoney } from '../../../lib/money'

interface Props {
  payload: PortfolioWidgetPayload;
}

/**
 * PortfolioWidget Bileşeni
 * 
 * Durumsuz (stateless) bir şekilde, gelen payload üzerinden portföy
 * verilerini listeleyen ve toplam durumu gösteren widget.
 */
export default function PortfolioWidget({ payload }: Props) {
  // Yüzde formatlayıcı
  const formatPercent = (value: number) => {
    return new Intl.NumberFormat('tr-TR', {
      style: 'percent',
      minimumFractionDigits: 2,
      signDisplay: 'exceptZero'
    }).format(value);
  };

  const isProfit = payload.total_profit_loss >= 0;

  return (
    <div className="w-full max-w-[320px] md:max-w-md mt-2 rounded-xl overflow-hidden border border-white/10 bg-slate-900/50 backdrop-blur-xl text-white shadow-2xl shadow-sm flex flex-col font-sans">
      {/* Başlık ve Özet */}
      <div className="bg-slate-50 p-4 border-b border-slate-200 flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Mevcut Portföy Durumu</h4>
        <div className="flex items-end justify-between">
          <span className="text-2xl font-bold text-slate-900">{formatMoney(payload.total_value, payload.base_currency ?? BASE_CURRENCY)}</span>
          <div className={`flex flex-col items-end text-sm font-medium ${isProfit ? 'text-emerald-600' : 'text-rose-600'}`}>
            <span>{isProfit ? '+' : ''}{formatMoney(payload.total_profit_loss, payload.base_currency ?? BASE_CURRENCY)}</span>
          </div>
        </div>
      </div>

      {/* Pozisyonlar Tablosu */}
      <div className="p-0 overflow-x-auto">
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead className="bg-slate-50 text-slate-400 text-[11px] uppercase tracking-wider border-b border-white/10">
            <tr>
              <th className="px-3 py-2 font-semibold">Sembol</th>
              <th className="px-3 py-2 font-semibold text-right">Adet</th>
              <th className="px-3 py-2 font-semibold text-right">Maliyet</th>
              <th className="px-3 py-2 font-semibold text-right">Fiyat</th>
              <th className="px-3 py-2 font-semibold text-right">K/Z</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {payload.positions.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-slate-400 italic">
                  Aktif pozisyon bulunmuyor.
                </td>
              </tr>
            ) : (
              payload.positions.map((pos) => {
                const isPosProfit = pos.unrealized_pnl >= 0;
                return (
                  <tr key={pos.symbol} className="hover:bg-white/5 transition-colors text-[13px]">
                    <td className="px-3 py-2 font-semibold text-slate-900">{pos.symbol}</td>
                    <td className="px-3 py-2 text-right text-slate-600">{pos.quantity}</td>
                    <td className="px-3 py-2 text-right text-slate-600">{formatMoney(pos.avg_cost, pos.instrument_currency)}</td>
                    <td className="px-3 py-2 text-right font-medium text-white">{formatMoney(pos.last_price, pos.instrument_currency)}</td>
                    <td className={`px-3 py-2 text-right font-semibold ${isPosProfit ? 'text-emerald-600' : 'text-rose-600'}`}>
                      <div className="flex flex-col">
                        <span>{isPosProfit ? '+' : ''}{formatMoney(pos.unrealized_pnl, payload.base_currency ?? BASE_CURRENCY)}</span>
                        <span className="text-[10px] opacity-80 font-medium">{formatPercent(pos.unrealized_pnl_pct)}</span>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
