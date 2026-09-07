"""Kullanıcının kendi hedefindeki sapmanın lot karşılığı.

`allocation.py`'den AYRI, çünkü orası fiyat ve kur bilmiyor ve bilmemeli:
kova aritmetiği saf, lot aritmetiği ise fiyat, kur, yuvarlama ve satılabilir
miktar içeriyor.

**Bu bir tavsiye değil ve öyle olmadığı ekranda da yazıyor.** Sistem hedefi
KOYMUYOR; kullanıcının kendi girdiği hedefle ölçülen ağırlık arasındaki farkı
lota çeviriyor. `drift()` zaten "hedefe ulaşmak için kaç lira" diyordu; buradaki
tek fark, o lirayı o kovadaki MEVCUT pozisyonlara bölmek.

Hangi enstrümanın alınacağı SEÇİLMİYOR. Seçmek bir tavsiye olurdu; kovadaki
mevcut ağırlıklara orantılı dağıtmak aritmetiktir. Kovada pozisyon yoksa emir
de üretilmiyor -- "hangi enstrümanla dolduracağınız sizin seçiminiz".
"""

from __future__ import annotations

import math
from typing import Any, Optional, Sequence

from . import allocation

#: Ekranda kalıcı olarak duran etiket. Sunucudan geliyor ki arayüzde ikinci
#: kez yazılmasın: iki kopyadan biri değişip diğeri kalabilirdi.
DISCLAIMER_TR = (
    "Bu liste yatırım tavsiyesi değildir; kendi belirlediğiniz hedefin "
    "aritmetik karşılığıdır."
)

BUY = "BUY"
SELL = "SELL"

#: Fon adetleri kesirli olabiliyor (`Numeric(19,6)`), hisse adetleri değil.
FUND_QUANTITY_DIGITS = 6


def _tr_amount(value: float) -> str:
    """Türkçe sayı biçimi: ondalık virgül, binlik nokta.

    Tek yerde: cümle Türkçe, gerekçe İngilizce biçimliyken aynı ekranda iki
    ayrı ondalık ayracı görünüyordu.
    """
    text = f"{value:,.2f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _floor_quantity(raw: float, is_fund: bool) -> float:
    """Adet AŞAĞI yuvarlanır, en yakına değil.

    Yukarı yuvarlamak kullanıcının kendi hedefini aşar ve satışta elde
    olmayan adedi satmaya çalışır. Aşağı yuvarlamanın bıraktığı fark
    `residual_base` olarak her satırda yazılı -- saklanan bir artık,
    görünmeyen bir artıktan iyidir.
    """
    if is_fund:
        factor = 10 ** FUND_QUANTITY_DIGITS
        return math.floor(raw * factor) / factor
    return float(math.floor(raw))


