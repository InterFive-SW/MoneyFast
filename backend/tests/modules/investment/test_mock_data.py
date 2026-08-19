"""Unit tests for app/modules/investment/mock_data.py::generate_data.

Fonksiyon `random.random()` ve `time.time()` kullandığı için deterministik
değil; `random.random`'ı kontrollü bir değer dizisiyle monkeypatch'leyerek
hem yeşil (is_up=True) hem kırmızı (is_up=False) mum dallarını, hem de
`days=0` kenar durumunu tetikliyoruz.
"""

from __future__ import annotations

import pytest

import app.modules.investment.mock_data as mock_data_module

UP_COLOR = "rgba(38, 166, 154, 0.5)"
DOWN_COLOR = "rgba(239, 83, 80, 0.5)"


def _patch_random_sequence(monkeypatch, values):
    """`random.random()`'ın ardışık çağrılarında sırayla `values`'ı döndürür."""
    it = iter(values)
    monkeypatch.setattr(mock_data_module.random, "random", lambda: next(it))


def test_generate_data_marks_candle_green_when_close_at_or_above_open(monkeypatch):
    # open=100, high=110, low=100, close=105 -> close >= open
    _patch_random_sequence(monkeypatch, [0.5, 1.0, 0.0, 0.5, 0.3])

    candles = mock_data_module.generate_data(days=1, start_price=100.0, volatility=10.0)

    assert len(candles) == 1
    candle = candles[0]
    assert candle["close"] >= candle["open"]
    assert candle["color"] == UP_COLOR


def test_generate_data_marks_candle_red_when_close_below_open(monkeypatch):
    # open=100, high=100, low=90, close=90 -> close < open
    _patch_random_sequence(monkeypatch, [0.5, 0.0, 1.0, 0.0, 0.7])

    candles = mock_data_module.generate_data(days=1, start_price=100.0, volatility=10.0)

    assert len(candles) == 1
    candle = candles[0]
    assert candle["close"] < candle["open"]
    assert candle["color"] == DOWN_COLOR


def test_generate_data_returns_empty_list_for_zero_days():
    assert mock_data_module.generate_data(days=0, start_price=100.0, volatility=10.0) == []


def test_generate_data_chains_close_price_into_next_days_open(monkeypatch):
    """`current_price`, bir sonraki günün open hesaplamasına taşınmalı."""
    _patch_random_sequence(monkeypatch, [0.5, 1.0, 0.0, 0.5, 0.3] * 2)

    candles = mock_data_module.generate_data(days=2, start_price=100.0, volatility=10.0)

    assert len(candles) == 2
    # İlk günün close'u 105.0; ikinci günün open'ı bu değerden türemeli
    # (open = current_price + (0.5-0.5)*10 = current_price).
    assert candles[1]["open"] == pytest.approx(105.0)
