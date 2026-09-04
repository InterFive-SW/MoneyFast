"""The privilege boundary.

An administrator can credit a balance and grant a holding, which makes this
the most privileged surface in the application. The two properties that matter
are tested in BOTH directions, because a gate that only holds one way is not a
gate: a customer must not reach an admin endpoint, and an admin must not reach
a customer one.

Measured before the second direction existed: an admin token answered **200**
on `/api/investment/positions` and on `/api/ai_orchestrator/chat`. Not through
the admin gate -- through `get_optional_user_id`, which treated every
unresolvable token as "anonymous" and handed back the demo portfolio.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.security import ADMIN_TOKEN_TYPE, create_access_token, create_admin_token
from app.modules.admin import deps as admin_deps


def _admin(username="admin", active=True):
    return SimpleNamespace(
        id="a-1", username=username, hashed_password="x",
        full_name="Sistem Yöneticisi", is_active=active,
    )


def _db(found=None):
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.first.return_value = found
    return db


class TestAdminGate:
    def test_a_valid_admin_token_resolves(self):
        token = create_admin_token({"sub": "admin"})
        assert admin_deps.require_admin(token=token, db=_db(_admin())).username == "admin"

    def test_a_customer_token_is_refused(self):
        """The whole point. A customer access token carries `typ=access`."""
        token = create_access_token({"sub": "11111111110"})
        with pytest.raises(Exception) as exc:
            admin_deps.require_admin(token=token, db=_db(_admin()))
        assert exc.value.status_code == 401

    def test_a_token_with_no_type_claim_is_refused(self):
        """`get_current_user` treats a missing `typ` as an access token so that
        sessions minted before the claim existed keep working. Extending that
        courtesy here would make every one of those an ADMIN token -- the one
        place where being generous about an absent claim hands out privilege."""
        import jwt as pyjwt

        from app.core.config import settings

        legacy = pyjwt.encode(
            {"sub": "admin", "exp": 9_999_999_999},
            settings.SECRET_KEY, algorithm=settings.ALGORITHM,
        )
        with pytest.raises(Exception) as exc:
            admin_deps.require_admin(token=legacy, db=_db(_admin()))
        assert exc.value.status_code == 401

    def test_an_unknown_administrator_is_refused(self):
        token = create_admin_token({"sub": "ghost"})
        with pytest.raises(Exception) as exc:
            admin_deps.require_admin(token=token, db=_db(None))
        assert exc.value.status_code == 401

    def test_a_deactivated_administrator_is_refused(self):
        token = create_admin_token({"sub": "admin"})
        with pytest.raises(Exception) as exc:
            admin_deps.require_admin(token=token, db=_db(_admin(active=False)))
        assert exc.value.status_code == 401

    def test_a_token_with_no_subject_is_refused(self):
        token = create_admin_token({})
        with pytest.raises(Exception) as exc:
            admin_deps.require_admin(token=token, db=_db(_admin()))
        assert exc.value.status_code == 401


class TestAdminCannotBeACustomer:
    """The other direction, which is the one that was actually broken."""

    def test_an_admin_token_is_not_an_anonymous_customer(self):
        """It used to fall through to anonymous, which reads the DEMO
        portfolio and drives the chat. Refused, not downgraded."""
        from app.core.deps import get_optional_user_id

        token = create_admin_token({"sub": "admin"})
        with pytest.raises(Exception) as exc:
            get_optional_user_id(token=token, db=MagicMock(spec=Session))
        assert exc.value.status_code == 401

    def test_no_token_at_all_is_still_anonymous(self):
        """The behaviour the optional path exists for must survive."""
        from app.core.deps import get_optional_user_id

        assert get_optional_user_id(token=None, db=MagicMock(spec=Session)) is None

    def test_an_admin_token_cannot_open_the_chat(self):
        from app.modules.ai_orchestrator.deps import resolve_chat_identity

        token = create_admin_token({"sub": "admin"})
        with pytest.raises(Exception) as exc:
            resolve_chat_identity(token=token, db=MagicMock(spec=Session))
        assert exc.value.status_code == 401

    def test_the_admin_token_type_is_distinct(self):
        import jwt as pyjwt

        from app.core.config import settings

        payload = pyjwt.decode(
            create_admin_token({"sub": "admin"}),
            settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
        )
        assert payload["typ"] == ADMIN_TOKEN_TYPE
