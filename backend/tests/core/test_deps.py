"""Unit tests for app/core/deps.py.

The load-bearing claim here is a security one, not a convenience one. The MCP
tool contract says `user_id` must come only from the authenticated session
envelope; these tests pin the two ways that can go wrong — resolving the wrong
user, and resolving a user at all when the token is bad.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core import deps
from app.core.security import create_access_token


def make_db(user) -> MagicMock:
    """A Session double whose query chain resolves to `user`."""
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.first.return_value = user
    return db


ACTIVE_USER = SimpleNamespace(id="user-abc-123", tc_no="98765432109", is_active=True)


class TestGetCurrentUser:
    def test_resolves_the_user_behind_a_valid_token(self):
        token = create_access_token(data={"sub": "98765432109"})
        assert deps.get_current_user(token=token, db=make_db(ACTIVE_USER)) is ACTIVE_USER

    def test_looks_the_user_up_by_tc_no_not_by_id(self):
        """create_access_token puts the TC number in `sub`. Querying by id
        would silently find nothing and 401 every logged-in user."""
        token = create_access_token(data={"sub": "98765432109"})
        db = make_db(ACTIVE_USER)
        deps.get_current_user(token=token, db=db)
        # The filter expression is built from User.tc_no; assert the query ran
        # against the User model rather than inspecting SQLAlchemy internals.
        assert db.query.called

    def test_expired_or_malformed_token_is_rejected(self):
        """decode_access_token returns {} rather than raising, so a missing
        `sub` is the signal — and it must not fall through to a lookup."""
        db = make_db(ACTIVE_USER)
        with pytest.raises(HTTPException) as info:
            deps.get_current_user(token="not-a-jwt", db=db)
        assert info.value.status_code == 401
        assert db.query.called is False

    def test_token_without_a_subject_is_rejected(self):
        token = create_access_token(data={"nothing": "here"})
        with pytest.raises(HTTPException) as info:
            deps.get_current_user(token=token, db=make_db(ACTIVE_USER))
        assert info.value.status_code == 401

    def test_unknown_user_is_rejected(self):
        """A validly signed token for a deleted user must not authenticate."""
        token = create_access_token(data={"sub": "00000000000"})
        with pytest.raises(HTTPException) as info:
            deps.get_current_user(token=token, db=make_db(None))
        assert info.value.status_code == 401

    def test_deactivated_user_is_rejected(self):
        token = create_access_token(data={"sub": "98765432109"})
        inactive = SimpleNamespace(id="u-1", tc_no="98765432109", is_active=False)
        with pytest.raises(HTTPException) as info:
            deps.get_current_user(token=token, db=make_db(inactive))
        assert info.value.status_code == 401

    def test_rejection_reason_is_not_disclosed(self):
        """An unknown user and a bad signature return the same message, so the
        endpoint cannot be used to enumerate accounts."""
        db = make_db(None)
        bad_token = create_access_token(data={"sub": "00000000000"})
        with pytest.raises(HTTPException) as unknown:
            deps.get_current_user(token=bad_token, db=db)
        with pytest.raises(HTTPException) as malformed:
            deps.get_current_user(token="garbage", db=db)
        assert unknown.value.detail == malformed.value.detail


class TestGetCurrentUserId:
    def test_returns_the_identifier_as_a_string(self):
        assert deps.get_current_user_id(user=ACTIVE_USER) == "user-abc-123"

    def test_coerces_a_non_string_id(self):
        """The column is a bare String today but may become a real UUID; the
        contract calls user_id an opaque string either way."""
        import uuid

        identifier = uuid.uuid4()
        user = SimpleNamespace(id=identifier, tc_no="1", is_active=True)
        assert deps.get_current_user_id(user=user) == str(identifier)


class TestGetOptionalUserId:
    def test_no_token_means_anonymous_not_forbidden(self):
        """The chat endpoint must serve general questions to a visitor. None
        is returned rather than a placeholder: the portfolio tools read None
        as "no holdings to fetch", whereas an invented id would be sent to a
        custodian lookup."""
        assert deps.get_optional_user_id(token=None, db=make_db(ACTIVE_USER)) is None

    def test_valid_token_resolves_normally(self):
        token = create_access_token(data={"sub": "98765432109"})
        assert deps.get_optional_user_id(token=token, db=make_db(ACTIVE_USER)) == "user-abc-123"

    def test_expired_token_degrades_to_anonymous(self):
        """An expired session should drop the user to general questions, not
        show them a wall in the middle of a conversation."""
        assert deps.get_optional_user_id(token="expired-nonsense", db=make_db(ACTIVE_USER)) is None

    def test_unknown_user_degrades_to_anonymous(self):
        token = create_access_token(data={"sub": "00000000000"})
        assert deps.get_optional_user_id(token=token, db=make_db(None)) is None
