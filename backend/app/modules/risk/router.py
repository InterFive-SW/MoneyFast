from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_id
from app.modules.banking import service as banking_service
from app.modules.investment import ai_service, allocation, market_service
from app.modules.investment import service as investment_service
from . import profile, questionnaire_v2 as questionnaire, scenario, service, store
from . import returns as risk_returns
from app.core.deps import require_service_token
from .deps import lookback_param
from .schemas import (
    AssessmentRequest,
    AssessmentResultOut,
    QuestionnaireOut,
    RiskHistoryOut,
    RiskProfileOut,
    RiskRequest,
    RiskResponse,
    RiskSummaryOut,
    ScenarioOut,
    ScenarioRequest,
    SimulationOut,
    SimulationRequest,
    SnapshotOut,
    StressOut,
)

router = APIRouter(tags=["risk"])


@router.post(
    "/calculate",
    response_model=RiskResponse,
    summary="Portföy risk metrikleri (MCP v2.1 sözleşmesi)",
)
def calculate_risk(request: RiskRequest, db: Session = Depends(get_db)):
    """
    Verilen pozisyon kümesi için geçmişe dönük (ex-post) risk istatistikleri döner.

    Yoğunlaşma metrikleri (HHI, etkin N, ağırlıklar) tam olarak hesaplanır.
    Volatilite, drawdown, VaR, CVaR, beta ve Sharpe ise `market_candles`'taki
    gerçek günlük kapanışlardan hesaplanır.

    Yeterli geçmişi olmayan enstrümanlar `data_quality.excluded_symbols`'e
    yazılır; komşularından doldurulmaz. Hesaplanamayan bir metrik `None` kalır —
    uydurulmuş bir volatilite değeri, olmayan bir değerden kesinlikle daha
    kötüdür, çünkü olmayan değer olmadığı belli olur.
    """
    if not request.positions:
        # The contract documents this as InvalidInputError rather than an
        # empty result: an empty position set cannot produce a meaningful
        # metric, and a zeroed HHI would render as "perfectly diversified".
        raise HTTPException(status_code=400, detail="positions boş olamaz.")

    return service.calculate(
        positions=[position.model_dump() for position in request.positions],
        # Injected so the service stays free of database concerns and can be
        # tested against hand-built series. The limit follows the requested
        # window: the reader defaults to 260 rows, so anything past 1Y came
        # back truncated while the response still carried the longer label.
        closes_for=lambda symbol: market_service.candle_closes(
            db, symbol, limit=service.history_limit(request.lookback)
        ),
        lookback=request.lookback,
        benchmark_symbol=request.benchmark_symbol,
        metrics=request.metrics,
        confidence_level=request.confidence_level,
        risk_free_rate=request.risk_free_rate,
        rebalance_assumption=request.rebalance_assumption,
    )


#: The window the cashflow figures cover. Matches the banking spending
#: endpoint so the two never disagree about what "this month" means.
CASHFLOW_DAYS = 30


def _current_positions(db: Session, user_id: str):
    """The user's holdings, valued in one currency, plus what was left out.

    Shared by `/profile` and `/simulate` so the two can never disagree about
    what the portfolio is -- a simulation compared against a differently-built
    "current" would report a change the user never made.
    """
    holdings = market_service.holdings(db, user_id=user_id)
    quotes = market_service.latest_quotes(db)
    rates = ai_service.fx_rates(quotes)
    warnings: list[str] = []

    positions: list[dict] = []
    for row in holdings:
        if row.get("price") is None:
            warnings.append(f"{row['symbol']}: fiyat yok, hesaba katılmadı")
            continue
        # Converted to one currency before the weights are taken. Comparing a
        # 481-dollar holding against a 404-lira one as though the numbers were
        # commensurate made a 98% position look like half the portfolio, and
        # concentration is computed from exactly these weights.
        value = ai_service.holding_value(row, rates)
        if value is None:
            warnings.append(f"{row['symbol']}: kur bilinmiyor, hesaba katılmadı")
            continue
        positions.append(
            {
                "symbol": row["symbol"],
                "quantity": row["quantity"],
                "market_value": value,
                # The real product type, not a constant. `holdings()` has
                # returned it all along; writing "EQUITY" over it made
                # by_asset_class report {"EQUITY": 1.0} for every portfolio,
                # including one holding nothing but gold.
                "asset_class": row.get("product_type") or "EQUITY",
                # Kova eşlemesi İŞLEM YERİNDEN okunuyor (`allocation.py`),
                # para biriminden değil: altın dolarla fiyatlanıyor ama
                # yabancı hisse değil.
                "market": row.get("market"),
                "sector": row.get("sector") or "UNCLASSIFIED",
                # The key the risk engine actually reads.
                "instrument_currency": row.get("currency") or "TRY",
            }
        )
    return positions, rates, warnings


