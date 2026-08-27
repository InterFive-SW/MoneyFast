from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.investment import market_service
from app.modules.market import social_service
from app.modules.market.models import SocialAccount, SocialPost

NOW = datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc)


def counters():
    return {
        "accounts_inserted": 0,
        "accounts_updated": 0,
        "accounts_duplicate": 0,
        "posts_inserted": 0,
        "posts_updated": 0,
        "posts_duplicate": 0,
        "posts_tombstoned": 0,
        "instruments_matched": 0,
        "instruments_unresolved": 0,
        "instrument_links_removed": 0,
        "unresolved": [],
    }


def account_data(**overrides):
    data = {
        "platform": "x",
        "external_account_id": "100",
        "handle": "test_finans",
        "display_name": "Test Finans",
        "source_type": "financial_media",
        "trust_score": 0.75,
        "is_active": True,
    }
    data.update(overrides)
    return data


def post_data(**overrides):
    data = {
        "platform": "x",
        "account_external_id": "100",
        "external_post_id": "200",
        "content_text": "THYAO açıklaması",
        "post_url": "https://x.com/test_finans/status/200",
        "language": "tr",
        "published_at": NOW,
        "collected_at": NOW + timedelta(minutes=1),
        "post_kind": "original",
        "referenced_external_post_id": None,
        "conversation_id": "200",
        "is_tombstoned": False,
        "raw_metadata": {"expanded_urls": []},
        "underlying_source_url": None,
        "instrument_references": ["THYAO"],
    }
    data.update(overrides)
    return data


def db_returning(row):
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.one_or_none.return_value = row
    return db


class TestCanonicalPostUrl:
    def test_normalizes_www_and_fragment(self):
        assert (
            social_service._canonical_post_url(
                "https://www.x.com/Test_Finans/status/200?x=1#f",
                "test_finans",
                "200",
            )
            == "https://x.com/test_finans/status/200"
        )

    @pytest.mark.parametrize(
        "url",
        [
            "http://x.com/test_finans/status/200",
            "https://attacker.example/test_finans/status/200",
            "https://user@x.com/test_finans/status/200",
            "https://x.com:444/test_finans/status/200",
            "https://x.com:bad/test_finans/status/200",
            "https://x.com/test_finans/not-status/200",
            "https://x.com/other/status/200",
        ],
    )
    def test_rejects_noncanonical_or_mismatched_urls(self, url):
        with pytest.raises(social_service.SocialBatchError):
            social_service._canonical_post_url(url, "test_finans", "200")


class TestAccountUpsert:
    def test_inserts_new_account(self):
        db = db_returning(None)
        result = counters()
        row = social_service._upsert_account(db, account_data(), result)
        assert isinstance(row, SocialAccount)
        assert result["accounts_inserted"] == 1
        assert db.add.called and db.flush.called

    def test_updates_mutable_account_fields(self):
        row = SocialAccount(
            id="a1",
            platform="x",
            external_account_id="100",
            handle="old",
            source_type="analyst",
            trust_score=Decimal("0.500"),
            is_active=True,
        )
        db = db_returning(row)
        result = counters()
        social_service._upsert_account(db, account_data(), result)
        assert result["accounts_updated"] == 1
        assert row.handle == "test_finans"

    def test_unchanged_account_is_duplicate(self):
        row = SocialAccount(id="a1", **account_data())
        db = db_returning(row)
        result = counters()
        social_service._upsert_account(db, account_data(), result)
        assert result["accounts_duplicate"] == 1


