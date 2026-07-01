"""共享 pytest fixture。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def mini_hq() -> pd.DataFrame:
    """3 只股票 × 5 个交易日的原始 hq 宽表。"""
    dates = pd.date_range("2024-01-02", periods=5, freq="B")
    instruments = ["000001.SZ", "000002.SZ", "600000.SH"]
    rows = []
    for dt in dates:
        for i, inst in enumerate(instruments):
            base = 10.0 + i
            rows.append(
                {
                    "datetime": dt,
                    "instrument": inst,
                    "open": base,
                    "high": base + 0.5,
                    "low": base - 0.5,
                    "close": base + 0.1,
                    "adjfactor": 1.0,
                    "volume": 1000.0,
                    "amount": base * 1000,
                    "float_cap": 1e9,
                    "tot_cap": 2e9,
                    "is_trade": 1,
                    "not_st": 1,
                }
            )
    df = pd.DataFrame(rows).set_index(["datetime", "instrument"])
    return df.sort_index()


@pytest.fixture
def mini_panel(mini_hq: pd.DataFrame) -> pd.DataFrame:
    from seekalpha.data.panel import build_panel_from_hq

    return build_panel_from_hq(mini_hq, universe_mask=False)
