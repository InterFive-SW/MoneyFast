"""The Portföy Analizi endpoint.

One call, not three: the user story sets a 2-second load budget, and fetching
allocation, trend and performance separately would read the same position list
three times.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core import pdf_generator
from app.modules.analytics import report
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_optional_user_id
from app.main import app
from app.modules.investment import market_service

NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)
URL = "/api/analytics/portfolio"


@pytest.fixture
def analytics_client(mocker, caller):
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.all.return_value = []

    mocker.patch.object(
        market_service, "holdings",
        return_value=[{"symbol": "THYAO", "quantity": 100.0, "price": 300.0, "avg_cost": 250.0}],
    )
    mocker.patch.object(market_service, "latest_quotes", return_value={})
    mocker.patch.object(market_service, "freshness", return_value=(NOW, 15, True))
    mocker.patch.object(
        market_service, "account", return_value=SimpleNamespace(id="a1", cash_balance=25000.0, currency_code="TRY")
    )
    mocker.patch.object(market_service, "sector_by_symbol", return_value={"THYAO": "Industrials"})
    mocker.patch.object(
        market_service, "candle_closes",
        return_value=[(NOW, 300.0), (NOW, 301.0)],
    )

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_optional_user_id] = lambda: caller
    try:
        with TestClient(app) as client:
            client.db = db
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_optional_user_id, None)


@pytest.fixture
def caller():
    return "user-1"


class TestPortfolioAnalysis:
    def test_the_report_is_assembled_in_one_call(self, analytics_client):
        body = analytics_client.get(URL).json()
        assert body["total_value"] == pytest.approx(55000.0)
        assert body["cash"] == pytest.approx(25000.0)
        assert body["allocation"]
        assert body["performance"]["observations"] >= 0

    def test_freshness_is_carried(self, analytics_client):
        """A valuation without its as_of is a valuation presented as current."""
        body = analytics_client.get(URL).json()
        assert body["delay_minutes"] == 15
        assert body["is_delayed"] is True
        assert body["as_of"].startswith("2026-08-20")

    def test_the_sector_breakdown_is_present(self, analytics_client):
        body = analytics_client.get(URL).json()
        assert body["sectors"][0]["label"] == "Industrials"

    def test_confirmed_proposals_are_read_for_the_caller(self, analytics_client):
        analytics_client.get(URL)
        assert analytics_client.db.query.called

    @pytest.mark.parametrize("caller", [None])
    def test_an_anonymous_caller_reads_no_transaction_history(self, analytics_client):
        """İK-19: only the authenticated user's data. With no identity there is
        no history to attribute, so none is queried."""
        body = analytics_client.get(URL).json()
        assert body["activity"]["confirmed_count"] == 0


class TestLookback:
    """One period selector drives this endpoint and `/risk/profile`.

    A fixed window here would leave the trend chart showing a year while the
    risk metrics beside it moved to three months -- two spans on one screen,
    which is the failure this whole change exists to remove.
    """

    def test_the_requested_window_reaches_the_candle_reader(self, analytics_client):
        from app.modules.analytics import service

        analytics_client.get(URL, params={"lookback": "3M"})
        _, kwargs = market_service.candle_closes.call_args
        assert kwargs["limit"] == service.window_limit("3M")

    def test_the_default_window_matches_the_risk_module(self, analytics_client):
        """Both resolve 1Y off the same table, so "close enough" cannot creep
        back in as two slightly different year-long windows."""
        from app.modules.analytics import service
        from app.modules.risk import service as risk_service

        analytics_client.get(URL)
        _, kwargs = market_service.candle_closes.call_args
        assert kwargs["limit"] == risk_service.history_limit("1Y")
        assert service.window_limit("1Y") == risk_service.history_limit("1Y")

    def test_casing_is_normalised_rather_than_refused(self, analytics_client):
        """The body model has always uppercased this; only the query string
        did not, and a perfectly valid "3m" reached the user as an error."""
        assert analytics_client.get(URL, params={"lookback": "3m"}).status_code == 200

    def test_an_unknown_window_is_refused(self, analytics_client):
        """Silently falling back to a year would return one span under
        another's label."""
        response = analytics_client.get(URL, params={"lookback": "3Yil"})
        assert response.status_code == 422
        assert "3Yil" in response.json()["detail"]


REPORT_URL = "/api/analytics/report"
REPORT_TOKEN = "TEST-service-key"


@pytest.fixture()
def report_auth(monkeypatch):
    monkeypatch.setenv("BACKEND_API_KEY", REPORT_TOKEN)
    return {"Authorization": f"Bearer {REPORT_TOKEN}"}


