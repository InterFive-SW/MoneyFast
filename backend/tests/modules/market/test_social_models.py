from pathlib import Path

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from app.modules.market.models import (
    SocialAccount,
    SocialPost,
    SocialPostInstrument,
)


def _names(table, kind):
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, kind)
    }


def test_social_account_constraints_cover_identity_and_trust():
    uniques = _names(SocialAccount.__table__, UniqueConstraint)
    checks = _names(SocialAccount.__table__, CheckConstraint)
    assert "uq_social_accounts_platform_external" in uniques
    assert "uq_social_accounts_platform_handle" in uniques
    assert {
        "ck_social_accounts_platform",
        "ck_social_accounts_source_type",
        "ck_social_accounts_trust_score",
    } <= checks


def test_social_post_constraints_cover_identity_content_and_labels():
    uniques = _names(SocialPost.__table__, UniqueConstraint)
    checks = _names(SocialPost.__table__, CheckConstraint)
    assert "uq_social_posts_platform_external" in uniques
    assert {
        "ck_social_posts_active_content",
        "ck_social_posts_kind",
        "ck_social_posts_verification",
    } <= checks


def test_relation_has_unique_pair_and_explicit_cascades():
    assert "uq_social_post_instruments_post_product" in _names(
        SocialPostInstrument.__table__, UniqueConstraint
    )
    foreign_keys = {
        tuple(constraint.column_keys): constraint.ondelete
        for constraint in SocialPostInstrument.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert foreign_keys[("post_id",)] == "CASCADE"
    assert foreign_keys[("product_id",)] == "RESTRICT"


def test_migration_chain_and_required_ddl_are_present():
    source = (
        Path(__file__).parents[3] / "alembic" / "versions" / "0012_social_signals.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0012"' in source
    assert 'down_revision: Union[str, None] = "0011"' in source
    for required in (
        "social_accounts",
        "social_posts",
        "social_post_instruments",
        "ck_social_posts_active_content",
        "uq_social_posts_platform_external",
    ):
        assert required in source