class TestPostUpsert:
    def test_inserts_unverified_post_and_validates_kap(self):
        db = db_returning(None)
        result = counters()
        account = SocialAccount(id="a1", **account_data())
        row = social_service._upsert_post(
            db,
            post_data(underlying_source_url="https://kap.org.tr/tr/Bildirim/1?q=2#x"),
            account,
            result,
        )
        assert result["posts_inserted"] == 1
        assert row.verification_status == "unverified"
        assert row.underlying_source_url.endswith("Bildirim/1?q=2")
        assert row.underlying_source_type == "kap_disclosure"

    def test_invalid_kap_does_not_discard_post(self):
        db = db_returning(None)
        row = social_service._upsert_post(
            db,
            post_data(underlying_source_url="https://kap.org.tr.attacker.example/x"),
            SocialAccount(id="a1", **account_data(source_type="disclosure_aggregator")),
            counters(),
        )
        assert row.underlying_source_url is None
        assert row.verification_status == "unverified"

    def test_existing_post_cannot_be_reassigned_to_another_account(self):
        row = SocialPost(
            id="p1",
            account_id="original-account",
            platform="x",
            external_post_id="200",
            content_text="old",
            post_url="https://x.com/test_finans/status/200",
            published_at=NOW,
            collected_at=NOW,
            post_kind="original",
            is_tombstoned=False,
            raw_metadata={},
            verification_status="unverified",
        )
        with pytest.raises(social_service.SocialBatchError, match="reassigned"):
            social_service._upsert_post(
                db_returning(row),
                post_data(),
                SocialAccount(id="different-account", **account_data()),
                counters(),
            )

    def test_new_tombstone_is_counted(self):
        db = db_returning(None)
        result = counters()
        social_service._upsert_post(
            db,
            post_data(content_text="", is_tombstoned=True),
            SocialAccount(id="a1", **account_data()),
            result,
        )
        assert result["posts_tombstoned"] == 1

    def test_mutable_fields_update_without_downgrading_verification(self):
        row = SocialPost(
            id="p1",
            account_id="a1",
            platform="x",
            external_post_id="200",
            content_text="old",
            post_url="https://x.com/test_finans/status/200",
            language="tr",
            published_at=NOW,
            collected_at=NOW,
            post_kind="original",
            is_tombstoned=False,
            raw_metadata={},
            verification_status="officially_verified",
        )
        db = db_returning(row)
        result = counters()
        social_service._upsert_post(
            db,
            post_data(content_text="new", is_tombstoned=True),
            SocialAccount(id="a1", **account_data()),
            result,
        )
        assert result["posts_updated"] == 1
        assert result["posts_tombstoned"] == 1
        assert row.verification_status == "officially_verified"

    def test_non_tombstone_update_does_not_increment_tombstone_counter(self):
        row = SocialPost(
            id="p1",
            account_id="a1",
            platform="x",
            external_post_id="200",
            content_text="old",
            post_url="https://x.com/test_finans/status/200",
            language="tr",
            published_at=NOW,
            collected_at=NOW,
            post_kind="original",
            is_tombstoned=False,
            raw_metadata={},
            verification_status="unverified",
        )
        result = counters()
        social_service._upsert_post(
            db_returning(row),
            post_data(content_text="new"),
            SocialAccount(id="a1", **account_data()),
            result,
        )
        assert result["posts_updated"] == 1
        assert result["posts_tombstoned"] == 0

    def test_removed_or_invalid_underlying_link_clears_stale_provenance(self):
        row = SocialPost(
            id="p1",
            account_id="a1",
            platform="x",
            external_post_id="200",
            content_text="old",
            post_url="https://x.com/test_finans/status/200",
            language="tr",
            published_at=NOW,
            collected_at=NOW,
            post_kind="original",
            is_tombstoned=False,
            raw_metadata={},
            verification_status="corroborated",
            underlying_source_url="https://kap.org.tr/old",
            underlying_source_type="kap_disclosure",
            underlying_source_domain="kap.org.tr",
        )
        social_service._upsert_post(
            db_returning(row),
            post_data(underlying_source_url="https://kap.org.tr.attacker.example/x"),
            SocialAccount(id="a1", **account_data()),
            counters(),
        )
        assert row.underlying_source_url is None
        assert row.underlying_source_type is None
        assert row.verification_status == "corroborated"

    def test_repeated_post_is_duplicate_and_preserves_collected_time(self):
        data = post_data()
        row = SocialPost(
            id="p1",
            account_id="a1",
            external_post_id="200",
            verification_status="unverified",
            collected_at=NOW,
            updated_at=NOW,
            **{
                k: v
                for k, v in data.items()
                if k
                not in {
                    "account_external_id",
                    "external_post_id",
                    "collected_at",
                    "instrument_references",
                    "underlying_source_url",
                }
            },
        )
        db = db_returning(row)
        result = counters()
        social_service._upsert_post(
            db, data, SocialAccount(id="a1", **account_data()), result
        )
        assert result["posts_duplicate"] == 1
        assert row.collected_at == NOW


def integrity_error(constraint_name: str | None):
    """Build an IntegrityError with an optional structured PostgreSQL diag name."""

    class Diag:
        def __init__(self, name):
            self.constraint_name = name

    class Orig(Exception):
        def __init__(self, name):
            self.diag = Diag(name)

    return IntegrityError("INSERT", {}, Orig(constraint_name))


