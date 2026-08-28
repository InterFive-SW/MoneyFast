import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { apiClient, type ApiCard, type PortfolioAccount } from '../api/client'
import { useMarketStream } from '../hooks/useMarketStream'
import { BASE_CURRENCY, convert, formatMoney } from '../lib/money'

/** Hesap türü etiketleri; ekranda görünen ad sunumun işi, kaydın değil. */
const ACCOUNT_LABELS: Record<string, string> = {
  vadesiz: 'Vadesiz Hesap',
  vadeli: 'Vadeli Hesap',
  birikim: 'Birikim Hesabı',
  yatirim: 'Yatırım Hesabı',
}

/**
 * Ana sayfa: bir bankacılık uygulaması gibi bakiyelerle açılır.
 *
 * Uygulamayı ayıran şey yatırım sohbeti; ama bir bankacılık uygulamasını açan
 * kişi önce parasının nerede olduğunu görmek ister. Sohbet ve yatırım ekranları
 * bir tık uzakta duruyor, ilk gördüğü şey olarak değil.
 *
 * Toplam, para birimleri ÇEVRİLEREK hesaplanır. Kuru bilinmeyen hesap toplama
 * katılmaz ve altta adıyla söylenir; 1.0 varsaymak uydurma bir toplam üretir.
 */
/**
 * Ana sayfadaki hızlı işlemler.
 *
 * Fatura ödeme yalnızca Banka İşlemleri'nin içinden ulaşılabiliyordu; en çok
 * yapılan işlerden biri için üç tık fazlaydı.
 */
const ACTIONS = [
  { to: '/banking/transfer', icon: '↗', label: 'Para Gönder',
    hint: 'Kendi hesaplarınız veya başka bir IBAN' },
  { to: '/banking?pay=1', icon: '🧾', label: 'Ödeme Yap',
    hint: 'Abone numarasıyla fatura sorgulayın' },
  { to: '/banking/cards', icon: '💳', label: 'Kartlarım',
    hint: 'Limit, borç ve kart ayarları' },
  { to: '/banking/transfer', icon: '📈', label: 'Yatırıma Aktar',
    hint: 'İşlem yapmak için nakit yükleyin' },
]

