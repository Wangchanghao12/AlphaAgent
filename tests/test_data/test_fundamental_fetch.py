"""fundamental_fetch 单元测试（不调用 Tushare API）。"""

from __future__ import annotations

import pandas as pd
import pytest

from alphaagent.data.fundamental_fetch import (
    disclosure_events_to_wide,
    merge_disclosure_wide,
    merge_quarterly,
    quarter_periods_between,
    raw_fina_to_disclosure_events,
    raw_fina_to_quarterly,
)


def test_quarter_periods_between():
    periods = quarter_periods_between("2020-01-01", "2020-12-31")
    assert periods == ["20200331", "20200630", "20200930", "20201231"]

    partial = quarter_periods_between("2020-04-01", "2020-09-30")
    assert partial == ["20200630", "20200930"]

    cross_year = quarter_periods_between("2023-07-01", "2024-03-31")
    assert cross_year == ["20230930", "20231231", "20240331"]


def test_quarter_periods_between_invalid_range():
    with pytest.raises(ValueError, match="start 不能晚于 end"):
        quarter_periods_between("2024-12-31", "2024-01-01")


def test_raw_fina_to_quarterly_and_disclosure():
    raw = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000001.SZ"],
            "ann_date": ["20240428", "20240830"],
            "end_date": ["20240331", "20240630"],
            "roe": [0.12, 0.15],
            "debt_to_assets": [0.5, 0.48],
        }
    )
    q = raw_fina_to_quarterly(raw)
    assert q.index.names == ["report_end", "instrument"]
    assert "funda_roe" in q.columns
    assert q.loc[(pd.Timestamp("2024-03-31"), "000001.SZ"), "funda_roe"] == 0.12

    events = raw_fina_to_disclosure_events(raw)
    wide = disclosure_events_to_wide(events)
    assert wide.loc[pd.Timestamp("2024-03-31"), "000001.SZ"] == pd.Timestamp("2024-04-28")


def test_merge_quarterly_and_disclosure():
    idx1 = pd.MultiIndex.from_tuples(
        [("2023-12-31", "000001.SZ")],
        names=["report_end", "instrument"],
    )
    idx2 = pd.MultiIndex.from_tuples(
        [("2024-03-31", "000001.SZ")],
        names=["report_end", "instrument"],
    )
    a = pd.DataFrame({"funda_roe": [0.1]}, index=idx1)
    b = pd.DataFrame({"funda_roe": [0.2]}, index=idx2)
    merged = merge_quarterly(a, b)
    assert len(merged) == 2

    w1 = pd.DataFrame({"000001.SZ": [pd.Timestamp("2024-01-10")]}, index=[pd.Timestamp("2023-12-31")])
    w2 = pd.DataFrame({"000001.SZ": [pd.Timestamp("2024-04-28")]}, index=[pd.Timestamp("2024-03-31")])
    w = merge_disclosure_wide(w1, w2)
    assert w.shape == (2, 1)