class TestInstrumentLinks:
    def test_multiple_references_resolve_and_duplicates_do_not_duplicate_links(
        self, mocker
    ):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.all.return_value = []
        products = {
            "THYAO": [SimpleNamespace(id="thy", symbol="THYAO")],
            "Türk Hava Yolları": [SimpleNamespace(id="thy", symbol="THYAO")],
            "ASELS": [SimpleNamespace(id="asels", symbol="ASELS")],
        }
        mocker.patch.object(
            market_service,
            "resolve_candidates",
            side_effect=lambda _db, ref, strict: products[ref],
        )
        result = counters()
        social_service._attach_instruments(
            db,
            SimpleNamespace(id="p1", external_post_id="200"),
            ["THYAO", "Türk Hava Yolları", "ASELS"],
            result,
        )
        assert result["instruments_matched"] == 2
        assert db.add.call_count == 2
        assert all(
            call.args[0].match_method == "backend_resolver"
            for call in db.add.call_args_list
        )

    def test_ambiguous_and_unknown_references_are_not_guessed(self, mocker):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.all.return_value = []
        mocker.patch.object(
            market_service,
            "resolve_candidates",
            side_effect=[
                [
                    SimpleNamespace(id="1", symbol="KOZAL"),
                    SimpleNamespace(id="2", symbol="KOZAA"),
                ],
                [],
            ],
        )
        result = counters()
        social_service._attach_instruments(
            db,
            SimpleNamespace(id="p1", external_post_id="200"),
            ["koz", "NOTREAL"],
            result,
        )
        assert result["instruments_unresolved"] == 2
        assert result["unresolved"][0]["candidates"] == ["KOZAL", "KOZAA"]
        assert not db.add.called

    def test_existing_relation_is_not_inserted_again(self, mocker):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.all.return_value = [
            SimpleNamespace(product_id="thy")
        ]
        mocker.patch.object(
            market_service,
            "resolve_candidates",
            return_value=[SimpleNamespace(id="thy", symbol="THYAO")],
        )
        result = counters()
        social_service._attach_instruments(
            db, SimpleNamespace(id="p1", external_post_id="200"), ["THYAO"], result
        )
        assert result["instruments_matched"] == 1
        assert not db.add.called

    def test_relations_are_reconciled_to_latest_accepted_references(self, mocker):
        stale = SimpleNamespace(product_id="old")
        current = SimpleNamespace(product_id="thy")
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.all.return_value = [stale, current]
        mocker.patch.object(
            market_service,
            "resolve_candidates",
            return_value=[SimpleNamespace(id="thy", symbol="THYAO")],
        )
        result = counters()
        social_service._attach_instruments(
            db, SimpleNamespace(id="p1", external_post_id="200"), ["THYAO"], result
        )
        db.delete.assert_called_once_with(stale)
        assert result["instrument_links_removed"] == 1
        assert not db.add.called

    def test_unresolved_reference_preserves_existing_relations(self, mocker):
        existing = SimpleNamespace(product_id="thy")
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.all.return_value = [existing]
        mocker.patch.object(market_service, "resolve_candidates", return_value=[])
        result = counters()
        social_service._attach_instruments(
            db, SimpleNamespace(id="p1", external_post_id="200"), ["NOTREAL"], result
        )
        assert result["instruments_unresolved"] == 1
        assert result["instrument_links_removed"] == 0
        assert not db.delete.called

    def test_ambiguous_reference_preserves_existing_relations(self, mocker):
        existing = SimpleNamespace(product_id="thy")
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.all.return_value = [existing]
        mocker.patch.object(
            market_service,
            "resolve_candidates",
            return_value=[
                SimpleNamespace(id="1", symbol="KOZAL"),
                SimpleNamespace(id="2", symbol="KOZAA"),
            ],
        )
        result = counters()
        social_service._attach_instruments(
            db, SimpleNamespace(id="p1", external_post_id="200"), ["koz"], result
        )
        assert result["instruments_unresolved"] == 1
        assert not db.delete.called

    def test_mixed_resolved_and_unresolved_adds_without_deleting_uncertain(
        self, mocker
    ):
        stale = SimpleNamespace(product_id="old")
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.all.return_value = [stale]
        mocker.patch.object(
            market_service,
            "resolve_candidates",
            side_effect=[
                [SimpleNamespace(id="thy", symbol="THYAO")],
                [],
            ],
        )
        result = counters()
        social_service._attach_instruments(
            db,
            SimpleNamespace(id="p1", external_post_id="200"),
            ["THYAO", "NOTREAL"],
            result,
        )
        assert result["instruments_matched"] == 1
        assert result["instruments_unresolved"] == 1
        assert db.add.call_count == 1
        assert not db.delete.called
        assert result["instrument_links_removed"] == 0

    def test_authoritative_empty_list_removes_all_existing_links(self, mocker):
        stale = SimpleNamespace(product_id="old")
        other = SimpleNamespace(product_id="thy")
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.all.return_value = [stale, other]
        result = counters()
        social_service._attach_instruments(
            db, SimpleNamespace(id="p1", external_post_id="200"), [], result
        )
        assert db.delete.call_count == 2
        assert result["instrument_links_removed"] == 2

    def test_idempotent_replay_does_not_duplicate_existing_links(self, mocker):
        existing = SimpleNamespace(product_id="thy")
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.all.return_value = [existing]
        mocker.patch.object(
            market_service,
            "resolve_candidates",
            return_value=[SimpleNamespace(id="thy", symbol="THYAO")],
        )
        result = counters()
        social_service._attach_instruments(
            db, SimpleNamespace(id="p1", external_post_id="200"), ["THYAO"], result
        )
        assert result["instruments_matched"] == 1
        assert not db.add.called
        assert not db.delete.called

    def test_resolver_failure_rolls_back_with_batch(self, mocker):
        db = MagicMock(spec=Session)
        mocker.patch.object(
            social_service,
            "_upsert_account",
            return_value=SimpleNamespace(
                id="a1", platform="x", handle="test_finans", external_account_id="100"
            ),
        )
        mocker.patch.object(
            social_service,
            "_upsert_post",
            return_value=SimpleNamespace(id="p1", external_post_id="200"),
        )
        mocker.patch.object(
            market_service,
            "resolve_candidates",
            side_effect=RuntimeError("resolver unavailable"),
        )
        with pytest.raises(RuntimeError, match="resolver unavailable"):
            social_service.ingest_batch(db, [account_data()], [post_data()])
        assert db.rollback.called
        assert not db.commit.called


