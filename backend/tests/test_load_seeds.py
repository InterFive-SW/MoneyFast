"""The seed loader, which runs on every backend start.

Not covered by the `--cov=app` gate — it lives in `scripts/` — but it is the
riskiest code added with the seed system: it executes committed SQL against
the live database at boot. The cases below are the ones that decide whether
"there should be no duplicate data" actually holds.
"""

from __future__ import annotations

import pytest

from scripts import load_seeds

HEADER = """-- MoneyFast seed: someone@example.com (TEST-11111111112)
-- moneyfast:user id=aaaa-1111 tc=TEST-11111111112
--
-- Synthetic data only.

-- public.users (1)
INSERT INTO public.users ("id") VALUES ('aaaa-1111') ON CONFLICT DO NOTHING;

-- investment.investment_accounts (1)
INSERT INTO investment.investment_accounts ("id") VALUES ('acc-1') ON CONFLICT DO NOTHING;
"""


class TestStatementSplitting:
    def test_comment_lines_do_not_swallow_the_statement_after_them(self):
        """The exporter writes a `-- table (n)` banner before each block. If
        the splitter treated the banner and the INSERT as one chunk and then
        skipped it for starting with `--`, every table's rows would silently
        vanish."""
        assert list(load_seeds._statements(HEADER)) == [
            'INSERT INTO public.users ("id") VALUES (\'aaaa-1111\') ON CONFLICT DO NOTHING',
            'INSERT INTO investment.investment_accounts ("id") VALUES (\'acc-1\')'
            " ON CONFLICT DO NOTHING",
        ]

    def test_an_empty_file_yields_nothing(self):
        assert list(load_seeds._statements("")) == []

    def test_a_comment_only_file_yields_nothing(self):
        assert list(load_seeds._statements("-- just a note\n-- and another\n")) == []


class _Session:
    """Records what was executed, and answers the ownership probe."""

    def __init__(self, existing_id=None):
        self.existing_id = existing_id
        self.executed: list[str] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, statement, params=None):
        sql = str(statement)
        if "SELECT id FROM public.users" in sql:
            return _Scalar(self.existing_id)
        self.executed.append(sql)
        return None

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _Scalar:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


@pytest.fixture
def seed_file(tmp_path):
    users = tmp_path / "users"
    users.mkdir()
    path = users / "TEST-11111111112-someone.sql"
    path.write_text(HEADER, encoding="utf-8")
    return path


class TestOwnershipGuard:
    def test_a_fresh_database_applies_the_file(self, seed_file):
        session = _Session(existing_id=None)
        assert load_seeds.load_file(session, seed_file) == "2 statements"
        assert session.commits == 1

    def test_reloading_the_same_user_applies_again_and_relies_on_on_conflict(
        self, seed_file
    ):
        """Same id: the rows are already there and every statement is
        ON CONFLICT DO NOTHING, so re-running is a no-op at the database."""
        session = _Session(existing_id="aaaa-1111")
        assert load_seeds.load_file(session, seed_file) == "2 statements"

    def test_a_different_id_under_the_same_tc_is_skipped_entirely(self, seed_file):
        """The case that would corrupt the database rather than duplicate it.

        `public.users` has unique indexes on tc_no and email, so ON CONFLICT
        would drop the users row — but the file's accounts, positions and
        messages all carry the SEED's user id, and modules do not foreign-key
        across schemas. They would attach to an id no user has. Nothing would
        raise; the rows would simply be orphans."""
        session = _Session(existing_id="bbbb-2222")
        outcome = load_seeds.load_file(session, seed_file)

        assert "skipped" in outcome
        assert session.executed == []
        assert session.commits == 0

    def test_a_file_without_the_header_is_loaded_without_the_check(self, tmp_path):
        """Hand-written or pre-header files stay loadable: ON CONFLICT still
        makes them idempotent, so refusing them would cost more than it
        protects."""
        path = tmp_path / "legacy.sql"
        path.write_text('INSERT INTO public.users ("id") VALUES (\'x\');\n')
        session = _Session(existing_id="bbbb-2222")

        assert load_seeds.load_file(session, path) == "1 statements"


class TestLoadAll:
    def test_missing_seeds_directory_is_not_an_error(self, tmp_path):
        """What a teammate has before anyone's first export lands. The app
        still has to start."""
        assert load_seeds.load_all(_Session(), tmp_path) == 0

    def test_every_file_is_applied(self, seed_file):
        session = _Session()
        assert load_seeds.load_all(session, seed_file.parent.parent) == 1

    def test_one_broken_file_does_not_stop_the_others(self, tmp_path, mocker):
        """A seed problem must not be the reason the API will not start."""
        users = tmp_path / "users"
        users.mkdir()
        (users / "a-bad.sql").write_text(HEADER, encoding="utf-8")
        (users / "b-good.sql").write_text(HEADER, encoding="utf-8")

        session = _Session()
        mocker.patch.object(
            load_seeds, "load_file",
            side_effect=[RuntimeError("syntax error"), "2 statements"],
        )

        assert load_seeds.load_all(session, tmp_path) == 1
        assert session.rollbacks == 1


def test_main_closes_the_session(mocker):
    session = _Session()
    mocker.patch.object(load_seeds, "SessionLocal", return_value=session)
    load_all = mocker.patch.object(load_seeds, "load_all", return_value=0)
    session.close = mocker.Mock()

    load_seeds.main()

    assert load_all.called and session.close.called
