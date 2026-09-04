"""Kaynak listesi — cevabın neye dayandığı, kelimesi kelimesine değil, YAPISAL.

`widgets.py` ile aynı değişmez: **modelden istenmez.** Aşağıdaki her satır,
bir aracın gerçekten döndürdüğü verinin izdüşümü; araç döndürmediyse satır
yoktur. Modelin yazdığı bir kaynakça, olmayan bir belgeyi de yazabilir.

Neden gerekiyordu: atıflar bugüne kadar YALNIZCA modelin düzyazı içine
koyduğu markdown bağlantılarıydı (`prompts.py`, CITING SOURCES). Ölçüldü --
kullanıcı "bana kaynakça verir misin" diye sorduğunda sistem cevap
veremedi, çünkü kaynaklar hiçbir yerde veri olarak durmuyordu; yalnızca
modelin o turda yazmayı seçtiği kadarı vardı.

`api._response_payload` içinde, `widgets.build` ile aynı yerde kuruluyor.
Bunun bir yan faydası var: uzman düğümü uygunluk kapısından ÖNCE çalışıyor,
yani BLOCK edilen bir turda bile `specialist_output` dolu. Kaynakların
engellenmiş bir turda hayatta kalması böylece bedavaya geliyor -- `disclosures`
için gereken durum alanı, sıfırlama ve birleştirme mantığının hiçbirine
ihtiyaç yok.
"""

from __future__ import annotations

from typing import Any, Optional

#: Bir turda gösterilecek en fazla kaynak. Sekiz, arama aracının varsayılan
#: `top_k` değeri; üstü listeyi cevabın kendisinden uzun yapıyor.
MAX_SOURCES = 8

#: Belge kaynakları önce. Sıralama, kullanıcının tıklayabileceği şeyin
#: listenin başında olmasını sağlıyor.
_KIND_ORDER = {"DOCUMENT": 0, "QUOTE": 1, "SERIES": 2, "HOLDINGS": 3, "PROFILE": 4}


def _tr_date(value: Any) -> str:
    """ISO zaman damgasından gün. Saat gösterilmiyor: bir bildirimin hangi
    dakikada yayımlandığı kaynak listesinde gürültü."""
    text = str(value or "")
    return text[:10] if len(text) >= 10 else text