class TestBatch:
    def test_commits_valid_posts_and_existing_accounts(self, mocker):
        db = MagicMock(spec=Session)
        account = SimpleNamespace(id="a1", handle="test_finans", platform="x")
        post = SimpleNamespace(id="p1")
        mocker.patch.object(social_service, "_upsert_account", return_value=account)
        mocker.patch.object(social_service, "_upsert_post", return_value=post)
        links = mocker.patch.object(social_service, "_attach_instruments")
        result = social_service.ingest_batch(db, [account_data()], [post_data()])
        assert db.commit.called
        assert result["posts_inserted"] == 0
        links.assert_called_once()

    def test_unknown_account_rolls_back_atomically(self, mocker):
        db = MagicMock(spec=Session)
        mocker.patch.object(social_service, "_find_account", return_value=None)
        with pytest.raises(social_service.SocialBatchError):
            social_service.ingest_batch(db, [], [post_data()])
        assert db.rollback.called and not db.commit.called

    def test_unexpected_failure_rolls_back(self, mocker):
        db = MagicMock(spec=Session)
        mocker.patch.object(
            social_service, "_upsert_account", side_effect=RuntimeError("db")
        )
        with pytest.raises(RuntimeError):
            social_service.ingest_batch(db, [account_data()], [])
        assert db.rollback.called

    def test_integrity_conflict_rolls_back_and_becomes_client_conflict(self, mocker):
        db = MagicMock(spec=Session)
        mocker.patch.object(
            social_service,
            "_upsert_account",
            side_effect=integrity_error("uq_social_accounts_platform_external"),
        )
        with pytest.raises(social_service.SocialBatchConflict, match="identity"):
            social_service.ingest_batch(db, [account_data()], [])
        assert db.rollback.called

    @pytest.mark.parametrize(
        "constraint",
        sorted(social_service.KNOWN_SOCIAL_IDENTITY_CONSTRAINTS),
    )
    def test_each_known_identity_constraint_becomes_conflict(self, mocker, constraint):
        db = MagicMock(spec=Session)
        mocker.patch.object(
            social_service,
            "_upsert_account",
            side_effect=integrity_error(constraint),
        )
        with pytest.raises(social_service.SocialBatchConflict):
            social_service.ingest_batch(db, [account_data()], [])
        assert db.rollback.called

    def test_unknown_constraint_is_reraised_after_rollback(self, mocker):
        db = MagicMock(spec=Session)
        mocker.patch.object(
            social_service,
            "_upsert_account",
            side_effect=integrity_error("ck_social_posts_kind"),
        )
        with pytest.raises(IntegrityError):
            social_service.ingest_batch(db, [account_data()], [])
        assert db.rollback.called

    def test_fk_or_missing_diag_integrity_errors_are_not_identity_conflicts(
        self, mocker
    ):
        db = MagicMock(spec=Session)
        mocker.patch.object(
            social_service,
            "_upsert_account",
            side_effect=integrity_error("social_posts_account_id_fkey"),
        )
        with pytest.raises(IntegrityError):
            social_service.ingest_batch(db, [account_data()], [])
        assert db.rollback.called

        db2 = MagicMock(spec=Session)
        mocker.patch.object(
            social_service,
            "_upsert_account",
            side_effect=IntegrityError("insert", {}, RuntimeError("unique")),
        )
        with pytest.raises(IntegrityError):
            social_service.ingest_batch(db2, [account_data()], [])
        assert db2.rollback.called

    def test_platform_mismatch_rolls_back(self, mocker):
        db = MagicMock(spec=Session)
        account = SimpleNamespace(id="a1", handle="test_finans", platform="other")
        mocker.patch.object(social_service, "_upsert_account", return_value=account)
        with pytest.raises(social_service.SocialBatchError, match="platform"):
            social_service.ingest_batch(db, [account_data()], [post_data()])
        assert db.rollback.called

    def test_finds_previously_stored_account(self):
        account = SimpleNamespace(id="a1")
        db = db_returning(account)
        assert social_service._find_account(db, "x", "100") is account