def _measure(db: Session, user_id: str, lookback: str) -> dict:
    """Everything a risk profile is built from, for one user, once.

    Both profile surfaces -- the page and the AI-facing summary -- read this.
    Computing them separately is how the chat agent and the risk page came to
    answer "how risky is my portfolio" with different numbers: one quoted a
    volatility figure, the other a 0-100 score, and nothing forced them to
    agree. They cannot diverge if there is one computation.
    """
    positions, _rates, warnings = _current_positions(db, user_id)

    metrics: dict = {}
    window: dict = {}
    assumptions: dict = {}
    if positions:
        result = service.calculate(
            positions=positions,
            lookback=lookback,
            closes_for=lambda symbol: market_service.candle_closes(
                db, symbol, limit=service.history_limit(lookback)
            ),
            # "Riskim Yüksek" dedikten sonraki ilk soru: hangi pozisyon
            # yüzünden. Yalnızca sayfa istiyor -- MCP sözleşmesinin metrik
            # listesi donuk.
            include_contributions=True,
        )
        metrics = result.get("metrics") or {}
        metrics["data_quality"] = result.get("data_quality") or {}
        # Carried out of the engine instead of dropped here. The page was
        # showing a Sharpe ratio and a beta without saying what either was
        # measured against or over what span -- and the MCP contract requires
        # the rate to be disclosed alongside Sharpe, which the chat path did
        # and the page did not.
        window = result.get("window") or {}
        assumptions = result.get("assumptions") or {}
    else:
        warnings.append("Portföyünüzde değerlenebilir pozisyon bulunamadı.")

    scored = profile.score_from(metrics)
    # Okumanın yan etkisi: bugünün ölçümü günde en fazla bir kez saklanır.
    # Ayrı bir zamanlanmış iş, aynı sayıları başka bir saatte yeniden
    # hesaplar ve iki değer birbirinden ayrışırdı. Sohbetten gelen okuma da
    # yazar: o gün sayfa hiç açılmasa bile ölçüm gerçekten yapılmıştır.
    store.record_snapshot(db, user_id, lookback, scored, metrics, len(positions))
    declared = store.latest_profile(db, user_id)
    # Nakit, kova dağılımının bir parçası: hedefini "%15 nakit" diye koyan
    # birine nakdi saymadan sapma göstermek, o hedefi hiç ölçmemek olurdu.
    account = market_service.account(db, user_id=user_id)

    return {
        "positions": positions,
        "metrics": metrics,
        "window": window,
        "assumptions": assumptions,
        "scored": scored,
        "declared": declared,
        "suitability": profile.suitability(
            scored["level"], declared.tolerance_level if declared else None
        ),
        # Aynı çizginin ikinci yarısı: `suitability` ölçülen risk seviyesini
        # beyan edilen toleransla karşılaştırıyor, bu ise ÜRÜN GRUBU başına
        # tutulan ağırlığı o grup için verilen bilgi/tecrübe beyanıyla.
        "group_exposure": profile.group_exposure(
            positions, getattr(declared, "product_groups", None)
        ),
        # Üçüncü karşılaştırma, aynı ailenin üçüncü üyesi: ölçülen KOVA
        # ağırlıkları ile kullanıcının kendi girdiği hedef. Sayfada zaten
        # vardı ve sohbete hiç ulaşmıyordu -- `suitability` ile aynı gerekçe:
        # iki yüzey aynı şekli okumazsa ayrışır.
        "allocation_drift": allocation.drift(
            allocation.current_amounts(
                [(row, float(row["market_value"])) for row in positions],
                float(account.cash_balance) if account else 0.0,
            ),
            investment_service.allocation_targets(db, user_id),
        ),
        "warnings": warnings,
    }