def plan(
    drift_rows: Sequence[dict[str, Any]],
    positions: Sequence[dict[str, Any]],
    rates: dict[str, float],
    base_currency: str,
    blocked_cash: float = 0.0,
    available_cash: float = 0.0,
) -> dict[str, Any]:
    """Sapmayı satır satır emir karşılığına çevirir.

    `positions` her biri en az `symbol`, `bucket`, `quantity`, `price`,
    `currency` ve `value_base` taşıyan sözlükler. Değerleme çağırana bırakılmış
    -- `ai_service.holding_value` tek uygulama ve onu burada tekrarlamak iki
    farklı portföy değeri demek olurdu.

    Dönen `rows` emir üretilebilen satırlar, `unresolved` ise üretilemeyenler
    ve HER BİRİ NEDENİNİ söylüyor. Sessizce atlanmış bir kova, kullanıcının
    hedefine ulaşamamasının sebebini görünmez yapardı.
    """
    by_bucket: dict[str, list[dict[str, Any]]] = {}
    for position in positions:
        by_bucket.setdefault(position.get("bucket") or allocation.OTHER, []).append(
            position
        )

    rows: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    residual_total = 0.0
    buy_total = 0.0

    for drift_row in drift_rows:
        bucket = drift_row.get("bucket")
        gap_amount = drift_row.get("gap_amount")
        label = drift_row.get("label") or bucket
        if gap_amount is None or bucket == allocation.OTHER:
            continue

        if bucket == allocation.CASH:
            # Nakit için emir YOK: nakit diğer emirlerin SONUCU olarak
            # değişiyor. Ayrıca bir "nakit al" emri üretmek, alınacak bir
            # enstrüman uydurmak olurdu.
            if abs(gap_amount) >= 0.01:
                unresolved.append({
                    "bucket": bucket, "label": label,
                    "gap_amount": gap_amount,
                    "reason": (
                        "Nakit, diğer emirlerin sonucunda değişir; bunun için "
                        "ayrı bir emir üretilmez."
                    ),
                })
            continue

        holdings = by_bucket.get(bucket) or []
        if not holdings:
            unresolved.append({
                "bucket": bucket, "label": label, "gap_amount": gap_amount,
                "reason": (
                    f"{label} kovasında pozisyonunuz yok; hangi enstrümanla "
                    "dolduracağınız sizin seçiminiz."
                ),
            })
            continue

        bucket_value = sum(float(h.get("value_base") or 0.0) for h in holdings)
        if bucket_value <= 0:
            unresolved.append({
                "bucket": bucket, "label": label, "gap_amount": gap_amount,
                "reason": f"{label} kovasının değeri ölçülemedi.",
            })
            continue

        side = SELL if gap_amount > 0 else BUY
        for holding in holdings:
            share = float(holding.get("value_base") or 0.0) / bucket_value
            # Kova farkı MEVCUT ağırlıklara orantılı dağıtılıyor. Hangi
            # enstrümanın satılacağını SEÇMEK bir tavsiye olurdu.
            amount_base = abs(gap_amount) * share
            row = _order_row(holding, side, amount_base, rates, base_currency)
            if row.get("reason"):
                unresolved.append({
                    "bucket": bucket, "label": label,
                    "symbol": holding.get("symbol"),
                    "gap_amount": round(amount_base, 2),
                    "reason": row["reason"],
                })
                continue
            row.update({"bucket": bucket, "label": label})
            residual_total += row["residual_base"]
            if side == BUY:
                buy_total += row["amount_base"]
            rows.append(row)

    usable_cash = round(available_cash - blocked_cash, 2)
    warning = None
    if buy_total > usable_cash:
        # Emirler yine listeleniyor: `stage` kendi bakiye kapısını zaten
        # uyguluyor ve listeyi gizlemek, kullanıcıya neyin eksik olduğunu
        # söylememek olurdu.
        warning = (
            f"Alış toplamı {_tr_amount(buy_total)} {base_currency}, "
            f"kullanılabilir nakit {_tr_amount(usable_cash)} {base_currency}. "
            "Bloke tutar düşülmüştür."
        )

    return {
        "disclaimer": DISCLAIMER_TR,
        # Sohbete GİDEN şey bu, satırlar değil. Gerekçe: ekranda duran liste
        # kullanıcının kendi koyduğu hedeften çıkıyor ve onayı kendi
        # tıklaması veriyor; aynı listeyi sohbette adet ve yönle yeniden
        # basmak, o nedensellik zincirini kopardığı için dışarıdan bakan biri
        # için bir tavsiyeden ayırt edilemez hâle geliyor. Ölçüldü: model
        # satırları bir alım-satım tablosuna çevirdi.
        "summary": _summary(rows, unresolved),
        "rows": rows,
        "unresolved": unresolved,
        "rounding_residual_base": round(residual_total, 2),
        "buy_total_base": round(buy_total, 2),
        "usable_cash_base": usable_cash,
        "blocked_cash_base": round(blocked_cash, 2),
        "warning": warning,
    }


