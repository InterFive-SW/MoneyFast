"""Chat identity resolution.

`core.deps.get_optional_user_id` collapses two callers into one None: someone
who sent no token, and someone whose token no longer resolves. Only the second
is losing something — their turns stop being stored — so the chat path needs
the distinction these tests pin.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.core.security import create_access_token, create_refresh_token
from app.modules.ai_orchestrator import deps


def make_db(user) -> MagicMock:
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.first.return_value = user
    return db


ACTIVE_USER = SimpleNamespace(id="user-abc-123", tc_no="98765432109", is_active=True)


class TestResolveChatIdentity:
    def test_no_token_is_anonymous_and_says_so(self):
        identity = deps.resolve_chat_identity(token=None, db=make_db(None))
        assert identity == deps.ChatIdentity(user_id=None, token_present=False)

    def test_valid_token_resolves_to_the_user_id(self):
        token = create_access_token(data={"sub": "98765432109"})
        identity = deps.resolve_chat_identity(token=token, db=make_db(ACTIVE_USER))
        assert identity == deps.ChatIdentity(user_id="user-abc-123", token_present=True)

    def test_unresolvable_token_is_anonymous_but_flagged(self):
        """The whole point of the type. A malformed token grants nothing, but
        the caller had a session and lost it, which is worth telling them."""
        identity = deps.resolve_chat_identity(token="not-a-jwt", db=make_db(None))
        assert identity == deps.ChatIdentity(user_id=None, token_present=True)

    def test_refresh_token_presented_as_a_bearer_is_flagged_not_accepted(self):
        """A refresh token lives for days. Accepting one here would make a
        leaked refresh token equivalent to the password for a week."""
        token = create_refresh_token(data={"sub": "98765432109"})
        identity = deps.resolve_chat_identity(token=token, db=make_db(ACTIVE_USER))
        assert identity == deps.ChatIdentity(user_id=None, token_present=True)

    def test_token_for_a_deleted_user_is_flagged_not_accepted(self):
        token = create_access_token(data={"sub": "98765432109"})
        identity = deps.resolve_chat_identity(token=token, db=make_db(None))
        assert identity == deps.ChatIdentity(user_id=None, token_present=True)

    def test_user_id_is_coerced_to_a_string(self):
        """`ai.conversations.user_id` is a String column; handing SQLAlchemy a
        UUID object here would key one user's conversations two ways."""
        numeric = SimpleNamespace(id=4242, tc_no="98765432109", is_active=True)
        token = create_access_token(data={"sub": "98765432109"})
        identity = deps.resolve_chat_identity(token=token, db=make_db(numeric))
        assert identity.user_id == "4242"
