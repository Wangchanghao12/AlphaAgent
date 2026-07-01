"""data 模块测试。"""



import numpy as np
import pandas as pd

from seekalpha.core.types import OUTPUT_COLUMNS
from seekalpha.data.panel import (

    _expand_update_dates,

    _group_contiguous_trade_dates,

    _merge_raw_daily,

    _panel_missing_trade_dates,

    _rederive_since,

    _select_daily_basic,

    build_panel_from_hq,

    count_suspect_adjfactor_rows,

    find_adjfactor_jump_instruments,

    find_suspect_adjfactor_instruments,

    save_panel,

    load_panel,

    slice_panel,

)

from seekalpha.data.universe import apply_is_st, mark_not_st





def test_output_columns(mini_panel):

    assert list(mini_panel.columns) == OUTPUT_COLUMNS





def test_find_suspect_adjfactor_instruments(mini_panel):

    suspects = find_suspect_adjfactor_instruments(mini_panel)

    assert suspects == []



def test_find_suspect_adjfactor_detects_bad_stock():

    idx = pd.MultiIndex.from_product(

        [pd.date_range("2024-01-02", periods=3, freq="B"), ["X.SH"]],

        names=["datetime", "instrument"],

    )

    panel = pd.DataFrame(

        {

            "open": [10.0, 10.0, 10.0],

            "high": [10.5, 10.5, 10.5],

            "low": [9.5, 9.5, 9.5],

            "close": [10.0, 10.0, 10.0],

            "adjfactor": [1.0, 1.0, 2.0],

            "volume": [1000.0, 1000.0, 1000.0],

            "amount": [10000.0, 10000.0, 10000.0],

        },

        index=idx,

    )

    assert find_suspect_adjfactor_instruments(panel) == ["X.SH"]

    assert count_suspect_adjfactor_rows(panel, ["X.SH"]) == 2





def test_find_adjfactor_jump_detects_regime_break():

    idx = pd.MultiIndex.from_product(

        [pd.date_range("2024-01-02", periods=4, freq="B"), ["Y.SH"]],

        names=["datetime", "instrument"],

    )

    panel = pd.DataFrame(

        {

            "close": [10.0, 10.1, 10.0, 10.2],

            "adjfactor": [1.0, 1.0, 5764.0, 5764.0],

        },

        index=idx,

    )

    assert find_adjfactor_jump_instruments(panel) == ["Y.SH"]





def test_build_panel_from_hq_shape(mini_hq):

    panel = build_panel_from_hq(mini_hq, universe_mask=False)

    assert panel.shape[0] == mini_hq.shape[0]

    assert "adj_close" in panel.columns

    assert "adj_vwap" in panel.columns

    assert "ret" in panel.columns





def test_adj_vwap_matches_vwap_times_adjfactor(mini_hq):

    panel = build_panel_from_hq(mini_hq, universe_mask=False)

    expected = panel["vwap"] * panel["adjfactor"]

    np.testing.assert_allclose(panel["adj_vwap"], expected, rtol=1e-6, equal_nan=True)

    # adj_vwap / adj_close 与 vwap / close 同比例（与 OHLC 复权一致）

    ratio_v = (panel["vwap"] / panel["close"]).replace([np.inf, -np.inf], np.nan)

    ratio_a = (panel["adj_vwap"] / panel["adj_close"]).replace([np.inf, -np.inf], np.nan)

    np.testing.assert_allclose(ratio_v, ratio_a, rtol=1e-5, equal_nan=True)





def test_slice_panel(mini_panel):

    sliced = slice_panel(mini_panel, start="2024-01-03", end="2024-01-04")

    dt = sliced.index.get_level_values("datetime")

    assert dt.min() >= pd.Timestamp("2024-01-03")

    assert dt.max() <= pd.Timestamp("2024-01-04")





def test_mark_not_st():

    names = pd.Series(["平安银行", "ST某某", "*ST测试"])

    flags = mark_not_st(names)

    assert flags.tolist() == [1, 0, 0]





def test_apply_is_st():

    df = pd.DataFrame(

        {

            "ts_code": ["000001.SZ", "000002.SZ", "600000.SH"],

            "trade_date": ["20240102", "20240102", "20240102"],

            "close": [1.0, 2.0, 3.0],

        }

    )

    st_table = pd.DataFrame(

        {"ts_code": ["000002.SZ"], "trade_date": ["20240102"], "is_st": [1]}

    )

    out = apply_is_st(df, st_table)

    assert out["is_st"].tolist() == [0, 1, 0]

    assert out["not_st"].tolist() == [1, 0, 1]





def test_select_daily_basic_filters_codes():

    basic = pd.DataFrame(

        {

            "ts_code": ["000001.SZ", "000002.SZ", "600000.SH"],

            "trade_date": ["20240102", "20240102", "20240102"],

            "circ_mv": [100.0, 200.0, 300.0],

            "total_mv": [110.0, 220.0, 330.0],

        }

    )

    out = _select_daily_basic(basic, ["000001.SZ", "600000.SH"])

    assert len(out) == 2

    assert set(out["ts_code"]) == {"000001.SZ", "600000.SH"}