class TestRead:
    def test_filters_orders_and_projects_without_raw_metadata(self, mocker):
        post = SimpleNamespace(
            id="p1",
            platform="x",
            verification_status="unverified",
            published_at=NOW,
            collected_at=NOW,
            content_text="signal",
            post_url="https://x.com/test_finans/status/200",
            underlying_source_url="https://kap.org.tr/x",
            underlying_source_type="kap_disclosure",
            post_kind="original",
        )
        account = SimpleNamespace(
            handle="test_finans",
            display_name="Test Finans",
            source_type="financial_media",
            trust_score=Decimal("0.750"),
        )
        main_query = MagicMock()
        main_query.join.return_value = main_query
        main_query.filter.return_value = main_query
        main_query.order_by.return_value = main_query
        main_query.limit.return_value = main_query
        main_query.all.return_value = [(post, account)]
        relation_query = MagicMock()
        relation_query.filter.return_value = relation_query
        relation_query.order_by.return_value = relation_query
        relation_query.all.return_value = [
            SimpleNamespace(post_id="p1", canonical_symbol="THYAO")
        ]
        db = MagicMock(spec=Session)
        db.query.side_effect = [main_query, relation_query]
        product = SimpleNamespace(id="prod-thy")
        mocker.patch.object(market_service, "resolve_symbol", return_value=product)

        rows = social_service.list_signals(
            db,
            symbol="Türk Hava Yolları",
            since_hours=24,
            limit=20,
            minimum_trust_score=0.5,
            verification_status="unverified",
            source_type="financial_media",
        )
        assert rows[0]["matchedSymbols"] == ["THYAO"]
        assert rows[0]["trustScore"] == 0.75
        assert "raw_metadata" not in rows[0]
        main_query.limit.assert_called_once_with(20)

    def test_unknown_symbol_is_an_empty_valid_result(self, mocker):
        db = MagicMock(spec=Session)
        mocker.patch.object(market_service, "resolve_symbol", return_value=None)
        assert (
            social_service.list_signals(
                db,
                symbol="unknown",
                since_hours=24,
                limit=20,
                minimum_trust_score=None,
                verification_status=None,
                source_type=None,
            )
            == []
        )

    def test_empty_results_do_not_query_relations(self):
        main_query = MagicMock()
        main_query.join.return_value = main_query
        main_query.filter.return_value = main_query
        main_query.order_by.return_value = main_query
        main_query.limit.return_value = main_query
        main_query.all.return_value = []
        db = MagicMock(spec=Session)
        db.query.return_value = main_query
        assert (
            social_service.list_signals(
                db,
                symbol=None,
                since_hours=12,
                limit=5,
                minimum_trust_score=None,
                verification_status=None,
                source_type=None,
            )
            == []
        )
