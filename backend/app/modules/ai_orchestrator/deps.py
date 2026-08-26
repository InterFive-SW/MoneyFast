"""Chat identity resolution.

`core.deps.get_optional_user_id` answers one question -- "who is this?" -- and
returns None for two very different callers: a visitor who sent no token, and
someone whose session expired mid-conversation. The chat endpoints need to
tell those apart, because only the second one is losing something: their turns
stop being persisted and their history stops being read, and until now that
happened in complete silence.

This lives in the module rather than in `core/` deliberately. Only the chat
path needs the distinction, and CLAUDE.md puts `core/` behind a team decision.
It imports from `core.deps`; it does not modify it.
"""

from typing import NamedTuple, Optional

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, optional_oauth2_scheme


class ChatIdentity(NamedTuple):
    """Who is asking, and whether they tried to prove it.

    `user_id is None and token_present` is the interesting case: a token was
    sent and it did not resolve. Expired, malformed, minted for a deleted
    user -- from here they are the same thing, and all of them mean the
    session is gone rather than absent.
    """

    user_id: Optional[str]
    token_present: bool


def resolve_chat_identity(
    token: Optional[str] = Depends(optional_oauth2_scheme),
    db: Session = Depends(get_db),
) -> ChatIdentity:
    if not token:
        return ChatIdentity(user_id=None, token_present=False)
    try:
        user = get_current_user(token=token, db=db)
    except HTTPException:
        # Still anonymous for authorisation purposes -- an unresolvable token
        # grants nothing. The flag only changes what the user is told.
        return ChatIdentity(user_id=None, token_present=True)
    return ChatIdentity(user_id=str(user.id), token_present=True)
