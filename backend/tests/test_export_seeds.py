"""How the exporter writes ids that are not portable between machines.

Two columns hold ids generated on whichever machine created the row, so
writing them literally produces SQL that only works there. `product_id` was
already handled; `conversation_id` was not, and the consequence was not a
duplicate but a silent total loss.

Measured before the fix, on a database that already held one of the seeded
user's threads under a different conversation id -- which is what two people
chatting on the shared `tester` login produces:

    seed 11111111110-tester.sql failed, skipped: ForeignKeyViolation
    tc_no 11111111110 -> 1 conversation, 0 positions

Every one of that user's 46 conversations and 13 positions was rolled back,
reported as a single line in the log.
"""

from __future__ import annotations

from types import SimpleNamespace

from scripts import export_seeds


class _Session:
    """Returns one prepared row for whatever SELECT the dumper builds."""

    def __init__(self, row):
        self._row = row
        self.sql = ""

    def execute(self, statement, params=None):
        self.sql = str(statement)
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: [self._row]))


class TestConversationLookup:
    ROW = {
        "id": "m-1",
        "conversation_id": "local-uuid-that-differs-per-machine",
        "role": "user",
        "content": "merhaba",
        "_conv_user": "u-1",
        "_conv_thread": "probe-trade-2",
    }

    def _emit(self):
        session = _Session(self.ROW)
        return "\n".join(export_seeds._dump_table(
            session, "ai.messages", "TRUE", "id", "u-1", ("conversation_id",),
        ))

    def test_the_conversation_is_looked_up_by_user_and_thread(self):
        """(user_id, thread_id) is the unique key on ai.conversations, so the
        lookup is single-valued by construction."""
        sql = self._emit()
        assert "SELECT id FROM ai.conversations" in sql
        assert "user_id = 'u-1'" in sql
        assert "thread_id = 'probe-trade-2'" in sql

    def test_the_local_id_is_never_written(self):
        """The whole point: a literal id belongs to the machine that made it."""
        assert "local-uuid-that-differs-per-machine" not in self._emit()

    def test_the_message_id_stays_literal(self):
        """Message ids ARE stable, and ON CONFLICT dedupes on them. Resolving
        them too would break the re-run-is-a-no-op property."""
        assert "'m-1'" in self._emit()

    def test_the_carried_helper_columns_are_not_inserted(self):
        """`_conv_user` and `_conv_thread` are how the lookup is built, not
        columns of ai.messages."""
        sql = self._emit()
        assert '"_conv_user"' not in sql and '"_conv_thread"' not in sql

    def test_every_row_still_carries_on_conflict(self):
        assert "ON CONFLICT DO NOTHING;" in self._emit()


class TestProductLookupStillWorks:
    """The pattern this generalises from. Instruments come from a migration's
    gen_random_uuid(), so their ids differ per clone too."""

    ROW = {"id": "p-1", "product_id": "generated-elsewhere", "quantity": 3,
           "_symbol": "THYAO"}

    def test_the_symbol_lookup_is_emitted(self):
        session = _Session(self.ROW)
        sql = "\n".join(export_seeds._dump_table(
            session, "investment.portfolio_positions", "TRUE", "id", "u-1",
            ("product_id",),
        ))
        assert "WHERE symbol = 'THYAO'" in sql
        assert "generated-elsewhere" not in sql


class TestPlainTables:
    def test_a_table_with_nothing_to_resolve_writes_values_directly(self):
        session = _Session({"id": "a-1", "account_number": "TR-TEST-0001"})
        sql = "\n".join(export_seeds._dump_table(
            session, "banking.accounts", "TRUE", "id", "u-1",
        ))
        assert "'TR-TEST-0001'" in sql
        assert "SELECT id FROM" not in sql

    def test_an_empty_table_emits_nothing(self):
        session = _Session(None)
        session.execute = lambda *a, **k: SimpleNamespace(
            mappings=lambda: SimpleNamespace(all=lambda: [])
        )
        assert export_seeds._dump_table(session, "banking.accounts", "TRUE", "id", "u-1") == []
