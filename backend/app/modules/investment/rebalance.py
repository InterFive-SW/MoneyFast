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

from sqlalchemy.orm import Session

from . import allocation
from .models import RiskBandTarget

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


# ── Gerekçe: bir satırı listeye sokan sayı ──────────────────────────────────
#
# **Sayısı olmayan satır listeye girmiyor.** Bu, kaldırılan yasakların yerine
# konan birinci kontrol: öneri hâlâ bir ölçüme dayanmak zorunda. Boş bir
# gerekçe alanıyla öneri sunmak, gerekçeyi kullanıcının uydurmasına bırakmak
# olurdu -- ve bir tavsiyeyi bir ölçüm raporundan ayıran tek şey bu.

RISK_CONTRIBUTION = "RISK_CONTRIBUTION"
CONCENTRATION = "CONCENTRATION"
VALUATION = "VALUATION"
PROFITABILITY = "PROFITABILITY"
LEVERAGE = "LEVERAGE"
NEWS = "NEWS"

#: Tek pozisyon ağırlığı bu oranı aşarsa gerekçe olarak yazılıyor. `profile`
#: yoğunlaşmayı HHI ile ölçüyor; bu ondan ayrı ve daha dar bir soru: TEK bir
#: satırın kendi payı. Eşik `HHI_CEILING`in karekökü civarı -- iki eşit
#: pozisyonun her birinin payı.
CONCENTRATION_FLOOR = 0.20

#: Ölçülen katkı bu payın altındaysa gerekçe olarak yazılmıyor: yüzde birlik
#: bir katkı, satışı açıklayan bir sayı değil.
CONTRIBUTION_FLOOR = 0.05


def _pct(value: float) -> str:
    """Yüzde, İŞARETİYLE.

    Mutlak değer ALMIYOR ve bu bir kez ölçülerek düzeltildi: özkaynak
    kârlılığı -0,3521 olan bir şirket "Özkaynak kârlılığı %35,2" diye
    yazılıyordu -- zarar eden bir şirketi kâr ediyor gibi göstermek, gerekçe
    olarak sunulan sayının tam tersini söylemek demek.

    İşareti cümleye bırakan tek yer risk katkısı ve orası onu KELİMEYLE
    söylüyor ("üretiyor" / "azaltıyor"), bu yüzden oraya mutlak değer ayrıca
    geçiliyor.
    """
    # İşaret yüzde işaretinin ÖNÜNDE: Türkçede "-%35,2" yazılır, "%-35,2"
    # değil, ve ikincisi ekranda bir dizgi hatası gibi okunuyor.
    sign = "-" if value < 0 else ""
    return f"{sign}%{abs(value) * 100:.1f}".replace(".", ",")


def _num(value: float) -> str:
    return f"{value:,.2f}".replace(",", "~").replace(".", ",").replace("~", ".")


