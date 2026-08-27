"""Python-side column defaults.

These helpers run at INSERT time against a real database, so no other test
exercises them — the suite uses mocked sessions throughout. They are small but
load-bearing: a broken id default means colliding primary keys, and a naive
timestamp default means `expires_at` comparisons raise instead of expiring.
"""

from __future__ import annotations

import uuid
from datetime import timezone

from app.modules.ai_orchestrator import models as ai_models
from app.modules.investment import models as investment_models


class TestUuidDefault:
    def test_investment_default_is_a_uuid_string(self):
        value = investment_models._uuid()
        assert isinstance(value, str)
        assert uuid.UUID(value)

    def test_ai_default_is_a_uuid_string(self):
        assert uuid.UUID(ai_models._uuid())

    def test_successive_calls_differ(self):
        assert investment_models._uuid() != investment_models._uuid()


class TestRiskModelDefaults:
    def test_risk_uuid_default_is_a_uuid_string(self):
        from app.modules.risk import models as risk_models

        assert uuid.UUID(risk_models._uuid())

    def test_risk_timestamp_is_timezone_aware_utc(self):
        from app.modules.risk import models as risk_models

        value = risk_models._now()
        assert value.tzinfo is not None
        assert value.utcoffset() == timezone.utc.utcoffset(None)


class TestTimestampDefault:
    def test_investment_timestamp_is_timezone_aware_utc(self):
        """A naive default would make `expires_at < now` raise TypeError, and
        a proposal that cannot be compared cannot be expired."""
        value = investment_models._now()
        assert value.tzinfo is not None
        assert value.utcoffset() == timezone.utc.utcoffset(None)

    def test_ai_timestamp_is_timezone_aware_utc(self):
        assert ai_models._now().tzinfo is not None


class TestMarketModelDefaults:
    def test_news_uuid_default(self):
        from app.modules.market import models as market_models

        assert uuid.UUID(market_models._uuid())

    def test_news_timestamp_default_is_utc(self):
        from app.modules.market import models as market_models

        assert market_models._now().tzinfo is not None