def _summary(
    rows: Sequence[dict[str, Any]], unresolved: Sequence[dict[str, Any]]
) -> str:
    """Listenin ŞEKLİNİ anlatan cümle; satırların kendisini değil.

    Sohbet bu cümleyi aktarıyor ve emirler ekranda kalıyor. "Kaç satır var,
    hangi kovalarda, kaçı neden üretilemedi" sorusunun cevabı burada; "ne
    kadar sat" sorusununki ekranda ve orada kullanıcının kendi tıklaması
    onaylıyor.
    """
    if not rows and not unresolved:
        return "Hedefinizle ölçülen ağırlıklar arasında emre dönüşen bir fark yok."

    parts: list[str] = []
    if rows:
        buckets = sorted({row["label"] for row in rows})
        sells = sum(1 for row in rows if row["side"] == SELL)
        buys = len(rows) - sells
        shape = []
        if sells:
            shape.append(f"{sells} satış")
        if buys:
            shape.append(f"{buys} alış")
        parts.append(
            f"Dengeleme ekranında {' ve '.join(shape)} satırı var "
            f"({', '.join(buckets)})."
        )
    if unresolved:
        parts.append(
            f"{len(unresolved)} kova için emir üretilemedi ve her birinin "
            "nedeni listede yazılı."
        )
    return " ".join(parts)


def _order_row(
    holding: dict[str, Any],
    side: str,
    amount_base: float,
    rates: dict[str, float],
    base_currency: str,
) -> dict[str, Any]:
    """Bir pozisyon için emir satırı ya da neden üretilemediği."""
    symbol = holding.get("symbol")
    price = holding.get("price")
    currency = (holding.get("currency") or base_currency).upper()

    if not price or price <= 0:
        return {"reason": f"{symbol} için güncel fiyat yok."}

    rate = 1.0 if currency == base_currency.upper() else rates.get(currency)
    if not rate:
        # 1.0 VARSAYILMIYOR: bu depoda bir kez ölçüldü, 15.098 TL'lik bir
        # alım 315 TL'ye yapılıyordu.
        return {
            "reason": (
                f"{symbol} {currency} cinsinden fiyatlanıyor ve kuru "
                "okunamadı."
            )
        }

    is_fund = (holding.get("asset_kind") or "").lower() == "fund"
    raw = amount_base / (price * rate)
    quantity = _floor_quantity(raw, is_fund)

    if side == SELL:
        held = float(holding.get("quantity") or 0.0)
        # Elde olmayanı satmaya çalışmak `stage`in blokerine düşerdi; oraya
        # hiç gitmeden burada kesiliyor.
        quantity = min(quantity, held)

    if quantity <= 0:
        return {
            "reason": (
                f"{symbol} için hedef farkı bir birimden küçük "
                f"({_tr_amount(amount_base)} {base_currency}, birim fiyat "
                f"{_tr_amount(price)} {currency})."
            )
        }

    executed_base = quantity * price * rate
    return {
        "symbol": symbol,
        "name": holding.get("name"),
        "side": side,
        "quantity": quantity,
        "price": price,
        "currency": currency,
        "amount_base": round(executed_base, 2),
        # Yuvarlamadan artan fark. Saklanmıyor, YAZILIYOR: hedefe tam
        # ulaşılamadığını söylemek, ulaşılmış gibi göstermekten iyidir.
        "residual_base": round(amount_base - executed_base, 2),
        "statement": _row_statement(
            holding, side, quantity, executed_base, base_currency
        ),
    }


def _row_statement(
    holding: dict[str, Any],
    side: str,
    quantity: float,
    amount_base: float,
    base_currency: str,
) -> str:
    """Satırın Türkçe karşılığı, KODDA kurulu.

    "almalısınız" yok, "karşılığı" var: cümle kullanıcının kendi hedefinin
    aritmetiğini anlatıyor, ne yapması gerektiğini değil.
    """
    action = "satışın" if side == SELL else "alışın"
    amount = _tr_amount(amount_base)
    unit = f"{quantity:g}"
    return (
        f"{holding.get('symbol')} için {unit} adet {action} karşılığı "
        f"{amount} {base_currency}."
    )
