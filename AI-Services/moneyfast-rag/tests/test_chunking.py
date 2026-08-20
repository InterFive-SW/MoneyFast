"""Document splitting."""

from __future__ import annotations

import pytest

import chunking


class TestSplit:
    def test_paragraphs_are_packed_up_to_the_limit(self):
        text = "\n\n".join(["a" * 300, "b" * 300, "c" * 300])
        chunks = chunking.split(text, max_chars=700)
        assert len(chunks) == 2
        assert chunks[0].startswith("a")

    def test_oversized_paragraph_is_windowed_with_overlap(self):
        chunks = chunking.split("x" * 500, max_chars=200, overlap=50)
        # Windows advance by max_chars - overlap = 150.
        assert [len(chunk) for chunk in chunks] == [200, 200, 200, 50]

    def test_overlap_actually_repeats_content(self):
        text = "".join(chr(ord("a") + i % 26) for i in range(400))
        chunks = chunking.split(text, max_chars=200, overlap=50)
        assert chunks[0][-50:] == chunks[1][:50]

    def test_blank_paragraphs_are_dropped(self):
        assert chunking.split("ilk\n\n   \n\nikinci") == ["ilk\n\nikinci"]

    def test_empty_text_produces_no_chunks(self):
        assert chunking.split("   ") == []

    def test_overlap_at_or_above_max_chars_is_rejected(self):
        """Would loop forever: the window advances by max_chars - overlap."""
        with pytest.raises(ValueError, match="overlap must be smaller"):
            chunking.split("herhangi bir metin", max_chars=100, overlap=100)
