"""DSL 求值测试。"""

import numpy as np

from seekalpha.dsl import eval_factor


def test_ts_mean(mini_panel):
    out = eval_factor("TS_MEAN($adj_close, 3)", mini_panel)
    assert len(out) == len(mini_panel)
    assert out.notna().any()


def test_ret_expr(mini_panel):
    out = eval_factor("$ret", mini_panel)
    assert out.notna().sum() > 0


def test_cs_zscore(mini_panel):
    out = eval_factor("CS_ZSCORE($close)", mini_panel)
    assert out.notna().any()