def _declared_payload(declared) -> dict | None:
    if declared is None:
        return None
    return {
        "tolerance_level": declared.tolerance_level,
        "investment_horizon": declared.investment_horizon,
        "assessed_at": declared.updated_at,
        "questionnaire_version": declared.questionnaire_version,
    }


@router.get(
    "/profile",
    response_model=RiskProfileOut,
    summary="Kullanıcının risk profili (Risk sayfası)",
)
def risk_profile(
    # Same closed set the POST body enforces, and normalised the same way.
    lookback: str = Depends(lookback_param),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Risk sayfasının okuduğu profil: puan, puanı oluşturan bulgular ve nakit
    akışı.

    `POST /calculate` MCP sözleşmesine dondurulmuş ve ham metrik döner; bu uç
    nokta ekrana göre şekillendirilmiştir ve **kullanıcıya bağlıdır** — pozisyon
    listesini gövdeden almaz, oturumdan çözer.

    Sayfa daha önce tamamen sabit bir fixture'dan besleniyordu: 68 puan, dört
    uydurma bulgu ve hiç ölçülmemiş bir borç/gelir oranı. Buradaki her sayı
    `risk/service.calculate` çıktısına kadar izlenebilir; ham metrikler de
    `metrics` alanında aynen döner.
    """
    measured = _measure(db, user_id, lookback)
    metrics = measured["metrics"]
    scored = measured["scored"]
    positions = measured["positions"]

    since = datetime.now(timezone.utc) - timedelta(days=CASHFLOW_DAYS)
    income = banking_service.income_total(db, user_id, since)
    expense = sum(
        row["amount"] for row in banking_service.spending_by_category(db, user_id, since)
    )

    return RiskProfileOut(
        as_of=datetime.now(timezone.utc).isoformat(),
        score=scored["score"],
        level=scored["level"],
        components=scored["components"],
        findings=profile.findings_from(metrics, len(positions)),
        suggestions=profile.suggestions_from(metrics),
        cashflow={
            "period": f"Son {CASHFLOW_DAYS} gün",
            "currency_code": "TRY",
            "monthly_income": income,
            "monthly_expense": round(expense, 2),
            # None rather than 0.0 when nothing came in: a savings rate of
            # zero claims they spent exactly what they earned.
            "savings_rate": (
                round((income - expense) / income, 4) if income else None
            ),
        },
        metrics=metrics,
        window=measured["window"],
        assumptions=measured["assumptions"],
        position_count=len(positions),
        warnings=measured["warnings"],
        declared=_declared_payload(measured["declared"]),
        suitability=measured["suitability"],
        group_exposure=measured["group_exposure"],
    )


@router.get(
    "/profile/{user_id}",
    response_model=RiskSummaryOut,
    dependencies=[Depends(require_service_token)],
    summary="Risk profili özeti (MCP v2.4 sözleşmesi)",
)
def risk_summary_for_ai(
    user_id: str,
    lookback: str = Depends(lookback_param),
    db: Session = Depends(get_db),
):
    """Sohbet ajanının okuduğu özet: puan, seviye ve beyanla karşılaştırma.

    `POST /calculate` ham istatistik döner ve puanı üretmez; puan ile bandı
    `profile.py` üretiyor ve buraya kadar ajana hiç ulaşmıyordu. Sonuç, tek
    sisteme sorulan bir soruya iki cevaptı: sayfa 83 puan / "Düşük" derken
    sohbet aynı portföy için yalnızca bir oynaklık yüzdesi söylüyordu.

    `GET /profile`'ın aksine kullanıcıyı yoldan alır, oturumdan değil —
    `require_service_token` bu yüzden var: bu uç noktanın konusu çağıranın
    kendisi olmak zorunda değil.

    Sayfanın nakit akışı bloğu burada YOK. Gelir ve gider hiçbir risk
    sorusunu cevaplamıyor, dolayısıyla bir dil modeline gitmesi için de bir
    sebep yok.
    """
    measured = _measure(db, user_id, lookback)
    return RiskSummaryOut(
        as_of=datetime.now(timezone.utc).isoformat(),
        score=measured["scored"]["score"],
        level=measured["scored"]["level"],
        position_count=len(measured["positions"]),
        suitability=measured["suitability"],
        group_exposure=measured["group_exposure"],
        allocation_drift=measured["allocation_drift"],
        declared=_declared_payload(measured["declared"]),
        metrics=service.summarise_for_agent(measured["metrics"]),
        findings=profile.findings_from(
            measured["metrics"], len(measured["positions"])
        ),
        data_quality=measured["metrics"].get("data_quality") or {},
        warnings=measured["warnings"],
    )


@router.get(
    "/questionnaire",
    response_model=QuestionnaireOut,
    summary="Uygunluk testi",
)
async def get_questionnaire():
    """Testin kendisi, bölümlenmiş hâliyle.

    Kimlik doğrulaması istemez — sorularda kişisel veri yok ve formu görmek
    için giriş yapmak zorunda kalmak, testi doldurma ihtimalini düşürmekten
    başka bir işe yaramaz. Cevap GÖNDERMEK ise oturuma bağlıdır.

    Yürürlükteki sürüm dönüyor. Eski bir cevabı olan kullanıcı da bunu görür:
    v1 cevabı kaydında ve puanıyla duruyor, ama yeniden dolduracaksa
    dolduracağı test bu.
    """
    return questionnaire.as_payload()


@router.post(
    "/assessment",
    response_model=AssessmentResultOut,
    summary="Uygunluk testini gönder ve risk profilini güncelle",
)
def submit_assessment(
    request: AssessmentRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Cevapları kaydeder ve geçerli risk profilini günceller.

    Eksik ya da tanınmayan bir cevap 422 ile reddedilir; boşları sıfır sayıp
    puanlamak, yarıda bırakan birine temkinli bir tolerans atfeder ve o
    tolerans sonra portföyüyle karşılaştırılır.
    """
    missing = questionnaire.missing_answers(request.answers)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Şu sorular yanıtlanmadı: {', '.join(missing)}",
        )
    unknown = questionnaire.unknown_answers(request.answers)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Tanınmayan cevap: {', '.join(unknown)}",
        )

    scored = questionnaire.score_answers(request.answers)
    saved = store.record_assessment(db, user_id, request.answers, scored)
    return AssessmentResultOut(
        product_groups=saved.product_groups or [],
        tolerance_level=saved.tolerance_level,
        investment_horizon=saved.investment_horizon,
        assessed_at=saved.updated_at,
        questionnaire_version=saved.questionnaire_version,
        raw_score=scored["raw_score"],
    )