export default function Home() {
  const [accounts, setAccounts] = useState<PortfolioAccount[]>([])
  const [cards, setCards] = useState<ApiCard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { rates } = useMarketStream()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [accountRows, cardRows] = await Promise.all([
        apiClient.getAllAccounts(),
        // A customer with no card is not an error; the strip shows its empty
        // state rather than the page showing a failure.
        apiClient.getCards().catch(() => [] as ApiCard[]),
      ])
      setAccounts(accountRows)
      setCards(cardRows)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Hesaplar alınamadı.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const converted = accounts.map((account) => ({
    account,
    inBase: convert(account.balance, account.currency_code, BASE_CURRENCY, rates),
  }))
  const total = converted.reduce((sum, row) => sum + (row.inBase ?? 0), 0)
  const unconvertible = converted
    .filter((row) => row.inBase === null)
    .map((row) => row.account.currency_code)

  const banking = accounts.filter((a) => !a.is_investment)
  const investment = accounts.find((a) => a.is_investment)

  if (loading) {
    return <p className="p-6 text-sm text-slate-400">Yükleniyor…</p>
  }

  return (
    <div className="space-y-6 p-6">
      <section className="rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 to-slate-950 p-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Toplam Varlık
        </p>
        <p className="mt-2 text-3xl font-bold tabular-nums text-white">
          {formatMoney(total)}
        </p>
        {unconvertible.length > 0 && (
          <p className="mt-2 text-xs text-amber-400">
            {unconvertible.join(', ')} kuru bilinmediği için toplama dahil edilmedi.
          </p>
        )}
        {error && <p className="mt-2 text-sm text-rose-400">{error}</p>}
      </section>

      <section>
        <h2 className="text-sm font-semibold text-white">Hızlı İşlemler</h2>
        <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {ACTIONS.map((action) => (
            <Link
              key={action.to}
              to={action.to}
              className="group rounded-xl border border-slate-800 bg-slate-900 p-4 transition hover:border-brandBlue/60 hover:bg-slate-800/60"
            >
              <span
                aria-hidden
                className="flex h-9 w-9 items-center justify-center rounded-lg bg-brandBlue/15 text-base"
              >
                {action.icon}
              </span>
              <p className="mt-3 text-sm font-semibold text-white">{action.label}</p>
              <p className="mt-0.5 text-xs leading-snug text-slate-400">{action.hint}</p>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">Hesaplarım</h2>
          <Link to="/banking/accounts" className="text-xs text-brandBlue hover:underline">
            Tümü
          </Link>
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {banking.map((account) => (
            <Link
              key={account.id}
              to="/banking/accounts"
              className="rounded-xl border border-slate-800 bg-slate-900 p-4 transition hover:border-slate-700"
            >
              <p className="text-sm font-medium text-white">
                {ACCOUNT_LABELS[account.account_type] ?? 'Hesap'}
              </p>
              <p className="mt-1 font-mono text-xs text-slate-500">
                {account.iban ?? account.account_number}
              </p>
              <p className="mt-3 text-lg font-semibold tabular-nums text-white">
                {formatMoney(account.balance, account.currency_code)}
              </p>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">Kartlarım</h2>
          <Link to="/banking/cards" className="text-xs text-brandBlue hover:underline">
            Tüm kartlar
          </Link>
        </div>

        {cards.length === 0 ? (
          <p className="mt-3 rounded-xl border border-slate-800 bg-slate-900 p-5 text-sm text-slate-400">
            Henüz kartınız yok.
          </p>
        ) : (
          /* Yatay kaydırma, `scroll-snap` ile. Karusel kütüphanesi yok:
             touchpad, dokunmatik ekran ve klavye üçü de kendiliğinden
             çalışıyor, ok tuşlarıyla taklit edilmesi gerekmiyor. */
          <div
            className="mt-3 flex snap-x snap-mandatory gap-4 overflow-x-auto pb-2"
            role="list"
            aria-label="Kartlarım"
          >
            {cards.map((card) => (
              <Link
                key={card.id}
                to="/banking/cards"
                role="listitem"
                className="w-72 shrink-0 snap-start rounded-2xl border border-slate-700 bg-gradient-to-br from-slate-800 to-slate-950 p-5 transition hover:border-brandBlue/60"
              >
                <div className="flex items-start justify-between">
                  <p className="text-sm font-semibold text-white">{card.name}</p>
                  <span className="text-[10px] uppercase tracking-wide text-slate-400">
                    {card.brand}
                  </span>
                </div>
                <p className="mt-4 font-mono text-sm text-slate-300">{card.card_number}</p>
                <div className="mt-4 flex items-end justify-between">
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-slate-500">Borç</p>
                    <p className="text-sm font-semibold tabular-nums text-white">
                      {formatMoney(card.current_debt)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-[10px] uppercase tracking-wide text-slate-500">
                      Kullanılabilir
                    </p>
                    <p className="text-sm font-semibold tabular-nums text-emerald-400">
                      {formatMoney(card.available_limit)}
                    </p>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>

      {investment && (
        <section>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white">Yatırım</h2>
            <Link to="/portfolio" className="text-xs text-brandBlue hover:underline">
              Portföyüm
            </Link>
          </div>
          <div className="mt-3 rounded-xl border border-slate-800 bg-slate-900 p-4">
            <p className="text-sm font-medium text-white">Yatırım Hesabı</p>
            <p className="mt-1 text-xs text-slate-500">
              İşlem yapmak için kullanılabilir nakit
            </p>
            <p className="mt-3 text-lg font-semibold tabular-nums text-white">
              {formatMoney(investment.balance, investment.currency_code)}
            </p>
            <Link
              to="/banking/transfer"
              className="mt-3 inline-block text-xs text-brandBlue hover:underline"
            >
              Yatırım hesabına para aktar →
            </Link>
          </div>
        </section>
      )}

      <section className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <h2 className="text-sm font-semibold text-white">MoneyFast Asistan</h2>
        <p className="mt-1 text-xs text-slate-400">
          Piyasayı sorun, portföyünüzü konuşun, işlem hazırlatın — onay her
          zaman sizde.
        </p>
        <Link
          to="/chat"
          className="mt-3 inline-block rounded-lg bg-brandBlue px-4 py-2 text-sm font-semibold text-white"
        >
          Sohbete Başla
        </Link>
      </section>
    </div>
  )
}
