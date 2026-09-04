"""Piyasa taban verisinin yükleyicisi, her backend açılışında çalışıyor.

`--cov=app` kapısının dışında (`scripts/` altında) ama her açılışta canlı
veritabanına yazıyor. Buradaki iddialar, "her açılışta çalışması güvenli"
sözünün gerçekten tutup tutmadığına karar veren şeyler.
"""

from __future__ import annotations

import csv
import gzip
import io
from unittest.mock import MagicMock

import pytest

from scripts import load_market


def write_csv(path, header, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    path.write_bytes(gzip.compress(buffer.getvalue().encode("utf-8"), 9, mtime=0))


@pytest.fixture
def seed_dir(tmp_path, monkeypatch):
    directory = tmp_path / "market"
    directory.mkdir()
    monkeypatch.setattr(load_market, "SEED_DIR", directory)
    return directory


@pytest.fixture
def db():
    return MagicMock()


class TestReading:
    def test_an_empty_cell_becomes_none_not_an_empty_string(self, seed_dir):
        """CSV boş hücre ile boş metni ayırt etmiyor ve fark büyük: `''` bir
        sayı sütununa yazılamaz ve bir marj sütununda 0 diye okunabilir."""
        path = seed_dir / "x.csv.gz"
        write_csv(path, ("symbol", "gross_margin"), [("AKBNK", "")])

        rows = list(load_market._rows(path))

        assert rows[0]["gross_margin"] is None

    def test_a_present_zero_survives(self, seed_dir):
        path = seed_dir / "x.csv.gz"
        write_csv(path, ("symbol", "beta"), [("THYAO", "0")])
        assert list(load_market._rows(path))[0]["beta"] == "0"


class TestFundamentals:
    def test_a_symbol_this_clone_does_not_have_is_skipped(self, seed_dir, db):
        """Migration'lar evreni değiştirdiğinde dump'ın eskimesi normal;
        olmayan bir sembol için foreign key hatası almak değil."""
        write_csv(
            seed_dir / "fundamentals.csv.gz",
            ("symbol", *load_market.FUNDAMENTAL_COLUMNS),
            [("YOKBOYLE", *[""] * len(load_market.FUNDAMENTAL_COLUMNS))],
        )

        assert load_market.load_fundamentals(db, {"THYAO": "p-1"}) == 0
        assert db.execute.called is False

    def test_rows_are_bound_by_symbol_not_id(self, seed_dir, db):
        """Enstrüman id'leri her makinede farklı (`gen_random_uuid()`); id
        taşıyan bir satır başkasının veritabanında foreign key hatası
        verirdi."""
        write_csv(
            seed_dir / "fundamentals.csv.gz",
            ("symbol", *load_market.FUNDAMENTAL_COLUMNS),
            [("THYAO", *[""] * len(load_market.FUNDAMENTAL_COLUMNS))],
        )

        assert load_market.load_fundamentals(db, {"THYAO": "p-1"}) == 1
        payload = db.execute.call_args.args[1]
        assert payload[0]["pid"] == "p-1"

    def test_a_missing_file_is_not_an_error(self, seed_dir, db):
        """Dosyalar commit'lenmeden önceki hâl budur ve uygulama yine de
        açılmak zorunda."""
        assert load_market.load_fundamentals(db, {"THYAO": "p-1"}) == 0


class TestCandles:
    def _write(self, seed_dir, count):
        write_csv(
            seed_dir / "candles.csv.gz",
            ("symbol", "timestamp", "open", "high", "low", "close", "volume"),
            [("THYAO", f"2026-01-{i % 28 + 1:02d}", 1, 2, 0, 1, 10) for i in range(count)],
        )

    def _cursor(self, db):
        cursor = MagicMock()
        db.connection.return_value.connection.cursor.return_value.__enter__ \
            .return_value = cursor
        return cursor

    def test_bars_go_through_copy_not_row_by_row(self, seed_dir, db):
        """Satır satır INSERT ile ölçüldü: 505.563 bar 135 saniye ve o süre
        boyunca backend hiç açılmıyor -- giriş bile yapılamayan iki dakikalık
        bir bekleme, boş ekranlardan daha kötü bir ilk açılış."""
        cursor = self._cursor(db)
        self._write(seed_dir, 25)

        assert load_market.load_candles(db, {"THYAO": "p-1"}) == 25
        assert cursor.copy_expert.called
        copied = cursor.copy_expert.call_args.args[1].getvalue()
        assert copied.count("\n") == 25

    def test_the_conflict_clause_survives_the_copy(self, seed_dir, db):
        """COPY doğrudan `ON CONFLICT` kabul etmiyor; iki adım tam bu yüzden.
        Tekrar çalıştırma yine hiçbir şey yazmamalı."""
        cursor = self._cursor(db)
        self._write(seed_dir, 3)

        load_market.load_candles(db, {"THYAO": "p-1"})

        statements = " ".join(c.args[0] for c in cursor.execute.call_args_list)
        assert "CREATE TEMP TABLE" in statements
        assert "ON COMMIT DROP" in statements
        assert "ON CONFLICT ON CONSTRAINT uq_market_candles_bar DO NOTHING" in statements

    def test_only_resolved_ids_reach_the_database(self, seed_dir, db):
        """Semboller SQL'e hiç girmiyor; eşleme Python tarafında."""
        cursor = self._cursor(db)
        self._write(seed_dir, 2)

        load_market.load_candles(db, {"THYAO": "p-1"})

        copied = cursor.copy_expert.call_args.args[1].getvalue()
        assert "p-1" in copied
        assert "THYAO" not in copied

    def test_an_unknown_symbol_is_skipped(self, seed_dir, db):
        self._cursor(db)
        self._write(seed_dir, 3)
        assert load_market.load_candles(db, {"BASKA": "p-9"}) == 0

    def test_nothing_to_copy_makes_no_query(self, seed_dir, db):
        cursor = self._cursor(db)
        self._write(seed_dir, 3)

        load_market.load_candles(db, {"BASKA": "p-9"})

        assert cursor.copy_expert.called is False

    def test_a_missing_file_is_not_an_error(self, seed_dir, db):
        assert load_market.load_candles(db, {"THYAO": "p-1"}) == 0


class TestNews:
    HEADER = ("content_hash", "title", "summary", "source", "url", "language",
              "related_symbols", "published_at")

    def _write(self, seed_dir, rows):
        write_csv(seed_dir / "news.csv.gz", self.HEADER, rows)

    def _cursor(self, db):
        cursor = MagicMock()
        db.connection.return_value.connection.cursor.return_value.__enter__ \
            .return_value = cursor
        return cursor

    def _row(self, index=1, symbols="THYAO", url=None):
        return (
            str(index) * 64, f"THYAO — bildirim {index}", "Şirket · Form",
            "KAP", url or f"https://www.kap.org.tr/tr/Bildirim/{index}",
            "tr", symbols, "2026-08-28T20:15:00+00:00",
        )

    def test_disclosures_go_through_copy_not_row_by_row(self, seed_dir, db):
        """~28.900 satır. Tek tek INSERT etmek, backend'in açılmasını
        bekleten saniyeler demek -- mumlarda ölçülen hatanın aynısı."""
        cursor = self._cursor(db)
        self._write(seed_dir, [self._row(i) for i in range(30)])

        assert load_market.load_news(db) == 30
        assert cursor.copy_expert.called
        assert cursor.copy_expert.call_args.args[1].getvalue().count("\n") == 30

    def test_the_conflict_clause_survives_the_copy(self, seed_dir, db):
        """Yeniden çalıştırmak hiçbir şey yazmamalı."""
        cursor = self._cursor(db)
        self._write(seed_dir, [self._row()])
        load_market.load_news(db)
        statement = cursor.execute.call_args.args[0]
        assert "ON CONFLICT (content_hash) DO NOTHING" in statement

    def test_symbols_become_a_postgres_array(self, seed_dir, db):
        cursor = self._cursor(db)
        self._write(seed_dir, [self._row(symbols="ASELS TUPRS")])
        load_market.load_news(db)
        assert "{ASELS,TUPRS}" in cursor.copy_expert.call_args.args[1].getvalue()

    def test_a_disclosure_naming_no_symbol_still_loads(self, seed_dir, db):
        cursor = self._cursor(db)
        self._write(seed_dir, [self._row(symbols="")])
        assert load_market.load_news(db) == 1
        assert "{}" in cursor.copy_expert.call_args.args[1].getvalue()

    def test_a_symbol_this_clone_does_not_carry_is_still_loaded(self, seed_dir, db):
        """Mumların aksine: haberler enstrümana foreign key ile bağlı değil,
        `related_symbols` bir metin dizisi. Evrende olmayan bir sembolü anan
        bildirim yine okunur ve bağlantısı yine çalışır, o yüzden atılmaz."""
        cursor = self._cursor(db)
        self._write(seed_dir, [self._row(symbols="YOKBOYLE")])
        assert load_market.load_news(db) == 1

    def test_an_empty_file_makes_no_query(self, seed_dir, db):
        cursor = self._cursor(db)
        self._write(seed_dir, [])
        assert load_market.load_news(db) == 0
        assert cursor.copy_expert.called is False

    def test_a_missing_file_is_not_an_error(self, seed_dir, db):
        assert load_market.load_news(db) == 0

    def test_a_full_table_skips_the_load(self, seed_dir, db):
        """Künye kontrolü: onsuz her açılış 27.500 satırı geçici tabloya
        kopyalayıp hiçbir şey yazmadan atardı."""
        cursor = self._cursor(db)
        self._write(seed_dir, [self._row()])
        db.execute.return_value.scalar.return_value = 27_541
        assert load_market.load_news(db, expected=27_541) == 0
        assert cursor.copy_expert.called is False

    def test_the_skip_check_counts_only_kap_rows(self, seed_dir, db):
        """RSS haberleri aynı tabloda. Onları da saymak, RSS yeterince
        biriktiğinde bildirim tohumunun hiç yüklenmemesi demekti."""
        self._write(seed_dir, [self._row()])
        db.execute.return_value.scalar.return_value = 0
        load_market.load_news(db, expected=27_541)
        assert "source = 'KAP'" in str(db.execute.call_args_list[0].args[0])


class TestAlreadyLoaded:
    """Künye kontrolü.

    Onsuz her yeniden başlatma 505 bin satırı geçici tabloya kopyalayıp
    hiçbir şey yazmadan atıyordu: ölçülen 30 saniye, her açılışta, tamamen
    boşuna.
    """

    def test_a_full_table_skips_the_load(self, seed_dir, db):
        write_csv(
            seed_dir / "fundamentals.csv.gz",
            ("symbol", *load_market.FUNDAMENTAL_COLUMNS),
            [("THYAO", *[""] * len(load_market.FUNDAMENTAL_COLUMNS))],
        )
        db.execute.return_value.scalar.return_value = 1011

        assert load_market.load_fundamentals(db, {"THYAO": "p-1"}, expected=1011) == 0

    def test_a_partial_table_is_completed(self, seed_dir, db):
        """Küçükse yükleme yarım kalmış demektir ve tekrar denenmeli."""
        write_csv(
            seed_dir / "fundamentals.csv.gz",
            ("symbol", *load_market.FUNDAMENTAL_COLUMNS),
            [("THYAO", *[""] * len(load_market.FUNDAMENTAL_COLUMNS))],
        )
        db.execute.return_value.scalar.return_value = 500

        assert load_market.load_fundamentals(db, {"THYAO": "p-1"}, expected=1011) == 1

    def test_more_rows_than_expected_still_counts_as_loaded(self, db):
        """İngestor dump'ın üstüne yazmaya devam ediyor; dolu bir
        veritabanında satır sayısı beklenenden BÜYÜK olur."""
        db.execute.return_value.scalar.return_value = 729_921
        assert load_market._already_loaded(db, "t", 505_563) is True

    def test_no_manifest_means_try_everything(self, db):
        """Eski bir dump ile açılan bir klonda doğru davranış bu."""
        assert load_market._already_loaded(db, "t", 0) is False

    def test_a_missing_manifest_is_not_an_error(self, seed_dir):
        assert load_market._expected() == {}

    def test_a_corrupt_manifest_is_not_an_error(self, seed_dir):
        (seed_dir / "manifest.json").write_text("bu json değil", encoding="utf-8")
        assert load_market._expected() == {}

    def test_the_manifest_is_read(self, seed_dir):
        (seed_dir / "manifest.json").write_text(
            '{"fundamentals": 1011, "candles": 505563}', encoding="utf-8"
        )
        assert load_market._expected()["candles"] == 505563


class TestMain:
    def test_a_missing_directory_is_not_an_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(load_market, "SEED_DIR", tmp_path / "yok")
        assert load_market.main() == 0

    def test_an_empty_universe_skips_rather_than_failing(
        self, seed_dir, monkeypatch
    ):
        """Migration'lar henüz çalışmadıysa bağlanacak enstrüman yoktur."""
        monkeypatch.setattr(load_market, "SessionLocal", lambda: MagicMock())
        monkeypatch.setattr(load_market, "_symbol_ids", lambda db: {})
        assert load_market.main() == 0

    def test_it_loads_both_files(self, seed_dir, monkeypatch):
        monkeypatch.setattr(load_market, "SessionLocal", lambda: MagicMock())
        monkeypatch.setattr(load_market, "_symbol_ids", lambda db: {"THYAO": "p-1"})
        loaded = []
        monkeypatch.setattr(
            load_market, "load_fundamentals",
            lambda db, ids, expected=0: loaded.append("f") or 1,
        )
        monkeypatch.setattr(
            load_market, "load_candles",
            lambda db, ids, expected=0: loaded.append("c") or 2,
        )

        assert load_market.main() == 0
        assert loaded == ["f", "c"]
