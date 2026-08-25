"""Embedding helpers. The E5 prefixes are the load-bearing detail here."""

from __future__ import annotations

import pytest

import embeddings


class TestPrefixes:
    def test_default_model_is_symmetric_and_gets_no_prefix(self, fake_embedder):
        """paraphrase-multilingual-MiniLM never saw "query: " in training.
        Prepending one costs recall rather than adding any."""
        embeddings.embed_query("THYAO bilanço")
        embeddings.embed_passages(["THYAO bilanço"])
        assert fake_embedder.seen == ["THYAO bilanço", "THYAO bilanço"]

    def test_e5_model_gets_the_asymmetric_prefixes(self, fake_embedder, monkeypatch):
        monkeypatch.setenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
        embeddings.embed_query("THYAO bilanço")
        embeddings.embed_passages(["ilk parça"])
        assert fake_embedder.seen == ["query: THYAO bilanço", "passage: ilk parça"]

    def test_bge_model_gets_its_own_query_instruction(self, fake_embedder, monkeypatch):
        monkeypatch.setenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
        embeddings.embed_query("earnings")
        embeddings.embed_passages(["a passage"])
        assert fake_embedder.seen[0].startswith("Represent this sentence")
        assert fake_embedder.seen[1] == "a passage"

    def test_unknown_model_family_defaults_to_no_prefix(self, monkeypatch):
        """Safe direction: a spurious prefix degrades a symmetric model, while
        a missing one only forgoes an improvement."""
        monkeypatch.setenv("EMBEDDING_MODEL", "some-vendor/brand-new-model")
        assert embeddings.prefixes() == ("", "")

    def test_prefixed_query_and_passage_encodings_differ(self, fake_embedder, monkeypatch):
        monkeypatch.setenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
        assert embeddings.embed_query("aynı metin") != embeddings.embed_passages(["aynı metin"])[0]

    def test_empty_passage_list_short_circuits(self, fake_embedder):
        assert embeddings.embed_passages([]) == []
        assert fake_embedder.seen == []


class TestConfiguration:
    def test_defaults_when_unset(self):
        assert embeddings.model_name() == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        assert embeddings.dimension() == 384

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_MODEL", "some/other-model")
        monkeypatch.setenv("EMBEDDING_DIMENSION", "768")
        assert embeddings.model_name() == "some/other-model"
        assert embeddings.dimension() == 768

    def test_non_numeric_dimension_falls_back(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_DIMENSION", "not-a-number")
        assert embeddings.dimension() == 384


class TestDimensionGuard:
    def test_mismatch_names_the_model_and_the_expectation(self, fake_embedder, monkeypatch):
        """Edge case: the configured dimension and the loaded model disagree.

        Letting this reach Postgres produces an error naming neither, which is
        the kind of failure someone loses an afternoon to.
        """
        monkeypatch.setenv("EMBEDDING_DIMENSION", "1536")
        with pytest.raises(ValueError, match="produced 384 dimensions"):
            embeddings.embed_query("herhangi bir sorgu")


class TestPgvectorLiteral:
    def test_renders_bracketed_comma_list(self):
        assert embeddings.to_pgvector([0.5, -1.25]) == "[0.5,-1.25]"

    def test_integers_are_rendered_as_floats(self):
        assert embeddings.to_pgvector([1, 0]) == "[1.0,0.0]"


class TestLazyLoading:
    def test_model_is_loaded_once_and_cached(self, monkeypatch):
        """Import of fastembed is deferred so the module can be imported (and
        unit-tested) without the ONNX runtime present."""
        import sys
        import types

        loads = []

        class StubTextEmbedding:
            def __init__(self, model_name):
                loads.append(model_name)

            def embed(self, texts):
                return ([0.0] * 384 for _ in texts)

        module = types.ModuleType("fastembed")
        module.TextEmbedding = StubTextEmbedding
        monkeypatch.setitem(sys.modules, "fastembed", module)
        monkeypatch.setattr(embeddings, "_model", None)

        first = embeddings.get_model()
        second = embeddings.get_model()

        assert first is second
        assert loads == ["sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"]


class TestDoubleCheckedLocking:
    """The second `if _model is None` inside the lock.

    It exists because uvicorn serves concurrently: two cold requests can both
    pass the outer check, and without the inner one the loser would load the
    model a second time and overwrite the winner's instance. Driven
    deterministically here — a real race would make the test flaky, which is
    worse than not testing it.
    """

    def test_a_model_loaded_while_waiting_for_the_lock_is_reused(self, monkeypatch):
        sentinel = object()

        class LockThatLoadsFirst:
            """Stands in for another thread finishing the load while this one
            waits at the lock."""

            def __enter__(self):
                embeddings._model = sentinel
                return self

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(embeddings, "_model", None)
        monkeypatch.setattr(embeddings, "_lock", LockThatLoadsFirst())

        def _explode(*args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("the model was loaded twice")

        monkeypatch.setattr(embeddings, "model_name", _explode)

        assert embeddings.get_model() is sentinel

    def test_an_already_loaded_model_never_takes_the_lock(self, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(embeddings, "_model", sentinel)

        class LockThatMustNotBeUsed:
            def __enter__(self):  # pragma: no cover - must not run
                raise AssertionError("the lock was taken for a loaded model")

            def __exit__(self, *exc):  # pragma: no cover - must not run
                return False

        monkeypatch.setattr(embeddings, "_lock", LockThatMustNotBeUsed())
        assert embeddings.get_model() is sentinel
