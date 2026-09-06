import { useCallback, useMemo, useState } from 'react'
import { apiClient } from '../../api/client'
import { formatWithBase } from '../../lib/money'
import { useMarketStream, useQuote } from '../../hooks/useMarketStream'
import { GRACE_SECONDS, useTradeFlow } from '../../hooks/useTradeFlow'

type TradeAction = 'Alış' | 'Satış'

interface TradeModalProps {
  symbol: string
  price: number
  /** The instrument's own currency. Without it this modal priced a dollar
   *  stock in lira — AAPL showed "₺314,88" for a $314.88 share. */
  currency?: string
  /** Alım için kullanılabilir nakit; %25/50/100 kısayolları bunu bölüyor. */
  availableCash?: number
  /** Satış için elde bulunan adet. */
  heldQuantity?: number
  /** Fon mu hisse mi. Limit emrinin ne sıklıkla kontrol edildiği buna bağlı:
   *  fonun gün içi fiyatı YOK, NAV günde bir yayımlanıyor. */
  assetKind?: 'stock' | 'fund' 
  onClose: () => void
}

/** Panelin varsayılan yatırım hesabı; backend tek demo hesabı bu numarayla tutar. */
const DEFAULT_ACCOUNT_ID = 'TR-DEMO-0001'

/** Tutar kısayolları: mevcut nakdin (ya da pozisyonun) yüzdesi. */
const SHORTCUTS = [25, 50, 100] as const

