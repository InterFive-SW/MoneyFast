"""Haber yargısı ucu.

Bu uç kullanıcıyla konuşmuyor ve grafiğe girmiyor: bir toplu iş. Backend
zamanlıyor, evreni veriyor ve sonucu saklıyor; LLM çıkışı burada kalıyor.

Sabitlenen iki şey: **evren dışı bir sembol kaydedilmiyor** (uydurmaya karşı
tek kilit; prompt "listeden seç" diyor ama prompt tavsiyedir) ve **tek bir
haberin hatası turu düşürmüyor** -- yüz haberin birinde bozuk bir JSON, tüm
partinin kaybı olmamalı.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api

URL = "/analyze/news-impact"


def _payload(items=None, universe=("ASELS", "THYAO")):
    return {
        "items": items if items is not None else [
            {"news_id": "n1", "title": "Aselsan yeni sözleşme imzaladı",
             "summary": "özet", "source": "KAP"},
        ],
        "universe": list(universe),
    }


def _rows(rows):
    return {"impacts": rows}


@pytest.fixture()
def client():
    with TestClient(api.app) as test_client:
        yield test_client


class TestCleanImpacts:
    def test_a_symbol_outside_the_universe_is_dropped(self):
        """Olmayan bir sembol için etki saklamak, ekranda bulunamayan bir
        satır demek."""
        rows = api._clean_impacts(
            [{"symbol": "YOKBOYLE", "direction": "UP", "mechanism": "x"}],
            {"ASELS"},
        )
        assert rows == []

    def test_a_symbol_is_matched_case_insensitively(self):
        rows = api._clean_impacts(
            [{"symbol": " asels ", "direction": "up", "mechanism": "sebep"}],
            {"ASELS"},
        )
        assert rows[0]["symbol"] == "ASELS" and rows[0]["direction"] == "UP"

    def test_an_unknown_direction_drops_the_row(self):
        """Sessizce nötre çevrilen bir 'BULLISH', yanlış bir yargıyı doğru
        gibi saklardı."""
        assert api._clean_impacts(
            [{"symbol": "ASELS", "direction": "BULLISH", "mechanism": "sebep"}],
            {"ASELS"},
        ) == []

    def test_a_row_without_a_mechanism_is_dropped(self):
        assert api._clean_impacts(
            [{"symbol": "ASELS", "direction": "UP", "mechanism": "  "}], {"ASELS"}
        ) == []

    def test_the_same_symbol_is_not_judged_twice(self):
        rows = api._clean_impacts([
            {"symbol": "ASELS", "direction": "UP", "mechanism": "ilk"},
            {"symbol": "ASELS", "direction": "DOWN", "mechanism": "ikinci"},
        ], {"ASELS"})
        assert len(rows) == 1 and rows[0]["mechanism"] == "ilk"

    def test_an_unknown_scope_falls_back_to_direct(self):
        rows = api._clean_impacts(
            [{"symbol": "ASELS", "direction": "UP", "mechanism": "s", "scope": "X"}],
            {"ASELS"},
        )
        assert rows[0]["scope"] == "DIRECT"

    def test_an_unknown_magnitude_falls_back_to_low(self):
        rows = api._clean_impacts(
            [{"symbol": "ASELS", "direction": "UP", "mechanism": "s",
              "magnitude": "ENORMOUS"}],
            {"ASELS"},
        )
        assert rows[0]["magnitude"] == "LOW"

    def test_a_declared_scope_and_magnitude_survive(self):
        rows = api._clean_impacts(
            [{"symbol": "ASELS", "direction": "UP", "mechanism": "s",
              "scope": "spillover", "magnitude": "high"}],
            {"ASELS"},
        )
        assert rows[0]["scope"] == "SPILLOVER" and rows[0]["magnitude"] == "HIGH"

    def test_a_confidence_outside_the_scale_is_clamped(self):
        """Kırpmak onu doğru saymak değil; tek bir alan yüzünden yargıyı
        atmak da doğru olmazdı."""
        rows = api._clean_impacts([
            {"symbol": "ASELS", "direction": "UP", "mechanism": "s", "confidence": 9},
            {"symbol": "THYAO", "direction": "UP", "mechanism": "s", "confidence": -3},
        ], {"ASELS", "THYAO"})
        assert [row["confidence"] for row in rows] == [1.0, 0.0]

    def test_a_non_numeric_confidence_falls_back(self):
        rows = api._clean_impacts(
            [{"symbol": "ASELS", "direction": "UP", "mechanism": "s",
              "confidence": "çok"}],
            {"ASELS"},
        )
        assert rows[0]["confidence"] == 0.5

    def test_a_long_mechanism_is_cut(self):
        rows = api._clean_impacts(
            [{"symbol": "ASELS", "direction": "UP", "mechanism": "a" * 900}],
            {"ASELS"},
        )
        assert len(rows[0]["mechanism"]) == api.MAX_MECHANISM_CHARS

    def test_the_row_cap_is_enforced_in_code(self):
        """Prompt da altıyı söylüyor; burası onu ZORLUYOR."""
        rows = api._clean_impacts(
            [{"symbol": f"S{index}", "direction": "UP", "mechanism": "s"}
             for index in range(20)],
            {f"S{index}" for index in range(20)},
        )
        assert len(rows) == api.MAX_IMPACTS_PER_ITEM

    def test_a_non_list_answer_is_empty(self):
        assert api._clean_impacts(None, {"ASELS"}) == []
        assert api._clean_impacts("impacts", {"ASELS"}) == []

    def test_a_non_dict_row_is_skipped(self):
        assert api._clean_impacts(["ASELS"], {"ASELS"}) == []


class TestEndpoint:
    def test_a_judged_item_comes_back_with_its_rows(self, client, mocker):
        mocker.patch.object(
            api.orchestrator, "_llm_json",
            return_value=_rows([{"symbol": "ASELS", "direction": "UP",
                                 "mechanism": "Sözleşme yıllık ihracata ekleniyor."}]),
        )
        mocker.patch.object(api.orchestrator, "model_name", return_value="test-model")
        body = client.post(URL, json=_payload()).json()
        assert body["analyzed"] == 1 and body["failed"] == 0
        assert body["model"] == "test-model"
        assert body["results"][0]["news_id"] == "n1"
        assert body["results"][0]["impacts"][0]["symbol"] == "ASELS"

    def test_one_broken_item_does_not_lose_the_batch(self, client, mocker):
        mocker.patch.object(
            api.orchestrator, "_llm_json",
            side_effect=[RuntimeError("bozuk JSON"),
                         _rows([{"symbol": "THYAO", "direction": "DOWN",
                                 "mechanism": "Yakıt maliyeti marjı daraltıyor."}])],
        )
        mocker.patch.object(api.orchestrator, "model_name", return_value="m")
        body = client.post(URL, json=_payload(items=[
            {"news_id": "n1", "title": "Bir", "summary": "", "source": ""},
            {"news_id": "n2", "title": "İki", "summary": "", "source": ""},
        ])).json()
        assert body["analyzed"] == 1 and body["failed"] == 1
        assert body["results"][0]["news_id"] == "n2"

    def test_an_empty_batch_is_not_an_error(self, client, mocker):
        mocker.patch.object(api.orchestrator, "model_name", return_value="m")
        body = client.post(URL, json=_payload(items=[])).json()
        assert body == {"analyzed": 0, "failed": 0, "model": "m", "results": []}

    def test_an_empty_universe_stores_nothing(self, client, mocker):
        """Evren boşken model ne yazarsa yazsın hiçbir satır geçmiyor."""
        mocker.patch.object(
            api.orchestrator, "_llm_json",
            return_value=_rows([{"symbol": "ASELS", "direction": "UP",
                                 "mechanism": "sebep"}]),
        )
        mocker.patch.object(api.orchestrator, "model_name", return_value="m")
        body = client.post(URL, json=_payload(universe=[])).json()
        assert body["results"][0]["impacts"] == []

    def test_blank_universe_entries_are_ignored(self, client, mocker):
        mocker.patch.object(
            api.orchestrator, "_llm_json",
            return_value=_rows([{"symbol": "ASELS", "direction": "UP",
                                 "mechanism": "sebep"}]),
        )
        mocker.patch.object(api.orchestrator, "model_name", return_value="m")
        body = client.post(URL, json=_payload(universe=["  ", "ASELS"])).json()
        assert body["results"][0]["impacts"][0]["symbol"] == "ASELS"

    def test_an_empty_answer_is_a_complete_answer(self, client, mocker):
        """Zayıf satırlarla listeyi doldurmak, bu işin en açık olduğu hata."""
        mocker.patch.object(api.orchestrator, "_llm_json", return_value={"impacts": []})
        mocker.patch.object(api.orchestrator, "model_name", return_value="m")
        body = client.post(URL, json=_payload()).json()
        assert body["analyzed"] == 1 and body["results"][0]["impacts"] == []
