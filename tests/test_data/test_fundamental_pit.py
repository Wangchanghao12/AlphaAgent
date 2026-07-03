"""基本面 PIT 展开单测（不调用 Tushare API）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alphaagent.data.fundamental import (
    FUNDAMENTAL_STATEMENT_COLUMN_MAP,
    _disclosure_effective_trade_positions,
    append_disclosure_distance_features,
    enrich_panel_fundamentals,
    expand_quarterly_fundamentals_pit,
    quarter_period_start,
)
from alphaagent.data.panel import build_panel_from_hq


def _make_hq_panel(tmp_path) -> pd.DataFrame:
    """20 个交易日 × 2 只股票。"""
    dates = pd.date_range("2024-01-02", periods=20, freq="B")
    codes = ["000001.SZ", "000002.SZ"]
    rows = []
    for dt in dates:
        for i, inst in enumerate(codes):
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
    hq = pd.DataFrame(rows).set_index(["datetime", "instrument"])
    return build_panel_from_hq(hq, universe_mask=False)


def _make_disclosure_map_parquet(tmp_path):
    report_ends = pd.to_datetime(["2023-12-31", "2024-03-31"])
    wide = pd.DataFrame(
        {
            "000001.SZ": ["2024-01-10", "2024-01-24"],
            "000002.SZ": ["2024-01-12", None],
        },
        index=report_ends,
    )
    path = tmp_path / "disclosure_map.parquet"
    wide.to_parquet(path)
    return path


def _make_quarterly_fundamentals_parquet(tmp_path):
    col = FUNDAMENTAL_STATEMENT_COLUMN_MAP["总资产"]
    idx = pd.MultiIndex.from_tuples(
        [
            ("2023-12-31", "000001.SZ"),
            ("2024-03-31", "000001.SZ"),
            ("2023-12-31", "000002.SZ"),
        ],
        names=["report_end", "instrument"],
    )
    df = pd.DataFrame({col: [100.0, 120.0, 200.0]}, index=idx)
    path = tmp_path / "fundamentals.parquet"
    df.to_parquet(path)
    return path


def test_disclosure_effective_next_trade_day():
    trade_dates = pd.bdate_range("2024-04-15", "2024-04-26")
    pos = _disclosure_effective_trade_positions(
        trade_dates,
        np.array(["2024-04-20"], dtype="datetime64[ns]"),
    )
    assert trade_dates[pos[0]] == pd.Timestamp("2024-04-22")

    pos2 = _disclosure_effective_trade_positions(
        trade_dates,
        np.array(["2024-04-24"], dtype="datetime64[ns]"),
    )
    assert trade_dates[pos2[0]] == pd.Timestamp("2024-04-25")


def test_disclosure_distance_features(tmp_path):
    panel = _make_hq_panel(tmp_path)
    disc = _make_disclosure_map_parquet(tmp_path)
    panel = append_disclosure_distance_features(panel, disc)
    sub = panel.xs("000001.SZ", level="instrument").sort_index()
    assert "funda_days_to_disclose" not in panel.columns

    jan10 = sub.loc[pd.Timestamp("2024-01-10")]
    jan11 = sub.loc[pd.Timestamp("2024-01-11")]
    jan12 = sub.loc[pd.Timestamp("2024-01-12")]
    jan25 = sub.loc[pd.Timestamp("2024-01-25")]

    assert pd.isna(jan10["funda_days_since_disclose"])
    assert jan11["funda_days_since_disclose"] == 0
    assert jan12["funda_days_since_disclose"] == 1
    assert jan25["funda_days_since_disclose"] == 0


def test_expand_quarterly_fundamentals_pit(tmp_path):
    panel = _make_hq_panel(tmp_path)
    disc = _make_disclosure_map_parquet(tmp_path)
    funda = _make_quarterly_fundamentals_parquet(tmp_path)
    panel = expand_quarterly_fundamentals_pit(panel, funda, disc)

    col = "funda_fs_total_assets"
    s1 = panel.xs("000001.SZ", level="instrument").sort_index()

    assert pd.isna(s1.loc[pd.Timestamp("2024-01-10"), col])
    assert s1.loc[pd.Timestamp("2024-01-11"), col] == 100.0
    assert s1.loc[pd.Timestamp("2024-01-23"), col] == 100.0
    assert s1.loc[pd.Timestamp("2024-01-25"), col] == 120.0

    s2 = panel.xs("000002.SZ", level="instrument").sort_index()
    assert pd.isna(s2.loc[pd.Timestamp("2024-01-12"), col])
    assert s2.loc[pd.Timestamp("2024-01-15"), col] == 200.0


def test_quarter_period_start_days(tmp_path):
    panel = _make_hq_panel(tmp_path)
    disc = _make_disclosure_map_parquet(tmp_path)
    panel = enrich_panel_fundamentals(
        panel,
        quarterly_path=_make_quarterly_fundamentals_parquet(tmp_path),
        disclosure_path=disc,
    )
    sub = panel.xs("000001.SZ", level="instrument").sort_index()

    assert sub.loc[pd.Timestamp("2024-01-02"), "funda_days_since_quarter_start"] == 0
    assert sub.loc[pd.Timestamp("2024-01-03"), "funda_days_since_quarter_start"] == 1
    assert quarter_period_start(pd.Timestamp("2024-02-15")) == pd.Timestamp("2024-01-01")


def test_enrich_rejects_duplicate_funda_columns(tmp_path):
    panel = _make_hq_panel(tmp_path)
    disc = _make_disclosure_map_parquet(tmp_path)
    funda = _make_quarterly_fundamentals_parquet(tmp_path)
    panel = expand_quarterly_fundamentals_pit(panel, funda, disc)
    with pytest.raises(ValueError, match="已含基本面列"):
        expand_quarterly_fundamentals_pit(panel, funda, disc)