export default function TradeModal({
  symbol, price, currency = 'TRY', availableCash, heldQuantity,
  assetKind = 'stock', onClose,
}: TradeModalProps) {
  // The live quote, so the confirm screen and the ticker cannot disagree about
  // what you are about to pay. The price prop is only the opening value.
  const quote = useQuote(symbol)
  const { rates } = useMarketStream()
  // `??` DEĞİL: açılış fiyatı bilinmiyor olabilir ve `??` yalnızca
  // null/undefined yakalar -- NaN geçtiğinde ekrana "NaN" yazılırdı.
  const opening = Number.isFinite(price) ? price : undefined
  const livePrice = quote?.price ?? opening

  const [action, setAction] = useState<TradeAction>('Alış')
  const [quantity, setQuantity] = useState(1)
  const [limitEnabled, setLimitEnabled] = useState(false)
  const [limitPrice, setLimitPrice] = useState(opening ?? 0)
  const [message, setMessage] = useState('')

  const effectivePrice = limitEnabled ? limitPrice : livePrice
  const priceKnown = Number.isFinite(effectivePrice)
  const gross = priceKnown ? quantity * (effectivePrice as number) : null

  /** Emri hazırlar ve onaylar. Yalnızca mühlet dolduğunda ya da kullanıcı
   *  beklemeden onayladığında çağrılıyor. */
  const submit = useCallback(async () => {
    // İki adım: önce öneri hazırlanır (hiçbir emir iletilmez), sonra
    // onaylanır. Hazırlama KABUL'den sonra: her yarım yazılmış adet için
    // öneri üretmek, kimsenin dokunmadığı satırlarla dolu bir tablo bırakır.
    const me = await apiClient.getCurrentUser()
    const proposal = await apiClient.stageTransaction({
      user_id: me.id,
      transaction_type: action === 'Alış' ? 'BUY' : 'SELL',
      source_account_id: DEFAULT_ACCOUNT_ID,
      idempotency_key: `ui-${symbol}-${Date.now()}`,
      instrument: { symbol },
      quantity,
      order_type: limitEnabled ? 'LIMIT' : 'MARKET',
      limit_price: limitEnabled ? limitPrice : null,
      // Limit emri iptal edilene kadar geçerli (GTC). `DAY` olsaydı emir
      // seans sonunda sessizce düşerdi ve kullanıcı bunu hiçbir yerde
      // görmezdi -- bekleyen bir emrin kaybolması, verilmemiş sayılması
      // demek.
      time_in_force: limitEnabled ? 'GTC' : 'DAY',
      assumptions: [],
    })

    if (proposal.status !== 'PENDING_USER_CONFIRMATION') {
      // Backend'in gerekçesi kullanıcının görmesi gereken şey; yerine genel
      // bir hata yazmak reddin sebebini gizlerdi.
      throw new Error(
        proposal.blockers?.join(' ') || 'Bu emir doğrulanamadı, lütfen bilgileri kontrol edin.',
      )
    }

    const confirmed = await apiClient.confirmProposal(proposal.proposal_id)
    setMessage(confirmed.message ?? 'Emir onaylandı.')
  }, [action, symbol, quantity, limitEnabled, limitPrice])

  const flow = useTradeFlow({ onSubmit: submit })

  /** Kısayolun karşılığı: alımda nakdin yüzdesi kadar lot, satışta
   *  pozisyonun yüzdesi. Fiyat bilinmiyorsa kısayol gösterilmiyor --
   *  bölünemeyen bir tutardan adet üretmek uydurmak olurdu. */
  const shortcutFor = useCallback(
    (percent: number): number | null => {
      if (action === 'Satış') {
        if (!heldQuantity) return null
        return Math.max(1, Math.floor((heldQuantity * percent) / 100))
      }
      if (!availableCash || !priceKnown || !effectivePrice) return null
      return Math.max(1, Math.floor((availableCash * percent) / 100 / effectivePrice))
    },
    [action, heldQuantity, availableCash, priceKnown, effectivePrice],
  )

  const shortcuts = useMemo(
    () => SHORTCUTS.map((p) => ({ percent: p, lots: shortcutFor(p) })).filter((s) => s.lots),
    [shortcutFor],
  )

  const priceLabel = livePrice === undefined
    ? 'Fiyat bekleniyor…'
    : formatWithBase(livePrice, currency, rates)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-xl p-4">
      <div className="w-full max-w-sm rounded-[2.5rem] bg-slate-900/50 backdrop-blur-xl border border-white/10 p-6 shadow-2xl">
        {flow.stage === 'done' ? (
          <div className="flex flex-col items-center text-center gap-3 py-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/15">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6 text-emerald-400">
                <path d="M20 6 9 17l-5-5" />
              </svg>
            </div>
            <h3 className="font-bold text-white">Emriniz İletildi</h3>
            <p className="text-sm text-slate-400">{message}</p>
            <button
              onClick={onClose}
              className="mt-2 w-full rounded-xl bg-emerald-500 py-2.5 text-sm font-semibold text-white shadow-sm shadow-emerald-500/30 transition-colors hover:bg-emerald-600"
            >
              Kapat
            </button>
          </div>
        ) : (
          <>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Varlık</h3>
                <p className="text-lg font-bold text-white">{symbol}</p>
              </div>
              <button onClick={onClose} className="text-slate-400 transition-colors hover:text-slate-300" aria-label="Kapat">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p className="mb-4 text-2xl font-bold tabular-nums text-white">{priceLabel}</p>

            {/* ---- Adım 1: giriş ---- */}
            {flow.stage === 'entry' && (
              <>
                <div className="mb-4 flex gap-2">
                  {(['Alış', 'Satış'] as TradeAction[]).map((side) => (
                    <button
                      key={side}
                      onClick={() => setAction(side)}
                      className={`flex-1 rounded-xl py-2.5 text-sm font-semibold transition-colors ${
                        action === side
                          ? side === 'Alış'
                            ? 'bg-emerald-500 text-white shadow-sm shadow-emerald-500/30'
                            : 'bg-rose-500 text-white shadow-sm shadow-rose-500/30'
                          : 'bg-white/5 text-slate-400 hover:bg-white/10'
                      }`}
                    >
                      {side === 'Alış' ? 'AL' : 'SAT'}
                    </button>
                  ))}
                </div>

                <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  Adet
                </label>
                <input
                  type="number"
                  min={1}
                  value={quantity}
                  onChange={(e) => setQuantity(Math.max(1, Number(e.target.value) || 1))}
                  className="mb-2 w-full rounded-xl border border-white/10 bg-slate-800/60 px-3 py-2.5 text-sm tabular-nums text-white focus:border-brandBlue focus:outline-none"
                />

                {/* Kısayollar yalnızca hesaplanabildiğinde. Bölünemeyen bir
                    tutardan adet üretmek uydurmak olurdu. */}
                {shortcuts.length > 0 && (
                  <div className="mb-4 flex gap-2">
                    {shortcuts.map(({ percent, lots }) => (
                      <button
                        key={percent}
                        onClick={() => setQuantity(lots as number)}
                        className="flex-1 rounded-lg border border-white/10 bg-slate-800/60 py-1.5 text-xs font-semibold text-slate-300 transition hover:border-brandBlue/40 hover:text-white"
                      >
                        %{percent}
                      </button>
                    ))}
                  </div>
                )}

                <label className="mb-4 flex items-center gap-2 text-xs text-slate-400">
                  <input
                    type="checkbox"
                    checked={limitEnabled}
                    onChange={(e) => setLimitEnabled(e.target.checked)}
                  />
                  Limitli emir
                </label>
                {limitEnabled && (
                  <>
                    <input
                      type="number"
                      step={0.01}
                      value={limitPrice}
                      onChange={(e) => setLimitPrice(Number(e.target.value))}
                      className="mb-2 w-full rounded-xl border border-white/10 bg-slate-800/60 px-3 py-2.5 text-sm tabular-nums text-white focus:border-brandBlue focus:outline-none"
                    />
                    {/* Limit bir TETİKLEYİCİ, bir fiyatlama girdisi değil.
                        Bunu yazmamak, emrin dondugu sanılmasına yol açar --
                        özellikle fonda, fiyat günde bir kez oluştuğu için. */}
                    <p className="mb-4 text-[11px] leading-relaxed text-slate-400">
                      Emir hemen gerçekleşmez: fiyat bu seviyeye gelene kadar bekler
                      ve tutar bloke edilir.{' '}
                      {assetKind === 'fund'
                        ? 'Fon fiyatı günde bir kez açıklanır, emir günde bir kez kontrol edilir.'
                        : 'Piyasa açıkken dakikada bir kontrol edilir.'}{' '}
                      Dilediğiniz zaman Emir Geçmişi’nden iptal edebilirsiniz.
                    </p>
                  </>
                )}

                <button
                  onClick={flow.review}
                  disabled={!priceKnown}
                  className="w-full rounded-xl bg-brandBlue py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Devam
                </button>
              </>
            )}

            {/* ---- Adım 2: özet, kabul/ret, mühlet ---- */}
            {flow.stage !== 'entry' && (
              <TradeSummary
                action={action}
                quantity={quantity}
                gross={gross}
                currency={currency}
                rates={rates}
                flow={flow}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}

/**
 * Özet, kabul/ret ve mühlet.
 *
 * Adet yazmakla paranın hareket etmesi arasında hiçbir ekran yoktu; bu o
 * ekran. Yetkilendiren şey "Kabul et" tıklaması, geri sayım ondan sonra
 * gelen bir mühlet.
 */
function TradeSummary({
  action, quantity, gross, currency, rates, flow,
}: {
  action: TradeAction
  quantity: number
  gross: number | null
  currency: string
  rates: Record<string, number>
  flow: ReturnType<typeof useTradeFlow>
}) {
  const money = (value: number | null) =>
    value === null ? '—' : formatWithBase(value, currency, rates)

  return (
    <>
      <dl className="mb-4 flex flex-col gap-1.5 rounded-2xl border border-white/10 bg-slate-800/40 p-4">
        <Line label="İşlem" value={action === 'Alış' ? 'Alış' : 'Satış'} />
        <Line label="Adet" value={String(quantity)} />
        <Line label="Tutar" value={money(gross)} />
      </dl>

      {flow.stage === 'error' && (
        <p className="mb-3 text-sm text-rose-400">{flow.error}</p>
      )}

      {flow.stage === 'review' || flow.stage === 'error' ? (
        <div className="flex gap-2">
          <button
            onClick={flow.reject}
            className="flex-1 rounded-xl border border-white/10 bg-white/5 py-2.5 text-sm font-semibold text-slate-300 transition-colors hover:bg-white/10"
          >
            Reddet
          </button>
          <button
            onClick={flow.accept}
            className="flex-1 rounded-xl bg-emerald-500 py-2.5 text-sm font-semibold text-white shadow-sm shadow-emerald-500/30 transition-colors hover:bg-emerald-600"
          >
            Kabul et
          </button>
        </div>
      ) : flow.stage === 'countdown' ? (
        <div className="flex flex-col gap-2">
          <button
            onClick={flow.submitNow}
            className="w-full rounded-xl bg-emerald-500 py-2.5 text-sm font-semibold text-white shadow-sm shadow-emerald-500/30 transition-colors hover:bg-emerald-600"
          >
            Onayla ({flow.remaining} sn)
          </button>
          <div className="flex gap-2">
            <button
              onClick={flow.edit}
              className="flex-1 rounded-xl border border-white/10 bg-white/5 py-2 text-xs font-semibold text-slate-300 transition-colors hover:bg-white/10"
            >
              İşlemi düzenle
            </button>
            <button
              onClick={flow.cancel}
              className="flex-1 rounded-xl border border-rose-500/25 bg-rose-500/10 py-2 text-xs font-semibold text-rose-300 transition-colors hover:bg-rose-500/20"
            >
              İptal
            </button>
          </div>
          <p className="text-center text-[11px] text-slate-500">
            {flow.remaining} saniye sonra iletilecek. Bu süre içinde
            düzenleyebilir ya da iptal edebilirsiniz.
          </p>
        </div>
      ) : (
        <p className="text-center text-sm text-slate-400">İletiliyor…</p>
      )}
    </>
  )
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-xs text-slate-400">{label}</dt>
      <dd className="text-sm font-semibold tabular-nums text-white">{value}</dd>
    </div>
  )
}

export { GRACE_SECONDS }