def rationale_for(
    side: str,
    contribution: Optional[dict[str, Any]] = None,
    fundamentals: Optional[dict[str, Any]] = None,
    news: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Bir adayı listeye sokan ölçümler ve her birinin cümlesi.

    Üç girdi, üçü de ölçüm: portföyün kendi getirilerinden hesaplanan risk
    katkısı, sağlayıcıdan gelen temel veriler, ve haber okuması. Hiçbiri
    yoksa dönen liste BOŞ ve çağıran o enstrümanı listeye almıyor.

    **Satış tarafında birincil kriter risk katkısı**, ağırlık değil: riski
    düşürmek isteyen için en büyük pozisyon değil, portföy oynaklığının en
    büyük payını üreten pozisyon önemli. İkisi aynı şey değil ve aradaki fark
    `returns.risk_contributions()` docstring'inde ölçülmüş.

    Cümleler burada kuruluyor, modelde değil: her cümle koşullu, sayısını
    içinde taşıyor ve "ucuz", "pahalı", "cazip" gibi bir niteleme
    kullanmıyor -- bir orana iyi ya da kötü demek, o oranın ne olduğunu
    söylemekten farklı bir iddiadır.
    """
    out: list[dict[str, Any]] = []

    if contribution:
        share = contribution.get("contribution")
        weight = contribution.get("weight")
        if share is not None and abs(share) >= CONTRIBUTION_FLOOR:
            out.append({
                "kind": RISK_CONTRIBUTION,
                "value": round(float(share), 4),
                # Yön KELİMEYLE, işaretle değil; bu yüzden sayı mutlak
                # geçiyor. "%-8,4 üretiyor" okunabilir bir cümle değil.
                "text": (
                    f"Portföy oynaklığının {_pct(abs(float(share)))}'lik "
                    "kısmını bu pozisyon üretiyor."
                    if share > 0
                    else
                    f"Bu pozisyon portföy oynaklığını {_pct(abs(float(share)))} "
                    "azaltıyor."
                ),
            })
        if weight is not None and float(weight) >= CONCENTRATION_FLOOR:
            out.append({
                "kind": CONCENTRATION,
                "value": round(float(weight), 4),
                "text": f"Tek pozisyon ağırlığı {_pct(float(weight))}.",
            })

    data = fundamentals or {}
    pe_ratio = data.get("pe_ratio")
    if pe_ratio is not None:
        out.append({
            "kind": VALUATION,
            "value": round(float(pe_ratio), 2),
            # "Ucuz" ya da "pahalı" DEĞİL: oranın kendisi. Nitelemek, bir
            # fiyat görüşü beyan etmek olurdu.
            "text": f"Fiyat/kazanç oranı {_num(float(pe_ratio))}.",
        })
    roe = data.get("return_on_equity")
    if roe is not None:
        out.append({
            "kind": PROFITABILITY,
            "value": round(float(roe), 4),
            "text": f"Özkaynak kârlılığı {_pct(float(roe))}.",
        })
    debt = data.get("debt_to_equity")
    if debt is not None:
        out.append({
            "kind": LEVERAGE,
            # Sağlayıcı bunu YÜZDE olarak veriyor (200 = 2 kat); cümlede kat
            # olarak yazmak, aynı sayıyı yüz kat küçültmek olurdu.
            "value": round(float(debt), 2),
            "text": f"Borç/özkaynak oranı {_num(float(debt))}.",
        })

    if news and news.get("mechanism"):
        out.append({
            "kind": NEWS,
            # Haber bir SAYI değil; `value` yok ve uydurulmuyor.
            "value": None,
            "text": str(news["mechanism"]),
        })

    return out


def _rank_key(side: str, contribution: Optional[dict[str, Any]]) -> tuple:
    """Aday sıralaması. Ölçülemeyen aday en sona.

    Satışta en yüksek risk katkısı önce: kova farkını kapatmak için satılacak
    ilk şey, oynaklığın en büyük payını üreten pozisyon. Alışta tersi --
    eklenecek ilk şey, portföyün oynaklığına en az katkı veren pozisyon.
    İki kural birbirinin aynası ve ikisi de ölçülmüş bir sayıya dayanıyor.
    """
    share = (contribution or {}).get("contribution")
    if share is None:
        return (1, 0.0)
    return (0, -float(share) if side == SELL else float(share))


def plan(
    drift_rows: Sequence[dict[str, Any]],
    positions: Sequence[dict[str, Any]],
    rates: dict[str, float],
    base_currency: str,
    blocked_cash: float = 0.0,
    available_cash: float = 0.0,
    contributions: Optional[dict[str, dict[str, Any]]] = None,
    fundamentals: Optional[dict[str, dict[str, Any]]] = None,
    news: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Sapmayı satır satır emir karşılığına çevirir.

    `positions` her biri en az `symbol`, `bucket`, `quantity`, `price`,
    `currency` ve `value_base` taşıyan sözlükler. Değerleme çağırana bırakılmış
    -- `ai_service.holding_value` tek uygulama ve onu burada tekrarlamak iki
    farklı portföy değeri demek olurdu.

    `contributions`, `fundamentals` ve `news` sembol -> ölçüm haritaları;
    üçü de opsiyonel ve üçü birden boşsa HİÇBİR satır üretilmiyor -- gerekçe
    zorunluluğu tam olarak bu.

    Dönen `rows` emir üretilebilen satırlar, `unresolved` ise üretilemeyenler
    ve HER BİRİ NEDENİNİ söylüyor. Sessizce atlanmış bir kova, kullanıcının
    hedefine ulaşamamasının sebebini görünmez yapardı.
    """
    contributions = contributions or {}
    fundamentals = fundamentals or {}
    news = news or {}
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

        # Adaylar SEÇİLİYOR, kova farkı orantılı dağıtılmıyor. "Hangi hisse"
        # ayrı bir soru ve üç ölçümden cevaplanıyor; sıralama satışta en
        # yüksek risk katkısıyla, alışta en düşüğüyle başlıyor.
        candidates = []
        for holding in holdings:
            symbol = holding.get("symbol")
            reasons = rationale_for(
                side,
                contributions.get(symbol),
                fundamentals.get(symbol),
                news.get(symbol),
            )
            if not reasons:
                # Sayısı olmayan satır listeye GİRMİYOR. Boş bir gerekçe
                # alanıyla öneri sunmak, gerekçeyi kullanıcının uydurmasına
                # bırakmak olurdu.
                unresolved.append({
                    "bucket": bucket, "label": label, "symbol": symbol,
                    "gap_amount": None,
                    "reason": (
                        f"{symbol} için bir seçim gerekçesi ölçülemedi "
                        "(risk katkısı, temel veri ve haber okuması yok)."
                    ),
                })
                continue
            candidates.append((holding, reasons))

        if not candidates:
            continue

        candidates.sort(
            key=lambda pair: _rank_key(side, contributions.get(pair[0].get("symbol")))
        )

        remaining = abs(gap_amount)
        for holding, reasons in candidates:
            if remaining < 0.01:
                break
            # Satışta bir enstrümandan elde olandan fazlası istenemez; sıra
            # bir sonrakine geçiyor. Alışta üst sınır nakit ve o plan
            # seviyesinde uyarılıyor.
            take = (
                min(remaining, float(holding.get("value_base") or 0.0))
                if side == SELL
                else remaining
            )
            if take < 0.01:
                continue
            row = _order_row(holding, side, take, rates, base_currency)
            if row.get("reason"):
                unresolved.append({
                    "bucket": bucket, "label": label,
                    "symbol": holding.get("symbol"),
                    "gap_amount": round(take, 2),
                    "reason": row["reason"],
                })
                continue
            row.update({
                "bucket": bucket,
                "label": label,
                # Satırı listeye sokan sayılar, satırla BİRLİKTE.
                "rationale": reasons,
            })
            residual_total += row["residual_base"]
            if side == BUY:
                buy_total += row["amount_base"]
            remaining -= row["amount_base"]
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
        # Seçim hangi ölçümlerle yapılabildi. Kapsama DÜZ DEĞİL: temiz bir
        # klonda analitik alanlar neredeyse boş ve seçim yalnızca temel
        # oranlar üzerinden çalışır. Bunu söylemeden bir liste sunmak,
        # eksik bir ölçümü tam bir ölçüm gibi göstermek olurdu.
        "data_quality": _coverage(positions, contributions, fundamentals, news),
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


def _coverage(
    positions: Sequence[dict[str, Any]],
    contributions: dict[str, dict[str, Any]],
    fundamentals: dict[str, dict[str, Any]],
    news: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Kaç pozisyon için hangi ölçüm vardı.

    Oran DEĞİL, sayı: "%67 kapsama" bir portföyün kaç pozisyonu olduğunu
    söylemiyor ve üç pozisyonun ikisi ile doksanın altmışı aynı orana
    düşüyor. Payda da yazılı olduğunda okuyan ikisini ayırt edebiliyor.
    """
    symbols = [row.get("symbol") for row in positions if row.get("symbol")]
    return {
        "positions": len(symbols),
        "risk_contribution": sum(1 for symbol in symbols if contributions.get(symbol)),
        "fundamentals": sum(1 for symbol in symbols if fundamentals.get(symbol)),
        "news": sum(1 for symbol in symbols if news.get(symbol)),
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
        # Kova mı enstrüman mı ayrı sayılıyor. Seçim motoru geldiğinden beri
        # çözülemeyenlerin çoğu kova değil ADAY -- ölçüldü, on dört satırın
        # tamamı "kova" diye yazılıyordu ve kullanıcının o hesabında on dört
        # kovası yok, beş kovası var.
        symbols = sum(1 for row in unresolved if row.get("symbol"))
        buckets = len(unresolved) - symbols
        shape = []
        if buckets:
            shape.append(f"{buckets} kova")
        if symbols:
            shape.append(f"{symbols} enstrüman")
        parts.append(
            f"{' ve '.join(shape)} için emir üretilemedi ve her birinin "
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


# ── Bant hedefi ─────────────────────────────────────────────────────────────
#
# Bu bölümün altındaki tek fonksiyon veritabanına dokunuyor; yukarısı saf
# aritmetik ve öyle kalıyor. `signals.refresh_all_signals` ile aynı ayrım:
# motorun kendisi DB tanımıyor, yalnızca onu besleyen fonksiyon tanıyor.
#
# Bağlayıcı bandın KENDİSİ burada değil, `risk.profile.binding_band` içinde:
# iki risk etiketi üzerinde yapılan bir işlem ve etiketlerin tanımı orada.
# Buraya koymak, `investment -> risk` yönünde bir bağımlılık açardı; kurulu
# yön bunun tersi.


def band_statement(
    measured_level: Optional[str],
    declared_tolerance: Optional[str],
    band: Optional[str],
    source: str,
) -> str:
    """Hedefin NEREDEN geldiğini söyleyen cümle, kodda kurulu.

    Ayrışma gizlenmiyor: iki eksen farklı ölçüldüyse hangisinin bağladığı
    yazılıyor. "Size uygun" ya da "önerilen" geçmiyor -- cümle iki olgunun
    karşılaştırması, kişi hakkında bir yargı değil (`profile.suitability()`
    ile aynı sınır).

    Kullanıcının kendi hedefi varsa bant hiç anlatılmıyor: o hedef zaten
    kullanıcınındır ve yanında bir gerekçe istemez.
    """
    if source == "USER":
        return (
            "Karşılaştırma, kendi belirlediğiniz hedef dağılıma göre yapıldı."
        )
    if source == "NONE" or band is None:
        return (
            "Karşılaştırma için ya kendi hedef dağılımınız ya da ölçülebilir "
            "bir portföyle tamamlanmış bir risk anketi gerekiyor."
        )
    if measured_level and declared_tolerance and measured_level != declared_tolerance:
        return (
            f"Portföyünüzün ölçülen riski \"{measured_level}\", ankette "
            f"belirttiğiniz tolerans \"{declared_tolerance}\". Hedef, ikisinden "
            f"daha temkinli olanına -- \"{band}\" bandına -- göre kuruldu."
        )
    if measured_level and declared_tolerance:
        return (
            f"Ölçülen riskiniz ve beyan ettiğiniz tolerans aynı bandda "
            f"(\"{band}\"); hedef o banda göre kuruldu."
        )
    known = "Ölçülen portföy riskiniz" if measured_level else "Ankette belirttiğiniz tolerans"
    return (
        f"{known} \"{band}\"; diğer taraf okunamadığı için hedef buna göre "
        "kuruldu."
    )


def band_targets(db: Session, band: str) -> dict[str, float]:
    """Bandın kova hedefleri. Satırı olmayan kova sözlükte de YOKTUR.

    Eksik bir anahtar "bu bandın o kova hakkında görüşü yok" demek ve
    `drift()` onu `None` olarak okuyor. Sıfırla doldurmak, o kovadaki her
    şeyin satılması gerektiğini söylemek olurdu -- matrisin söylemediği bir
    şey.
    """
    rows = (
        db.query(RiskBandTarget.bucket, RiskBandTarget.target_percent)
        .filter(RiskBandTarget.band == band)
        .all()
    )
    return {bucket: float(percent) for bucket, percent in rows}