class TestReportEndpoints:
    """İki uç, aynı rapor: biri oturumdan, biri yoldan.

    Yoldan adlandıran sürüm servis token'ı istiyor ve bu, ayrı ayrı korunan
    yüzeylerin TOPLAMI olduğu için: rapor pozisyonları, bakiyeyi, maaşı ve
    kira giderini tek belgede taşıyor.
    """

    SECTIONS = {
        "generated_at": "2026-09-03T08:00:00Z", "currency_code": "TRY",
        "as_of": "2026-09-03T07:42:00Z", "is_delayed": True, "delay_minutes": 18,
        "sections": [{"key": "overview", "title": "Genel bakış",
                      "summary": "Toplam varlığınız 1,00 TRY.",
                      "lines": ["a"], "rows": []}],
    }

    def test_the_session_endpoint_needs_no_service_token(self, analytics_client, mocker):
        mocker.patch.object(report, "build_report", return_value=self.SECTIONS)
        response = analytics_client.get(REPORT_URL)
        assert response.status_code == 200
        assert response.json()["sections"][0]["key"] == "overview"

    def test_the_path_scoped_endpoint_is_guarded(self, analytics_client, report_auth):
        assert analytics_client.get(f"{REPORT_URL}/user-9").status_code == 401

    def test_a_wrong_token_is_refused(self, analytics_client, report_auth):
        response = analytics_client.get(
            f"{REPORT_URL}/user-9", headers={"Authorization": "Bearer nope"}
        )
        assert response.status_code == 401

    def test_an_unconfigured_key_refuses_rather_than_opens(
        self, analytics_client, monkeypatch
    ):
        monkeypatch.delenv("BACKEND_API_KEY", raising=False)
        response = analytics_client.get(
            f"{REPORT_URL}/user-9", headers={"Authorization": "Bearer x"}
        )
        assert response.status_code == 503

    def test_the_guarded_endpoint_answers_for_the_named_user(
        self, analytics_client, report_auth, mocker
    ):
        spy = mocker.patch.object(report, "build_report", return_value=self.SECTIONS)
        response = analytics_client.get(f"{REPORT_URL}/user-9", headers=report_auth)
        assert response.status_code == 200
        assert spy.call_args.args[1] == "user-9"

    def test_both_endpoints_answer_from_the_same_builder(
        self, analytics_client, report_auth, mocker
    ):
        """Sohbet ile ekranın rapor konusunda ayrışması mümkün olmamalı."""
        mocker.patch.object(report, "build_report", return_value=self.SECTIONS)
        assert (
            analytics_client.get(REPORT_URL).json()
            == analytics_client.get(f"{REPORT_URL}/user-9", headers=report_auth).json()
        )


class TestReportPdf:
    """Belge SUNUCUDA üretiliyor.

    Ekranın DOM'unu yazdırmak, raporun metnini ikinci bir yerde kurmak olurdu
    ve iki yüzey er ya da geç ayrışırdı -- bu depoda defalarca ölçülen hata.
    """

    URL = "/api/analytics/report.pdf"

    def test_it_returns_a_pdf_as_an_attachment(self, analytics_client, mocker):
        mocker.patch.object(report, "build_report", return_value=TestReportEndpoints.SECTIONS)
        response = analytics_client.get(self.URL)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "attachment;" in response.headers["content-disposition"]
        assert response.content.startswith(b"%PDF")

    def test_the_filename_carries_the_date(self, analytics_client, mocker):
        mocker.patch.object(report, "build_report", return_value=TestReportEndpoints.SECTIONS)
        disposition = analytics_client.get(self.URL).headers["content-disposition"]
        assert "moneyfast-rapor-" in disposition and ".pdf" in disposition

    def test_a_missing_font_is_a_503_rather_than_a_mangled_document(
        self, analytics_client, mocker
    ):
        """Aksanları düşürülmüş Türkçe yanlış yazılmış Türkçedir. Kurulum
        eksikliği kullanıcının düzeltebileceği bir şey de değil, o yüzden
        4xx değil."""
        mocker.patch.object(report, "build_report", return_value=TestReportEndpoints.SECTIONS)
        mocker.patch.object(
            pdf_generator, "generate_report_pdf",
            side_effect=pdf_generator.UnicodeFontMissing("/yok"),
        )
        response = analytics_client.get(self.URL)
        assert response.status_code == 503
        assert "yazı tipi" in response.json()["detail"]

    def test_the_pdf_and_the_json_read_the_same_builder(self, analytics_client, mocker):
        spy = mocker.patch.object(
            report, "build_report", return_value=TestReportEndpoints.SECTIONS
        )
        analytics_client.get(self.URL)
        analytics_client.get(REPORT_URL)
        assert spy.call_count == 2
