"""Detaylı rapor: sistemin ölçtüğü her şeyin tek yerde toplanması.

Proje dokümanı bunu adıyla istiyor: *"'Portföyü Yeniden Dengele' ve 'Detaylı
Rapor Oluştur' butonlarıyla tek tıkla akıllı öneri ve kapsamlı analiz raporu
alınır."*

YENİ ÖLÇÜM YOK. Her bölüm zaten var olan bir servisten okuyor; raporun
katkısı ölçmek değil, dağınık duran ölçümleri tek belgede toplamak.

CÜMLELER BURADA KURULUYOR, ÜÇ YÜZEY İÇİN BİR KEZ. Ekran, PDF ve sohbet aynı
metni okuyor. Bu depoda tekrarlanan ders: iki yüzey aynı şeyi ayrı ayrı
yazarsa er ya da geç ayrışırlar -- `suitability` sayfa ile sohbette, kova
adları dağılım ile hedefte, `technical_posture` cümlesi araç ile yazarda.
Rapor üç yüzeye birden gittiği için burada risk üç katı.

Her bölüm bir `summary` cümlesi ve isteğe bağlı `rows` taşıyor. Sohbet
yalnızca cümleleri okuyor: satırların tamamı sentez gövdesini şişirir ve o
gövdenin sağlayıcı sınırına ne kadar yakın olduğu ölçülerek öğrenildi.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.modules.banking import service as banking_service
from app.modules.investment import ai_service, allocation, market_service
from app.modules.investment import service as investment_service
from app.modules.risk import profile as risk_profile
from app.modules.risk import store as risk_store

log = logging.getLogger("moneyfast.analytics.report")


def _money(amount: Optional[float], currency: str = "TRY") -> str:
    """Rapor metnindeki tek para biçimlendirici.

    Türkçe ayraçlarla: binlik nokta, ondalık virgül. Biçimi her bölümde
    yeniden yazmak, aynı belgede iki farklı sayı görünümü demekti.
    """
    if amount is None:
        return "veri yok"
    return f"{amount:,.2f}".replace(",", "~").replace(".", ",").replace("~", ".") + f" {currency}"


def _percent(value: Optional[float]) -> str:
    return "veri yok" if value is None else f"%{value:g}"


def build_report(db: Session, user_id: Optional[str]) -> dict[str, Any]:
    """Kullanıcının tüm ölçümlerini tek belgede toplar.

    Bölüm sırası kasıtlı: önce NE VAR (özet, dağılım), sonra HEDEFE GÖRE
    NEREDE (sapma), sonra NE KADAR RİSK (risk, uygunluk), en sonda NE KADARINI
    AYIRABİLİYOR (nakit akışı). Rapor bir tavsiye üretmiyor; sırası bile
    okuyanı bir sonuca itmemeli, yalnızca ölçümü okunabilir kılmalı.

    Verisi olmayan bölüm ATLANMIYOR, yokluğunu söyleyerek duruyor: sessizce
    düşen bir bölüm, o ölçümün hiç yapılmadığını değil raporun eksik
    olduğunu düşündürür.
    """
    now = datetime.now(timezone.utc)
    holdings = market_service.holdings(db, user_id=user_id)
    quotes = market_service.latest_quotes(db)
    rates = ai_service.fx_rates(quotes)
    account = market_service.account(db, user_id=user_id)
    cash = float(account.cash_balance) if account else 0.0

    valued: list[tuple[dict[str, Any], float]] = []
    unpriced: list[str] = []
    for row in holdings:
        value = ai_service.holding_value(row, rates)
        if value is None:
            unpriced.append(str(row.get("symbol")))
            continue
        valued.append((row, value))

    amounts = allocation.current_amounts(valued, cash)
    sections = [
        _overview_section(valued, cash, unpriced),
        _allocation_section(amounts),
        _drift_section(db, user_id, amounts),
        _risk_section(db, user_id, valued),
        _cash_flow_section(db, user_id),
        _positions_section(valued),
    ]
    # Fiyat tazeliği raporun KENDİSİNDE. Belgenin üretildiği an ile
    # içindeki fiyatların ait olduğu an farklı şeyler ve rapor, sistemin
    # gecikmeyi söylemeyen tek yüzeyi olmamalı: sohbet, portföy ucu ve
    # gösterge paneli hepsi söylüyor.
    #
    # YALNIZCA RAPORDAKİ enstrümanların kotaları. Evrenin tamamı gönderiliyordu
    # ve `freshness` en ESKİ gözlemi alıyor (haklı olarak: bir gövde en az
    # güncel rakamı kadar günceldir). Sonuç, kullanıcının hiç sahip olmadığı
    # ve o saatte KAPALI olan bir borsanın raporun tamamını bayat
    # göstermesiydi -- ölçüldü, BIST fiyatları otuz saniyelikken rapor
    # "462 dakika gecikmeli" diyordu, çünkü ABD borsası on sekiz saattir
    # kapalıydı.
    held = {row.get("symbol") for row, _value in valued}
    own_quotes = {s: q for s, q in quotes.items() if s in held} or quotes
    as_of, delay_minutes, is_delayed, is_stale = market_service.freshness(own_quotes)
    return {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "currency_code": "TRY",
        "as_of": (as_of or now).isoformat().replace("+00:00", "Z"),
        "is_delayed": bool(is_delayed),
        "delay_minutes": int(delay_minutes or 0),
        # Gözlem ESKİ mi. Beslemenin gecikmesinden AYRI: piyasa kapalıyken
        # son kapanış normaldir ve ona "gecikme" demek yanlış olur.
        "is_stale": bool(is_stale),
        "sections": [section for section in sections if section is not None],
    }


def _overview_section(valued, cash, unpriced) -> dict[str, Any]:
    positions_value = sum(value for _row, value in valued)
    total = positions_value + cash
    lines = [
        f"Toplam varlık: {_money(total)}",
        f"Pozisyonların piyasa değeri: {_money(positions_value)}",
        f"Nakit: {_money(cash)}",
        f"Pozisyon sayısı: {len(valued)}",
    ]
    if unpriced:
        # Fiyatlanamayan pozisyon SAYILMIYOR ve bu söyleniyor. Toplamın
        # sessizce eksik olması, raporun en kolay yanlış okunan yeri olurdu.
        lines.append(
            f"Fiyatı bilinmediği için toplama katılmayanlar: {', '.join(unpriced)}"
        )
    return {
        "key": "overview",
        "title": "Genel bakış",
        "summary": f"Toplam varlığınız {_money(total)}; bunun {_money(cash)} kadarı nakit.",
        "lines": lines,
    }


def _allocation_section(amounts: dict[str, float]) -> dict[str, Any]:
    percentages = allocation.as_percentages(amounts)
    rows = [
        {
            "label": allocation.label_for(key),
            "amount": round(value, 2),
            "percent": percentages.get(key),
        }
        for key, value in amounts.items()
        if value or key == allocation.CASH
    ]
    largest = max(rows, key=lambda row: row["amount"], default=None)
    if largest is None or largest["percent"] is None:
        summary = "Dağılım hesaplanacak bir varlık bulunamadı."
    else:
        summary = (
            f"En büyük kova {largest['label']}: "
            f"{_percent(largest['percent'])} ({_money(largest['amount'])})."
        )
    return {
        "key": "allocation",
        "title": "Varlık dağılımı",
        "summary": summary,
        "lines": [
            f"{row['label']}: {_percent(row['percent'])} ({_money(row['amount'])})"
            for row in rows
        ],
        "rows": rows,
    }


def _drift_section(db, user_id, amounts) -> dict[str, Any]:
    targets = investment_service.allocation_targets(db, user_id)
    drift = allocation.drift(amounts, targets)
    return {
        "key": "drift",
        "title": "Hedef dağılımdan sapma",
        # Cümle `allocation.drift`'ten OLDUĞU GİBİ geliyor. Raporun kendi
        # cümlesini kurması, aynı sapmanın ekranda ve raporda farklı
        # anlatılması demekti.
        "summary": drift["statement"],
        "lines": [
            f"{row['label']}: ölçülen {_percent(row['current_percent'])}, "
            f"hedef {_percent(row['target_percent'])}"
            + (
                ""
                if row["gap_points"] is None
                else f" ({row['gap_points']:+g} puan, {_money(row['gap_amount'])})"
            )
            for row in drift["buckets"]
        ],
        "rows": drift["buckets"],
    }


def _risk_section(db, user_id, valued) -> dict[str, Any]:
    positions = [
        {
            "symbol": row.get("symbol"),
            "market_value": value,
            "asset_class": row.get("product_type") or "EQUITY",
            "market": row.get("market"),
        }
        for row, value in valued
    ]
    declared = risk_store.latest_profile(db, user_id) if user_id else None
    # Rapor ölçümü YENİDEN YAPMIYOR: en son kaydedilen anlık görüntüyü
    # okuyor. Burada yeniden hesaplamak, aynı gün içinde raporun ve Analiz
    # sayfasının iki farklı puan göstermesine açık olurdu -- `record_snapshot`
    # tam olarak bu yüzden günde bir satır yazıyor.
    history = risk_store.snapshot_history(db, user_id, days=30) if user_id else []
    snapshot = history[-1] if history else None

    score = float(snapshot.score) if snapshot and snapshot.score is not None else None
    level = getattr(snapshot, "level", None)
    suitability = risk_profile.suitability(
        level, declared.tolerance_level if declared else None
    )
    exposure = risk_profile.group_exposure(
        positions, getattr(declared, "product_groups", None)
    )

    lines = []
    if score is None:
        # Puan YOK ile puan DÜŞÜK farklı şeyler. Ölçülemeyen bir portföye
        # sayı yazmak, raporun en sessiz yalanı olurdu.
        lines.append("Risk puanı henüz hesaplanmadı; Analiz sayfası açıldığında ölçülür.")
    else:
        lines.append(f"Risk puanı: {score:g} / 100 ({level}) — 100 en sakin.")
    lines.append(suitability["statement"])
    lines.extend(row["statement"] for row in exposure["groups"])
    return {
        "key": "risk",
        "title": "Risk ve uygunluk",
        "summary": suitability["statement"],
        "lines": lines,
        "rows": exposure["groups"],
    }


def _cash_flow_section(db, user_id) -> dict[str, Any]:
    flow = banking_service.cash_flow(db, user_id) if user_id else None
    if not flow or not flow.get("has_data"):
        return {
            "key": "cash_flow",
            "title": "Nakit akışı",
            # Bölüm DÜŞÜRÜLMÜYOR. Ölçüldü: 23 kullanıcının 3'ünde bankacılık
            # hareketi var, ve kayıt yokluğu "hiç kazanmıyor" demek değil.
            "summary": "Bu hesap için bankacılık hareketi kaydı bulunmuyor.",
            "lines": [],
        }
    lines = [
        f"Aylık ortalama gelir: {_money(flow['monthly_income'])}",
        f"Aylık ortalama gider: {_money(flow['monthly_expense'])}",
        f"Aylık ortalama artan: {_money(flow['monthly_net'])}",
    ]
    if flow.get("coverage_note"):
        lines.append(flow["coverage_note"])
    lines.extend(
        f"{row['category']}: {_money(row['monthly_amount'])} / ay"
        f" ({_percent(row['share_percent'])})"
        for row in flow.get("categories") or []
    )
    return {
        "key": "cash_flow",
        "title": "Nakit akışı",
        "summary": (
            f"Son {flow['period_days']} günde aylık ortalama "
            f"{_money(flow['monthly_net'])} artıyor."
        ),
        "lines": lines,
        "rows": flow.get("categories") or [],
    }


def _positions_section(valued) -> dict[str, Any]:
    rows = [
        {
            "symbol": row.get("symbol"),
            "name": row.get("name") or row.get("symbol"),
            "quantity": row.get("quantity"),
            "market_value": round(value, 2),
        }
        for row, value in sorted(valued, key=lambda pair: -pair[1])
    ]
    return {
        "key": "positions",
        "title": "Pozisyonlar",
        "summary": (
            f"{len(rows)} pozisyon, piyasa değerine göre sıralı."
            if rows
            else "Değerlenebilir pozisyon bulunamadı."
        ),
        "lines": [
            f"{row['symbol']}: {row['quantity']:g} adet, {_money(row['market_value'])}"
            for row in rows
        ],
        "rows": rows,
    }
