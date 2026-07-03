"""env_settings 与 StockEvalService 并行评估配置。"""

from __future__ import annotations

import pytest

from seekalpha.factor.mining.env_settings import (
    DEFAULT_MAX_PARALLEL_EVAL,
    ENV_MAX_PARALLEL_EVAL,
    parse_max_parallel_eval,
    resolve_max_parallel_eval,
)
from seekalpha.factor.mining.service import StockEvalService


def test_parse_max_parallel_eval_defaults():
    assert parse_max_parallel_eval("") == DEFAULT_MAX_PARALLEL_EVAL
    assert parse_max_parallel_eval(None) == DEFAULT_MAX_PARALLEL_EVAL
    assert parse_max_parallel_eval("4") == 4


def test_parse_max_parallel_eval_invalid():
    with pytest.raises(ValueError, match=ENV_MAX_PARALLEL_EVAL):
        parse_max_parallel_eval("0")


def test_resolve_max_parallel_eval_override():
    assert resolve_max_parallel_eval(3) == 3


def test_resolve_max_parallel_eval_env(monkeypatch):
    monkeypatch.setenv(ENV_MAX_PARALLEL_EVAL, "5")
    assert resolve_max_parallel_eval() == 5
    assert resolve_max_parallel_eval(2) == 2


def test_stock_eval_service_max_parallel_eval(monkeypatch):
    monkeypatch.delenv(ENV_MAX_PARALLEL_EVAL, raising=False)
    svc = StockEvalService(max_parallel_eval=2)
    assert svc.max_parallel_eval == 2

    svc_default = StockEvalService()
    assert svc_default.max_parallel_eval == DEFAULT_MAX_PARALLEL_EVAL
