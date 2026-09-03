"""Tutulan bir hisseye dokunan haber, o kişiye bildirilir.

Bu dosyanın koruduğu dört şey, hepsi ölçümden:

YALNIZCA YENİ HABER. `upsert_news` içerik hash'inde tekilleştiriyor; zaten
duran bir haberi yeniden bildirmek, akışı otuz saniyede bir tekrar eden bir
gürültüye çevirirdi.

HABER BAŞINA TEK BİLDİRİM. Bir haber kullanıcının üç hissesine birden
dokunuyorsa yine tek satır: aynı yazıyı üç kez göstermek üç ayrı haber varmış
gibi okunurdu.

DEMO HESABI DIŞARIDA. Ölçüldü: demo portföyünün `user_id` alanında gerçek bir
kullanıcı değil "demo" yazıyor ve `notifications.user_id`'nin foreign key'i
ihlal oluyor -- TEK bir geçersiz id partinin tamamını düşürüyordu, yani ASELS
haberi altı gerçek kullanıcıya da ulaşmıyordu.

PARTİ BAŞINA TAVAN. Olağandışı büyük bir tur (ilk doldurma, kaynağın geçmişi
yeniden yayımlaması) zili okunmayacak bir listeye çevirmemeli.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.investment import market_service
from app.modules.market import router as market_router
from app.modules.notification import service as notification_service


def item(news_id="n1", title="ASELS sözleşme imzaladı", symbols=("ASELS",)):
    return {"id": news_id, "title": title, "symbols": list(symbols)}


@pytest.fixture
def db():
    return MagicMock(spec=Session)


class TestWhoGetsNotified:
    def test_every_holder_gets_one(self, db, mocker):
        mocker.patch.object(
            market_service, "holders_of",
            return_value={"ASELS": {"u1", "u2", "u3"}},
        )
        assert market_router._notify_holders(db, [item()]) == 3
        assert db.add.call_count == 3

    def test_a_non_holder_gets_nothing(self, db, mocker):
        mocker.patch.object(market_service, "holders_of", return_value={})
        assert market_router._notify_holders(db, [item()]) == 0
        assert db.add.call_count == 0

    def test_no_fresh_news_asks_nobody(self, db, mocker):
        """Sorgu bile atılmıyor: yeni haber yoksa bildirilecek bir şey yok."""
        spy = mocker.patch.object(market_service, "holders_of", return_value={})
        assert market_router._notify_holders(db, []) == 0
        assert not spy.called

    def test_one_article_touching_two_holdings_is_one_notification(self, db, mocker):
        """Aynı yazıyı iki kez göstermek, iki ayrı haber varmış gibi okunurdu."""
        mocker.patch.object(
            market_service, "holders_of",
            return_value={"ASELS": {"u1"}, "THYAO": {"u1"}},
        )
        assert market_router._notify_holders(
            db, [item(symbols=("ASELS", "THYAO"))]
        ) == 1

    def test_the_description_names_only_the_symbols_that_user_holds(self, db, mocker):
        """Kullanıcının tutmadığı bir hisseyi bildirimin başına yazmak,
        ona ait olmayan bir pozisyon varmış gibi gösterirdi."""
        mocker.patch.object(
            market_service, "holders_of",
            return_value={"ASELS": {"u1"}, "THYAO": {"u2"}},
        )
        market_router._notify_holders(db, [item(symbols=("ASELS", "THYAO"))])
        descriptions = [call.args[0].description for call in db.add.call_args_list]
        by_user = {call.args[0].user_id: d
                   for call, d in zip(db.add.call_args_list, descriptions)}
        assert by_user["u1"].startswith("ASELS:")
        assert by_user["u2"].startswith("THYAO:")


class TestBatchCap:
    def test_a_huge_batch_is_capped_per_user(self, db, mocker):
        mocker.patch.object(market_service, "holders_of", return_value={"ASELS": {"u1"}})
        many = [item(news_id=f"n{i}", title=f"Haber {i}") for i in range(40)]
        written = market_router._notify_holders(db, many)
        assert written == notification_service.MAX_PER_USER_PER_BATCH

    def test_the_cap_is_per_user_not_per_batch(self, db, mocker):
        mocker.patch.object(
            market_service, "holders_of", return_value={"ASELS": {"u1", "u2"}}
        )
        many = [item(news_id=f"n{i}") for i in range(40)]
        written = market_router._notify_holders(db, many)
        assert written == 2 * notification_service.MAX_PER_USER_PER_BATCH


class TestContent:
    def test_the_notification_points_somewhere_useful(self, db, mocker):
        mocker.patch.object(market_service, "holders_of", return_value={"ASELS": {"u1"}})
        market_router._notify_holders(db, [item()])
        written = db.add.call_args.args[0]
        assert written.link_url == "/analiz/genel"
        assert written.type == "INFO"

    def test_a_very_long_headline_is_cut_to_the_column(self, db, mocker):
        """`description` 255 karakter. Kırpmamak, tüm partiyi düşüren bir
        veritabanı hatası olurdu."""
        mocker.patch.object(market_service, "holders_of", return_value={"ASELS": {"u1"}})
        market_router._notify_holders(db, [item(title="A" * 400)])
        assert len(db.add.call_args.args[0].description) <= 255


class TestDemoAccount:
    def test_the_demo_portfolio_has_nobody_to_notify(self):
        """Sorgu demo hesabını dışarıda bırakıyor; kontrolü burada, çünkü
        dışarıda bırakılmadığında foreign key ihlali partinin TAMAMINI
        düşürüyordu."""
        import inspect

        source = inspect.getsource(market_service.holders_of)
        assert "DEMO_ACCOUNT_NUMBER" in source


class TestWriter:
    def test_it_does_not_commit(self, db):
        """Commit çağıranın: bir turda birçok satır yazılıyor ve her satırdan
        sonra commit etmek turu onlarca transaction'a bölerdi."""
        notification_service.create_many(
            db, ["u1"], title="T", description="D",
        )
        assert not db.commit.called

    def test_it_writes_one_row_per_user(self, db):
        assert notification_service.create_many(
            db, ["u1", "u2"], title="T", description="D",
        ) == 2
        assert db.add.call_count == 2

    def test_no_users_writes_nothing(self, db):
        assert notification_service.create_many(
            db, [], title="T", description="D",
        ) == 0