@router.get(
    "/history",
    response_model=RiskHistoryOut,
    summary="Risk puanının zaman içindeki seyri",
)
def risk_history(
    days: int = Query(90, ge=7, le=365),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Kaydedilmiş günlük ölçümler, eskiden yeniye.

    Noktalar `GET /profile` okundukça birikir; geçmişe dönük bir seri
    üretilmez. Ölçülmemiş bir gün uydurulmuş bir noktadan iyidir — grafik o
    gün için boşluk gösterir, portföyün hiç yaşamadığı bir hareketi değil.
    """
    rows = store.snapshot_history(db, user_id, days)
    return RiskHistoryOut(
        lookback=store.SNAPSHOT_LOOKBACK,
        days=days,
        points=[SnapshotOut.model_validate(row) for row in rows],
    )



def _portfolio_series(db: Session, user_id: str, lookback: str):
    """Portföyün gün gün değeri, taban para biriminde.

    `value_series` ile: risk sayfası, analiz ekranı ve buradaki senaryo AYNI
    seriden besleniyor. Ayrı kurulsalardı aynı portföy için farklı bir beta
    çıkardı -- bu tam olarak bir kez oldu ve 0,0062 ile 0,7287 arasındaki fark
    tarih hizalamasıydı.
    """
    # `_current_positions`, ham `holdings()` DEĞİL: seri `market_value`'yu
    # taban para biriminde okuyor ve o dönüşüm orada yapılıyor. Ham hâlini
    # vermek, her pozisyonun değerini sıfır saydırırdı -- alan yok.
    positions, _rates, warnings = _current_positions(db, user_id)
    limit = service.history_limit(lookback)
    dates, values, excluded = risk_returns.value_series(
        positions,
        lambda symbol: market_service.candle_closes(db, symbol, limit=limit),
    )
    return warnings, dates[-limit:], values[-limit:], excluded


def _factor_bars(db: Session, symbol: str, limit: int):
    return market_service.candle_closes(db, symbol, limit=limit)


@router.post(
    "/scenario",
    response_model=ScenarioOut,
    summary="Koşullu senaryo: bir faktör oynasaydı portföy ne olurdu",
)
def run_scenario(
    request: ScenarioRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Ölçülen duyarlılığa göre bir faktör şokunun portföye yansıması.

    TAHMİN DEĞİL. Faktörün ne yapacağı hakkında hiçbir şey söylenmiyor;
    yalnızca yapsaydı ne olacağı, geçmiş birlikte hareketin aritmetiğiyle.
    Üretilen cümle koşullu kuruluyor ve çekincesi aynı cümlede duruyor --
    ikisini ayırmak, ilk yarıyı tek başına bir beklenti hâline getirirdi.

    Ölçülemeyen faktör 422 ile reddediliyor. En göze çarpanı FAİZ: sistemde
    faiz SERİSİ yok, `TR_POLICY_RATE` bir sabit. "Faizler artarsa"yı USDTRY
    gibi ölçüyormuş gibi cevaplamak, uydurulmuş bir sayıyı ölçüm diye vermek
    olurdu.
    """
    return _scenario_payload(db, user_id, request)


@router.post(
    "/scenario/{user_id}",
    response_model=ScenarioOut,
    dependencies=[Depends(require_service_token)],
    summary="Koşullu senaryo (MCP sözleşmesi)",
)
def run_scenario_for_ai(
    user_id: str,
    request: ScenarioRequest,
    db: Session = Depends(get_db),
):
    """Yukarıdakiyle aynı ölçüm, kullanıcısı yoldan gelen hâli.

    `GET /profile/{user_id}` ile aynı desen ve aynı sebep: bu uç noktanın
    konusu çağıranın kendisi olmak zorunda değil, MCP araçları kullanıcıyı
    doğrulanmış oturum zarfından alıp yola koyuyor. İkisi TEK bir yardımcıyı
    çağırıyor, böylece ekran ile sohbetin aynı portföy için farklı bir
    duyarlılık söylemesi mümkün değil.
    """
    return _scenario_payload(db, user_id, request)


def _scenario_payload(db: Session, user_id: str, request: ScenarioRequest) -> dict:
    """İki ucun ortak gövdesi."""
    factor_name = scenario.FACTORS.get(request.factor)
    if factor_name is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"«{request.factor}» için ölçülebilir bir fiyat serisi yok. "
                f"Ölçülebilen faktörler: {', '.join(scenario.FACTORS)}."
            ),
        )

    held_warnings, dates, values, excluded = _portfolio_series(db, user_id, request.lookback)
    if len(values) < scenario.MIN_OBSERVATIONS:
        raise HTTPException(
            status_code=400,
            detail="Senaryo için yeterli fiyat geçmişi olan bir pozisyon gerekiyor.",
        )

    bars = _factor_bars(db, request.factor, service.history_limit(request.lookback))
    measured = scenario.sensitivity(dates, values, bars)
    if measured is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{factor_name} ile portföyünüzün ortak işlem günü sayısı "
                f"duyarlılık ölçmeye yetmiyor."
            ),
        )

    impact_pct = scenario.impact(measured["beta"], request.shock_pct)
    warnings = held_warnings + [
        f"{symbol}: fiyat geçmişi yetersiz, hesaba katılmadı" for symbol in excluded
    ]

    return {
        "factor": request.factor,
        "factor_name": factor_name,
        "shock_pct": request.shock_pct,
        "lookback": request.lookback,
        "sensitivity": measured,
        "estimated_impact_pct": impact_pct,
        # Son gözlenen portföy değeri üzerinden. Değerlenemeyen pozisyonlar
        # seriye hiç girmiyor, dolayısıyla tutar onların dışında ve bu
        # `warnings`'te yazılı.
        "estimated_impact_value": values[-1] * impact_pct / 100,
        "statement": scenario.narrate(
            factor_name, request.shock_pct, measured, request.lookback
        ),
        # Gizlenmiş bir varsayım, olmayan bir kesinlik üretir.
        "assumptions": [
            "Duyarlılık, günlük getirilerin geçmiş birlikte hareketinden ölçüldü.",
            "Etki doğrusal varsayıldı: ölçülen katsayı şok büyüklüğüyle çarpıldı.",
            "Portföy bileşimi değişmiyor kabul edildi.",
        ],
        "warnings": warnings,
    }


