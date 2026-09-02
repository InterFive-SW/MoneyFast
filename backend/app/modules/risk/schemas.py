"""Request/response models for POST /api/risk/calculate.

Frozen against "MCP Tools Interface Definitions v2.1". Field names are
snake_case because that is what the contract specifies; this module has no
frontend consumer.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

LOOKBACKS = ("1M", "3M", "6M", "1Y", "3Y", "5Y", "MAX")
METRICS = (
    "VOLATILITY", "MAX_DRAWDOWN", "VAR", "CVAR",
    "BETA", "SHARPE", "CONCENTRATION", "CORRELATION_MATRIX",
)


class PositionIn(BaseModel):
    """One holding. Extra keys are accepted and ignored.

    The agent passes `get_portfolio_positions["positions"]` straight through,
    so this model must tolerate the full contract shape without enumerating
    every field.
    """

    symbol: str
    quantity: float = 0.0
    market_value: float
    #: All three are Optional with a default, and the validator below turns an
    #: explicit null into that default. A bare `str = "..."` only fills in an
    #: ABSENT key, and `get_portfolio_positions` sends `"sector": null` for an
    #: unclassified instrument -- so the whole chat risk path answered 422 and
    #: the user was told the data could not be retrieved.
    asset_class: Optional[str] = "EQUITY"
    instrument_currency: Optional[str] = "TRY"
    #: Declared, because `extra: "ignore"` silently dropped it. The engine
    #: reads `position["sector"]` for its breakdown, so every portfolio that
    #: arrived through this model reported `{"UNCLASSIFIED": 1.0}` -- the
    #: sector was carried all the way from the database and then stripped one
    #: layer before it was used.
    sector: Optional[str] = "UNCLASSIFIED"

    model_config = {"extra": "ignore"}

    @field_validator("asset_class", "instrument_currency", "sector", mode="before")
    @classmethod
    def _null_means_unknown(cls, value, info):
        """`null` and "not sent" say the same thing here: nobody knows.

        Distinguishing them would mean carrying a None into the engine, which
        groups weights by these values -- a None bucket renders as an unnamed
        slice of the pie rather than as "Sınıflandırılmamış".
        """
        if value is None:
            return cls.model_fields[info.field_name].default
        return value


class RiskRequest(BaseModel):
    positions: List[PositionIn]
    lookback: str = "1Y"
    benchmark_symbol: Optional[str] = None
    metrics: Optional[List[str]] = None
    confidence_level: float = 0.95
    risk_free_rate: Optional[float] = None
    rebalance_assumption: str = "BUY_AND_HOLD"

    @field_validator("lookback")
    @classmethod
    def _known_lookback(cls, value: str) -> str:
        """Reject an unknown window instead of quietly using a different one.

        `returns.window_for` falls back to 252 bars for anything it does not
        recognise, so a typo produced a year of data under whatever label the
        caller sent. The caller was never told.
        """
        upper = value.upper()
        if upper not in LOOKBACKS:
            raise ValueError(f"lookback {value!r} geçersiz; beklenen: {', '.join(LOOKBACKS)}")
        return upper

    @field_validator("metrics")
    @classmethod
    def _known_metrics(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        """An unrecognised metric name computes nothing and says nothing.

        The service matches uppercase, so casing is normalised here rather
        than rejected -- but a name that is not in the contract is an error,
        not an empty result.
        """
        if value is None:
            return None
        normalised = [item.upper() for item in value]
        unknown = [item for item in normalised if item not in METRICS]
        if unknown:
            raise ValueError(
                f"metrics {', '.join(unknown)} geçersiz; beklenen: {', '.join(METRICS)}"
            )
        return normalised


class Window(BaseModel):
    start_date: str
    end_date: str
    observation_count: int
    frequency: str


class DataQuality(BaseModel):
    coverage: float
    excluded_symbols: List[str] = Field(default_factory=list)
    #: Always zero, and correctly so: nothing in this module fills gaps. A
    #: symbol with too little history is excluded and named rather than
    #: interpolated, so there is no filled day to count. The field stays
    #: because the contract declares it.
    gap_filled_days: int = 0
    # Defaults False on purpose. The optimistic default would let a
    # three-observation window be presented as a firm volatility figure.
    is_statistically_reliable: bool = False


class RiskResponse(BaseModel):
    as_of: str
    source: str
    is_delayed: bool
    window: Window
    metrics: Dict[str, Any]
    assumptions: Dict[str, Any]
    data_quality: DataQuality


# ---------------------------------------------------------------------------
# The user-facing profile, for the Risk page.
#
# Distinct from RiskResponse above, which is frozen against the MCP contract
# and speaks in raw metrics. This one is shaped for a screen: a score, the
# findings behind it, and what to look at next.
# ---------------------------------------------------------------------------
class ScoreComponent(BaseModel):
    name: str
    #: The raw metric, so the UI can show what produced the sub-score.
    measured: Optional[float] = None
    weight: float
    #: 0..1, or None when the input could not be measured. Never coalesced to
    #: zero: an unmeasurable drawdown is not the same as no drawdown.
    penalty: Optional[float] = None


class RiskFinding(BaseModel):
    id: str
    title: str
    description: str
    impact: str
    #: The number the finding was derived from. A finding the user cannot
    #: trace back to a measurement is an opinion.
    value: Optional[float] = None


class RiskSuggestion(BaseModel):
    id: str
    title: str
    description: str
    actionLabel: str
    priority: str


class CashflowOut(BaseModel):
    """Income against expense, from the banking ledger.

    The page previously showed a debt-to-income ratio built from a fixture.
    There is no loan model in this system, so debt is not reported at all
    rather than invented.
    """

    period: str
    currency_code: str = "TRY"
    monthly_income: float = 0.0
    monthly_expense: float = 0.0
    #: None when there was no income to divide by — a savings rate of 0%
    #: would claim they spent everything they earned.
    savings_rate: Optional[float] = None


class RiskProfileOut(BaseModel):
    as_of: str
    #: None when nothing could be measured. Refusing to score is honest; a
    #: default of 50 is a number the user could act on.
    score: Optional[float] = None
    level: Optional[str] = None
    components: List[ScoreComponent] = Field(default_factory=list)
    findings: List[RiskFinding] = Field(default_factory=list)
    suggestions: List[RiskSuggestion] = Field(default_factory=list)
    cashflow: Optional[CashflowOut] = None
    #: The raw engine output, so nothing on the page is unverifiable.
    metrics: Dict[str, Any] = Field(default_factory=dict)
    #: What the numbers cover: start/end date, observation count, frequency.
    window: Dict[str, Any] = Field(default_factory=dict)
    #: What they were measured AGAINST: the benchmark, the risk-free rate the
    #: Sharpe ratio is net of, the rebalancing assumption. `POST /calculate`
    #: has always produced these; this endpoint dropped them, so the page
    #: rendered a Sharpe and a beta with nothing to interpret them by.
    assumptions: Dict[str, Any] = Field(default_factory=dict)
    position_count: int = 0
    warnings: List[str] = Field(default_factory=list)
    #: None until the questionnaire is completed. The page stays open either
    #: way -- a soft gate: measurement is shown, comparison waits.
    declared: Optional["DeclaredProfileOut"] = None
    #: Always present. With no declaration it carries `alignment: "UNKNOWN"`
    #: and the call-to-action wording, so the page never has to guess.
    suitability: Optional["SuitabilityOut"] = None


# ---------------------------------------------------------------------------
# Risk tolerance questionnaire
# ---------------------------------------------------------------------------
class QuestionOptionOut(BaseModel):
    value: str
    label: str


class QuestionOut(BaseModel):
    key: str
    prompt: str
    #: One line under the question explaining why it is being asked. A
    #: suitability test that reads like a form gets abandoned; one that
    #: explains itself gets finished.
    helper: Optional[str] = None
    options: List[QuestionOptionOut]


class QuestionGroupOut(BaseModel):
    """Bir ürün grubu ve ona sorulan üç soru.

    Bölüm 3 dört grup × üç soru; ekran bunu bir matris olarak çiziyor. Yapı
    yalnızca SUNUM meselesi -- puanlama düz soru listesi üzerinden çalışıyor
    ve bu gruplamadan habersiz.
    """
    key: str
    label: str
    #: Grubun risk seviyesi, testin kendi yazdığı hâliyle. Yeterlilik kuralı
    #: da buna bağlı: mevduat için istenen kanıtla türev için istenen aynı
    #: olamaz.
    risk: str
    questions: List[QuestionOut]


class QuestionSectionOut(BaseModel):
    """Testin bir bölümü.

    On altı soruyu tek listede göstermek kimsenin dolduracağı bir form değil;
    bölümler sihirbazın adımlarını veriyor.
    """
    key: str
    title: str
    helper: Optional[str] = None
    questions: List[QuestionOut] = []
    groups: List[QuestionGroupOut] = []


class QuestionnaireOut(BaseModel):
    version: str
    sections: List[QuestionSectionOut]


class AssessmentRequest(BaseModel):
    """Answers, keyed by question. Every question is required.

    A partial questionnaire scored with the blanks as zeros would report a
    cautious tolerance for someone who simply stopped halfway -- and that
    answer would then be compared against their portfolio as if they had
    given it.
    """

    answers: Dict[str, str]


class DeclaredProfileOut(BaseModel):
    """What the user said, and when they said it."""

    tolerance_level: str
    investment_horizon: str
    assessed_at: datetime
    questionnaire_version: str


class SuitabilityOut(BaseModel):
    """Measurement beside declaration.

    Both fields carry the SAME three labels (Düşük/Orta/Yüksek) rather than
    two numbers. The measured score is inverted -- 100 means calm -- and the
    questionnaire's raw score is not, so comparing the numbers would be read
    backwards sooner or later.
    """

    #: The measured portfolio risk level. None when nothing was measurable.
    measured_level: Optional[str] = None
    #: What the user declared. None until the questionnaire is completed.
    declared_tolerance: Optional[str] = None
    #: ALIGNED | PORTFOLIO_RISKIER | PORTFOLIO_CALMER | UNKNOWN
    alignment: str = "UNKNOWN"
    #: Turkish, and a statement of fact rather than a suitability claim.
    statement: str = ""


class ProductGroupOut(BaseModel):
    """Bir ürün grubunun yeterliliği ve GEREKÇESİ.

    Gerekçe zorunlu. "Uygun değil" tek başına kişi hakkında bir yargı gibi
    okunuyor; hangi beyandan çıktığı yazılı olunca hem öyle olmadığı hem de
    kullanıcının cevabını değiştirerek sonucu değiştirebileceği görünüyor.
    """
    key: str
    label: str
    risk: str
    knowledge: str
    frequency: str
    volume: str
    has_experience: bool
    eligible: bool
    reason: str


class AssessmentResultOut(DeclaredProfileOut):
    raw_score: float
    #: v1 ile doldurulmuş bir profilde boş. Eski bir cevap yeni kurallarla
    #: yeniden puanlanmıyor, dolayısıyla o profilde ürün grubu yeterliliği
    #: hiç ölçülmedi -- boş liste "hiçbiri uygun değil" demek değil,
    #: "sorulmadı" demek.
    product_groups: List[ProductGroupOut] = []


# ---------------------------------------------------------------------------
# "What if" simulation
# ---------------------------------------------------------------------------
class PositionChange(BaseModel):
    """One hypothetical trade.

    The DELTA comes from the caller, never from the server. That is what keeps
    this a calculator rather than a recommendation engine: nothing here
    proposes a change, it only measures one the user described.
    """

    symbol: str = Field(..., min_length=1, max_length=32)
    #: Positive adds, negative reduces. Zero is accepted and changes nothing,
    #: which is a useful way to confirm the two sides agree.
    quantity_delta: float


class SimulationRequest(BaseModel):
    changes: List[PositionChange] = Field(..., min_length=1, max_length=10)
    lookback: str = "1Y"

    @field_validator("lookback")
    @classmethod
    def _known_lookback(cls, value: str) -> str:
        upper = value.upper()
        if upper not in LOOKBACKS:
            raise ValueError(f"lookback {value!r} geçersiz; beklenen: {', '.join(LOOKBACKS)}")
        return upper


class SimulationSideOut(BaseModel):
    """One side of the comparison. A subset of the metrics on purpose —
    showing all twenty invites diffing numbers the change did not move."""

    score: Optional[float] = None
    level: Optional[str] = None
    volatility: Optional[float] = None
    hhi: Optional[float] = None
    effective_n: Optional[float] = None
    max_drawdown: Optional[float] = None
    position_count: int = 0


class AppliedChangeOut(BaseModel):
    """What the server actually did with each requested change.

    Echoed back because a silently dropped change would leave the user reading
    a comparison of something they did not ask for.
    """

    symbol: str
    quantity_delta: float
    applied: bool
    note: Optional[str] = None


class SimulationOut(BaseModel):
    as_of: str
    current: SimulationSideOut
    hypothetical: SimulationSideOut
    #: after - before, per metric. None where either side was unmeasurable —
    #: zero would read as "no change", a different claim from "we cannot tell".
    deltas: Dict[str, Optional[float]] = Field(default_factory=dict)
    changes: List[AppliedChangeOut] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Risk history
# ---------------------------------------------------------------------------
class SnapshotOut(BaseModel):
    """One day's measurement.

    Every metric is optional: a day on which something could not be measured
    is recorded as unmeasured rather than as zero, and the chart draws a gap
    instead of a crash the portfolio never had.
    """

    captured_on: date
    score: Optional[float] = None
    level: Optional[str] = None
    volatility: Optional[float] = None
    hhi: Optional[float] = None
    max_drawdown: Optional[float] = None
    position_count: int = 0

    model_config = {"from_attributes": True}


class RiskHistoryOut(BaseModel):
    #: The window every point was measured over. Stated because the series
    #: would be meaningless if the points came from different windows.
    lookback: str
    days: int
    points: List[SnapshotOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# AI-facing summary
#
# Read by the MCP tool server, not the frontend. Deliberately narrower than
# `RiskProfileOut`: this payload reaches a language model, and the page's
# cashflow block carries the user's income and spending, which answer no risk
# question and have no business in a prompt.
#
# Frozen against "MCP Tools Interface Definitions v2.4" -- the tool layer
# raises ContractViolationError on a missing key rather than defaulting it, so
# every field below is always present.
# ---------------------------------------------------------------------------
class RiskSummaryOut(BaseModel):
    """The interpreted layer: a score, a level, and the declared comparison.

    `POST /calculate` returns raw statistics and nothing else; the score and
    the band are produced here, by `profile.py`. Without this endpoint the
    chat agent had no access to either, so "how risky is my portfolio" was
    answered with a volatility figure while the risk page showed a 0-100
    score -- two answers to one question, from one system.
    """

    as_of: str
    #: None when nothing could be measured. Never defaulted: a score the
    #: engine refused to produce must not reach the model as a number.
    score: Optional[float] = None
    level: Optional[str] = None
    position_count: int = 0
    #: Same shape the page reads, so the two surfaces cannot diverge.
    suitability: SuitabilityOut
    declared: Optional[DeclaredProfileOut] = None
    #: The subset the score is built from, so a stated figure is traceable.
    metrics: Dict[str, Any] = Field(default_factory=dict)
    #: What the score is made of, already in Turkish.
    findings: List[RiskFinding] = Field(default_factory=list)
    data_quality: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Koşullu senaryo ve stres testi
# ---------------------------------------------------------------------------


class ScenarioRequest(BaseModel):
    #: Ölçülebilir faktörlerden biri. Kapalı küme: her biri için GÜNLÜK bir
    #: fiyat serisi gerekiyor ve faiz bilerek dışarıda -- sistemde faiz
    #: SERİSİ yok, yalnızca bir sabit var.
    factor: str
    #: Yüzde olarak şok. Negatif de olabilir; "dolar %10 düşse" de bir soru.
    #: Sınır ±%100: ölçülen bir günlük duyarlılığı bunun ötesine uzatmak,
    #: doğrusal varsayımı taşıyamayacağı yere taşımak olur.
    shock_pct: float = Field(..., ge=-100, le=100)
    lookback: str = "1Y"

    @field_validator("factor")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper().strip()

    @field_validator("lookback")
    @classmethod
    def _known_lookback(cls, value: str) -> str:
        upper = value.upper()
        if upper not in LOOKBACKS:
            raise ValueError(f"lookback {value!r} geçersiz; beklenen: {', '.join(LOOKBACKS)}")
        return upper


class SensitivityOut(BaseModel):
    """Ölçülen duyarlılık. `r_squared` ZORUNLU eşlikçi.

    Tek başına bir beta, ilişkinin ne kadar gerçek olduğu hakkında hiçbir şey
    söylemiyor: 0,42'lik bir beta, faktör değişkenliğin %3'ünü açıklıyorken de
    çıkar.
    """
    beta: float
    correlation: Optional[float] = None
    r_squared: Optional[float] = None
    observation_count: int
    is_statistically_reliable: bool


class ReplayOut(BaseModel):
    """Faktörün en sert oynadığı pencere ve portföyün o günlerde yaptığı.

    Bir model çıktısı değil: o günler gerçekten oldu.
    """
    start_date: datetime
    end_date: datetime
    factor_move_pct: float
    portfolio_move_pct: float
    trading_days: int


class WorstDayOut(BaseModel):
    date: datetime
    return_pct: float


class ScenarioOut(BaseModel):
    factor: str
    factor_name: str
    shock_pct: float
    lookback: str
    base_currency: str = "TRY"
    sensitivity: SensitivityOut
    #: Şokun portföye tahmini yansıması, yüzde ve tutar olarak. Tutar,
    #: değerlenebilen pozisyonların toplamı üzerinden.
    estimated_impact_pct: float
    estimated_impact_value: Optional[float] = None
    #: Kullanıcıya gösterilecek KOŞULLU cümle, çekincesiyle birlikte tam
    #: hâliyle. İkiye bölüp yalnızca ilk yarısını göstermek, koşulu düşürüp
    #: iddiayı bırakmak olur.
    statement: str
    #: Varsayımlar gizlenmiyor: gizlenmiş bir varsayım olmayan bir kesinlik
    #: üretir.
    assumptions: List[str] = []
    warnings: List[str] = []


class StressOut(BaseModel):
    """İki tür stres, ikisi de ÖLÇÜM.

    Uydurulmuş bir kayıp senaryosu yok: biri faktörün en sert oynadığı gerçek
    pencere, diğeri portföyün gerçekten yaşadığı en kötü günler.
    """
    lookback: str
    base_currency: str = "TRY"
    observation_count: int
    worst_days: List[WorstDayOut] = []
    #: Faktör başına tarihsel replay. Ölçülemeyen faktör listede YER ALMAZ,
    #: sıfırla görünmez.
    replays: dict[str, ReplayOut] = {}
    factor_names: dict[str, str] = {}
    excluded_symbols: List[str] = []
    warnings: List[str] = []