def prior(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Bu konuşmada en son gösterilen kaynaklar.

    Sohbet geçmişindeki asistan turlarından okunuyor; kaynaklar mesajın
    `meta` alanında saklandığı için yeniden açılan bir konuşmada da orada
    duruyorlar.
    """
    for turn in reversed(state.get("conversation_history") or []):
        if turn.get("role") != "assistant":
            continue
        rows = turn.get("sources")
        if rows:
            return [row for row in rows if isinstance(row, dict) and row.get("label")]
    return []


def build(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Bu turun dayandığı kaynaklar.

    `widgets.build`'in bayat durum koruması burada da var: graf `thread_id`
    üzerinden checkpoint alıyor, dolayısıyla hiç araç çalıştırmamış bir turda
    önceki turdan kalma bir `specialist_output` durabilir.

    `status != "OK"` kapısı ise BURADA YOK, bilerek. `_fold_in_own_documents`
    haber araması boş dönüp kullanıcının kendi belgesi bulunduğunda durumu
    "OK"a çeviriyor; ama haber araması HATA verip kendi belgesi bulunan bir
    turda elde gerçek kaynaklar var ve onları saklamanın bir sebebi yok.
    """
    # Önceki turun kaynağı soruluyorsa gösterilecek şey o turun kaynakları.
    # Bu hâlâ bir izdüşüm: satırlar önceki turda bir aracın döndürdüğünden
    # kurulmuştu ve saklandıkları yerden okunuyorlar.
    if state.get("meta_request") == "SOURCES_RECAP":
        return prior(state)[:MAX_SOURCES]

    output = state.get("specialist_output") or {}
    agent = output.get("agent")
    if not agent or agent != state.get("target_agent"):
        return []

    data = output.get("data") or {}
    rows: list[dict[str, Any]] = []
    rows.extend(_documents(data))
    rows.extend(_measurements(agent, data))

    # Aynı belge hem dar hem geniş aramadan gelebilir.
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        key = row.get("url") or row["label"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)

    unique.sort(key=lambda r: _KIND_ORDER.get(r["kind"], 9))
    return unique[:MAX_SOURCES]


def _documents(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Aramanın döndürdüğü belgeler."""
    out = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        publisher = str(item.get("publisher") or "").strip()
        label = title or publisher
        if not label:
            # Ne başlığı ne yayıncısı olan bir satır atıf edilemez.
            continue
        detail = " · ".join(
            part for part in (publisher if title else "", _tr_date(item.get("published_at")))
            if part
        )
        out.append({
            "kind": "DOCUMENT",
            "label": label,
            "detail": detail,
            "url": item.get("url") or None,
            "as_of": item.get("published_at") or None,
        })
    return out


def _measurements(agent: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Belge olmayan kaynaklar: hangi seri, kaç gözlem, hangi ana ait.

    Sağlayıcının adı ASLA yazılmıyor. `sanitize.SOURCE_REPLACEMENTS`
    `YFINANCE_DELAYED`'i "sağlayıcı"ya çeviriyor çünkü o ad 158 cevapta yedi
    kez kullanıcıya ulaşmıştı; buradaki etiket zaten "sağlayıcı" diyerek
    kuruluyor, sonradan temizlenmesi gereken bir şey üretmiyor.
    """
    if agent == "MARKET_DATA_AGENT":
        return _market_data_sources(data)
    if agent == "PORTFOLIO_AGENT":
        positions = data.get("positions")
        if isinstance(positions, list):
            return [{
                "kind": "HOLDINGS",
                "label": "Portföy pozisyonlarınız",
                "detail": f"{len(positions)} pozisyon, {_tr_date(data.get('as_of'))} değerlemesi",
                "url": None,
                "as_of": data.get("as_of"),
            }]
    if agent == "RISK_STRATEGY_AGENT":
        return _risk_sources(data)
    return []


def _market_data_sources(data: dict[str, Any]) -> list[dict[str, Any]]:
    signals = data.get("signals")
    symbol = str(data.get("symbol") or "").strip()
    if isinstance(signals, dict) and symbol:
        observations = signals.get("observations")
        detail = f"{observations} işlem günü" if observations else "günlük kapanışlar"
        return [{
            "kind": "SERIES",
            "label": f"{symbol} günlük kapanış serisi",
            "detail": f"{detail}, {_tr_date(data.get('as_of'))} itibarıyla",
            "url": None,
            "as_of": data.get("as_of"),
        }]

    instruments = data.get("instruments")
    if isinstance(instruments, list) and instruments:
        return [{
            "kind": "QUOTE",
            "label": f"{len(instruments)} enstrümanın son fiyatı",
            "detail": f"sağlayıcı, gecikmeli, {_tr_date(data.get('as_of'))} itibarıyla",
            "url": None,
            "as_of": data.get("as_of"),
        }]
    return []


def _risk_sources(data: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    window = (data.get("window") or {}) if isinstance(data.get("window"), dict) else {}
    count = window.get("observation_count")
    if count:
        out.append({
            "kind": "SERIES",
            "label": "Portföy getiri serisi",
            "detail": f"{count} işlem günü, {_tr_date(data.get('as_of'))} itibarıyla",
            "url": None,
            "as_of": data.get("as_of"),
        })
    assessed = data.get("assessed_at")
    if assessed:
        out.append({
            "kind": "PROFILE",
            "label": "Risk anketi yanıtlarınız",
            "detail": f"{_tr_date(assessed)} tarihinde tamamlandı",
            "url": None,
            "as_of": assessed,
        })
    return out