@router.get(
    "/stress",
    response_model=StressOut,
    summary="Stres testi: gerçekten olanlar",
)
def run_stress(
    lookback: str = Depends(lookback_param),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    İki tür stres, ikisi de ölçüm.

    1. **En kötü günler** — portföyün gerçekten yaşadığı en sert düşüşler,
       tarihleriyle.
    2. **Tarihsel replay** — her faktörün en sert oynadığı pencerede portföyün
       ne yaptığı.

    Uydurulmuş bir kayıp senaryosu yok. Varsayımsal bir tahminin aksine
    bunların doğrulanabilir bir karşılığı var: o günler oldu.

    Ölçülemeyen faktör listede YER ALMAZ, sıfırla görünmez -- sıfır bir
    ölçümdür ve "o faktör portföyü hiç etkilemedi" demektir.
    """
    return _stress_payload(db, user_id, lookback)


@router.get(
    "/stress/{user_id}",
    response_model=StressOut,
    dependencies=[Depends(require_service_token)],
    summary="Stres testi (MCP sözleşmesi)",
)
def run_stress_for_ai(
    user_id: str,
    lookback: str = Depends(lookback_param),
    db: Session = Depends(get_db),
):
    """Yukarıdakiyle aynı ölçüm, kullanıcısı yoldan gelen hâli."""
    return _stress_payload(db, user_id, lookback)


def _stress_payload(db: Session, user_id: str, lookback: str) -> dict:
    """İki ucun ortak gövdesi."""
    held_warnings, dates, values, excluded = _portfolio_series(db, user_id, lookback)
    replays: dict = {}
    names: dict = {}
    if len(values) >= scenario.MIN_OBSERVATIONS:
        limit = service.history_limit(lookback)
        for symbol, label in scenario.FACTORS.items():
            replay = scenario.factor_replay(
                dates, values, _factor_bars(db, symbol, limit)
            )
            if replay is not None:
                replays[symbol] = replay
                names[symbol] = label

    return {
        "lookback": lookback,
        "observation_count": max(0, len(values) - 1),
        "worst_days": scenario.worst_days(dates, values),
        "replays": replays,
        "factor_names": names,
        "excluded_symbols": excluded,
        "warnings": held_warnings + [
            f"{symbol}: fiyat geçmişi yetersiz, hesaba katılmadı" for symbol in excluded
        ],
    }


@router.post(
    "/simulate",
    response_model=SimulationOut,
    summary="\"Ne olur?\" — varsayımsal bir değişikliğin risk etkisi",
)
def simulate(
    request: SimulationRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Bir alım/satım yapılsaydı ölçülen risk nasıl değişirdi.

    Yeni bir matematik yok: `service.calculate` zaten dışarıdan bir pozisyon
    listesi alıyor, burada yapılan tek şey ikinci bir liste üretip motoru iki
    kez çalıştırmak.

    Bunun bir öneri motoruna dönüşmemesi iki kurala bağlı: **değişikliği
    sunucu önermez**, kullanıcı verir; ve yanıt "daha iyi/daha kötü" demez,
    yalnızca iki ölçümü yan yana koyar. Yorumu okuyan yapar.
    """
    return _simulate_payload(db, user_id, request)


@router.post(
    "/simulate/{user_id}",
    response_model=SimulationOut,
    dependencies=[Depends(require_service_token)],
    summary="Varsayımsal değişikliğin risk etkisi (MCP sözleşmesi)",
)
def simulate_for_ai(
    user_id: str,
    request: SimulationRequest,
    db: Session = Depends(get_db),
):
    """Yukarıdakiyle aynı karşılaştırma, kullanıcısı yoldan gelen hâli.

    Bu uç nokta aylardır yazılı ve testliydi; hiçbir MCP aracı onu
    çağırmıyordu. "Şu hisseden alsam riskim ne olur" sorusunun cevabı vardı
    ve sohbetten erişilemiyordu.
    """
    return _simulate_payload(db, user_id, request)


def _simulate_payload(db: Session, user_id: str, request: SimulationRequest) -> SimulationOut:
    """İki ucun ortak gövdesi."""
    positions, rates, warnings = _current_positions(db, user_id)
    if not positions:
        raise HTTPException(
            status_code=400,
            detail="Karşılaştırma için önce değerlenebilir bir pozisyon gerekiyor.",
        )

    held = {position["symbol"]: position for position in positions}
    resolved: list[dict] = []
    applied: list[dict] = []

    for change in request.changes:
        symbol = change.symbol.upper()
        existing = held.get(symbol)
        if existing is not None and existing["quantity"]:
            # Bir birimin değeri, elde tutulan pozisyonun kendisinden. Fiyatı
            # yeniden çekmek, portföyün değerlendiği kurdan farklı bir kur
            # kullanma riski taşır.
            unit_value = float(existing["market_value"]) / float(existing["quantity"])
            resolved.append({"symbol": symbol, "quantity_delta": change.quantity_delta,
                             "unit_value": unit_value})
            applied.append({"symbol": symbol, "quantity_delta": change.quantity_delta,
                            "applied": True, "note": None})
            continue

        product = market_service.get_product(db, symbol)
        if product is None:
            applied.append({"symbol": symbol, "quantity_delta": change.quantity_delta,
                            "applied": False, "note": "Bu sembol bulunamadı."})
            continue
        quote = market_service.latest_quotes(db, symbols=[symbol]).get(symbol)
        if quote is None or quote.get("price") is None:
            applied.append({"symbol": symbol, "quantity_delta": change.quantity_delta,
                            "applied": False, "note": "Bu sembolün güncel fiyatı yok."})
            continue
        unit_value = ai_service.holding_value(
            {"quantity": 1, "price": quote["price"], "currency": quote.get("currency")}, rates
        )
        if unit_value is None:
            applied.append({"symbol": symbol, "quantity_delta": change.quantity_delta,
                            "applied": False, "note": "Bu sembolün kuru bilinmiyor."})
            continue
        resolved.append({
            "symbol": symbol, "quantity_delta": change.quantity_delta,
            "unit_value": unit_value,
            "asset_class": product.product_type or "EQUITY",
            "sector": getattr(product, "sector", None) or "UNCLASSIFIED",
            "instrument_currency": product.currency_code or "TRY",
        })
        applied.append({"symbol": symbol, "quantity_delta": change.quantity_delta,
                        "applied": True, "note": None})

    hypothetical_positions = service.apply_changes(positions, resolved)

    def measure(rows: list[dict]) -> dict:
        result = service.calculate(
            positions=rows,
            lookback=request.lookback,
            closes_for=lambda symbol: market_service.candle_closes(
                db, symbol, limit=service.history_limit(request.lookback)
            ),
        )
        metrics = result.get("metrics") or {}
        side = service.summarise_for_simulation(metrics, profile.score_from(metrics))
        side["position_count"] = len(rows)
        return side

    current = measure(positions)
    hypothetical = measure(hypothetical_positions) if hypothetical_positions else {
        "score": None, "level": None, "volatility": None, "hhi": None,
        "effective_n": None, "max_drawdown": None, "position_count": 0,
    }

    return SimulationOut(
        as_of=datetime.now(timezone.utc).isoformat(),
        current=current,
        hypothetical=hypothetical,
        deltas=service.simulation_deltas(current, hypothetical),
        changes=applied,
        warnings=warnings,
    )


@router.get("/health", summary="Risk modülü sağlık durumu")
async def health_check():
    return {"status": "ok", "module": "risk"}