def test_merge_raw_daily_sets_float_cap_from_circ_mv():

    daily = pd.DataFrame(

        {

            "ts_code": ["000001.SZ"],

            "trade_date": ["20240102"],

            "open": [10.0],

            "high": [11.0],

            "low": [9.0],

            "close": [10.5],

            "vol": [1000.0],

            "amount": [10500.0],

        }

    )

    adj = pd.DataFrame(

        {"ts_code": ["000001.SZ"], "trade_date": ["20240102"], "adj_factor": [1.0]}

    )

    basic = pd.DataFrame(

        {

            "ts_code": ["000001.SZ"],

            "trade_date": ["20240102"],

            "circ_mv": [123.45],

            "total_mv": [234.56],

        }

    )

    st_table = pd.DataFrame(columns=["ts_code", "trade_date", "is_st"])

    out = _merge_raw_daily(daily, adj, basic, st_table)

    assert out.loc[(pd.Timestamp("2024-01-02"), "000001.SZ"), "float_cap"] == 123.45 * 10000





def test_rederive_since_fills_ret_on_appended_day(mini_hq):

    first = build_panel_from_hq(mini_hq.iloc[:6], universe_mask=False)

    last_day = mini_hq.iloc[6:9]

    appended = build_panel_from_hq(last_day, universe_mask=False)

    # 模拟增量：追加日 ret 在孤立计算下会是 NaN

    assert pd.isna(appended["ret"]).all()



    merged = pd.concat([first, appended]).sort_index()

    merged = merged[~merged.index.duplicated(keep="last")]

    since = appended.index.get_level_values("datetime").min()

    fixed = _rederive_since(merged, since)



    new_dt = since

    inst = "000001.SZ"

    idx = (new_dt, inst)

    assert np.isfinite(fixed.loc[idx, "ret"])





def test_expand_update_dates_includes_prev_trade_day():

    class FakePro:

        def trade_cal(self, **kwargs):

            return pd.DataFrame({"cal_date": ["20240102", "20240103", "20240104"]})



    fetch, backfill = _expand_update_dates(FakePro(), ["2024-01-04"])

    assert fetch == ["2024-01-03", "2024-01-04"]

    assert backfill == "2024-01-03"





class _FakeTradeCalPro:
    OPEN = ["20240102", "20240103", "20240104", "20240105"]

    def trade_cal(self, **kwargs):
        start = kwargs["start_date"]
        end = kwargs["end_date"]
        days = [d for d in self.OPEN if start <= d <= end]
        return pd.DataFrame({"cal_date": days})





def test_panel_missing_trade_dates_detects_internal_gap():
    pro = _FakeTradeCalPro()
    idx = pd.MultiIndex.from_product(
        [
            pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-05"]),
            ["000001.SZ"],
        ],
        names=["datetime", "instrument"],
    )
    panel = pd.DataFrame({"adj_close": [1.0, 1.1, 1.2]}, index=idx)
    missing = _panel_missing_trade_dates(pro, panel, "2024-01-05")
    assert missing == ["2024-01-04"]





def test_group_contiguous_trade_dates():
    pro = _FakeTradeCalPro()
    ranges = _group_contiguous_trade_dates(
        pro,
        ["2024-01-02", "2024-01-03", "2024-01-05"],
    )
    assert ranges == [("2024-01-02", "2024-01-03"), ("2024-01-05", "2024-01-05")]





def test_panel_gap_update_dates_fills_after_panel_max():
    pro = _FakeTradeCalPro()
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-03"]), ["000001.SZ"]],
        names=["datetime", "instrument"],
    )
    panel = pd.DataFrame({"adj_close": [1.0]}, index=idx)
    missing = _panel_missing_trade_dates(pro, panel, "2024-01-05")
    assert missing == ["2024-01-04", "2024-01-05"]





def test_panel_missing_trade_dates_empty_when_already_latest():
    pro = _FakeTradeCalPro()
    idx = pd.MultiIndex.from_product(
        [
            pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
            ["000001.SZ"],
        ],
        names=["datetime", "instrument"],
    )
    panel = pd.DataFrame({"adj_close": [1.0, 1.1, 1.2, 1.3]}, index=idx)
    missing = _panel_missing_trade_dates(pro, panel, "2024-01-05")
    assert missing == []





def test_label_nd_close_to_close_formula():
    dates = pd.date_range("2024-01-02", periods=15, freq="B")
    closes = np.arange(10.0, 25.0)  # 10, 11, ..., 24
    idx = pd.MultiIndex.from_product([dates, ["X.SH"]], names=["datetime", "instrument"])
    panel = pd.DataFrame({"adj_close": closes}, index=idx)

    from seekalpha.data.panel import _calc_label_nd_close_to_close

    label_1d = _calc_label_nd_close_to_close(panel["adj_close"], 1)
    # T=day0: (close[T+2]-close[T+1])/(close[T+1]) = (12-11)/11
    assert np.isclose(label_1d.iloc[0], (12.0 - 11.0) / 11.0)

    label_10d = _calc_label_nd_close_to_close(panel["adj_close"], 10)
    # T=day0: (close[T+11]-close[T+1])/(close[T+1]) = (21-11)/11
    assert np.isclose(label_10d.iloc[0], (21.0 - 11.0) / 11.0)
    assert label_10d.iloc[-10:].isna().all()


def test_save_load_panel_roundtrip(mini_panel, tmp_path):

    path = tmp_path / "panel.parquet"

    save_panel(mini_panel, path)

    loaded = load_panel(path)

    assert loaded.shape == mini_panel.shape

    assert list(loaded.columns) == list(mini_panel.columns)


