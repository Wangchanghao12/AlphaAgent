"""

Panel 构建与持久化

- 历史全量：build_panel → parquet

- 实盘增量：update_panel → merge 写回

- 衍生列逻辑与 AlphaAgent-Stock 保持一致

"""



from __future__ import annotations



import time

from pathlib import Path



import numpy as np

import pandas as pd



from seekalpha.core.paths import PANEL_PATH

from seekalpha.core.types import OUTPUT_COLUMNS

from seekalpha.data.tushare_client import get_pro

from seekalpha.data.universe import (

    apply_is_st,

    fetch_index_members,

    fetch_index_members_for_dates,

    fetch_st_table,

    filter_universe,

)



DEFAULT_PANEL_PATH = PANEL_PATH



_DERIVED_COLUMNS = ("ret", "label_1d_close_to_close", "label_1d_open_to_open")





def _format_yyyymmdd(d: str) -> str:

    return d.replace("-", "")





def _coerce_datetime_index(panel: pd.DataFrame) -> pd.DataFrame:

    """确保 MultiIndex datetime 层为 DatetimeIndex。"""

    if not isinstance(panel.index, pd.MultiIndex):

        return panel

    if panel.index.names[0] != "datetime":

        return panel



    dt = panel.index.get_level_values("datetime")

    if not pd.api.types.is_datetime64_any_dtype(dt):

        dt = pd.to_datetime(dt)

        inst = panel.index.get_level_values("instrument")

        panel = panel.copy()

        panel.index = pd.MultiIndex.from_arrays(

            [dt, inst],

            names=["datetime", "instrument"],

        )

    return panel.sort_index()





def slice_panel(

    panel: pd.DataFrame,

    *,

    start: str | None = None,

    end: str | None = None,

) -> pd.DataFrame:

    """按 datetime 闭区间 [start, end] 切片。"""

    if start is None and end is None:

        return panel



    dt = panel.index.get_level_values("datetime")

    mask = pd.Series(True, index=panel.index)

    if start is not None:

        mask &= dt >= pd.Timestamp(start)

    if end is not None:

        mask &= dt <= pd.Timestamp(end)

    return panel.loc[mask]





def _calc_label_1d_open_to_open(adj_open: pd.Series) -> pd.Series:

    open_t1 = adj_open.shift(-1)

    open_t2 = adj_open.shift(-2)

    denom = open_t1.replace(0, np.nan)

    return (open_t2 - open_t1) / denom





def _calc_label_1d_close_to_close(adj_close: pd.Series) -> pd.Series:

    close_t1 = adj_close.shift(-1)

    close_t2 = adj_close.shift(-2)

    denom = close_t1.replace(0, np.nan)

    return (close_t2 - close_t1) / denom





def _derive_base_columns(df: pd.DataFrame) -> pd.DataFrame:

    """从原始行情宽表衍生 adj_*、vwap 等（不含 ret / label）。"""

    df = df.copy()

    df = df.rename_axis(index={"code": "instrument"})



    for col in ("open", "high", "low", "close"):

        df[f"adj_{col}"] = df[col] * df["adjfactor"]



    if "isTrade" in df.columns:

        df = df.rename(columns={"isTrade": "is_trade", "notST": "not_st"})



    vol = df["volume"].replace(0, np.nan)

    df["vwap"] = df["amount"] / vol

    df["adj_vwap"] = df["vwap"] * df["adjfactor"]

    return df





def _add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:

    """在完整时间序列上计算 ret / label。"""

    df = df.copy()

    df["ret"] = df.groupby(level="instrument", sort=False)["adj_close"].pct_change(

        fill_method=None

    )

    df["label_1d_close_to_close"] = df.groupby(level="instrument", sort=False)[

        "adj_close"

    ].transform(_calc_label_1d_close_to_close)

    df["label_1d_open_to_open"] = df.groupby(level="instrument", sort=False)[

        "adj_open"

    ].transform(_calc_label_1d_open_to_open)

    return df





def _finalize_panel(df: pd.DataFrame, *, dtype: str = "float32") -> pd.DataFrame:

    panel = df[OUTPUT_COLUMNS].copy()

    numeric_cols = [c for c in OUTPUT_COLUMNS if c not in ("is_trade", "not_st")]

    for col in numeric_cols:

        panel[col] = panel[col].astype(dtype)



    panel = panel.sort_index()

    panel = _coerce_datetime_index(panel)



    assert panel.index.names == ["datetime", "instrument"]

    assert not panel.index.duplicated().any()

    return panel





def _derive_panel_columns(df: pd.DataFrame, *, dtype: str = "float32") -> pd.DataFrame:

    """从原始行情宽表衍生 adj_*、ret、vwap、label 列。"""

    df = _derive_base_columns(df)

    df = _add_derived_columns(df)

    return _finalize_panel(df, dtype=dtype)





def _panel_base_from_hq(

    hq: pd.DataFrame,

    *,

    universe_mask: bool = True,

    dtype: str = "float32",

) -> pd.DataFrame:

    """hq → panel 基础列（ret / label 置 NaN，供增量 merge 后统一重算）。"""

    df = hq.copy()

    if universe_mask:

        df = filter_universe(df)

    if df.empty:

        return df



    df = _derive_base_columns(df)

    for col in _DERIVED_COLUMNS:

        df[col] = np.nan



    return _finalize_panel(df, dtype=dtype)





def _rederive_since(panel: pd.DataFrame, since: pd.Timestamp, *, dtype: str = "float32") -> pd.DataFrame:

    """基于 panel 内 adj 列，从 since 起重算 ret / label（用全历史 groupby，避免前视缺失）。"""

    if panel.empty:

        return panel



    panel = panel.copy()

    since = pd.Timestamp(since)

    dt = panel.index.get_level_values("datetime")

    mask = dt >= since

    if not mask.any():

        return panel



    full_ret = panel.groupby(level="instrument", sort=False)["adj_close"].pct_change(

        fill_method=None

    )

    full_label_c = panel.groupby(level="instrument", sort=False)["adj_close"].transform(

        _calc_label_1d_close_to_close

    )

    full_label_o = panel.groupby(level="instrument", sort=False)["adj_open"].transform(

        _calc_label_1d_open_to_open

    )



    panel.loc[mask, "ret"] = full_ret.loc[mask].astype(dtype)

    panel.loc[mask, "label_1d_close_to_close"] = full_label_c.loc[mask].astype(dtype)

    panel.loc[mask, "label_1d_open_to_open"] = full_label_o.loc[mask].astype(dtype)

    return panel





def build_panel_from_hq(

    hq: pd.DataFrame,

    *,

    start: str | None = None,

    end: str | None = None,

    universe_mask: bool = True,

    dtype: str = "float32",

) -> pd.DataFrame:

    """从 (datetime, code) 行情宽表构建 panel。"""

    df = hq.copy()

    if start is not None or end is not None:

        dt = pd.to_datetime(df.index.get_level_values(0))

        mask = pd.Series(True, index=df.index)

        if start is not None:

            mask &= dt >= pd.Timestamp(start)

        if end is not None:

            mask &= dt <= pd.Timestamp(end)

        df = df.loc[mask]



    if universe_mask:

        df = filter_universe(df)



    if df.empty:

        return df



    df = _derive_base_columns(df)

    df = _add_derived_columns(df)

    return _finalize_panel(df, dtype=dtype)





def _fetch_trade_dates(pro, start: str, end: str) -> list[str]:

    cal = pro.trade_cal(

        exchange="SSE",

        start_date=_format_yyyymmdd(start),

        end_date=_format_yyyymmdd(end),

        is_open="1",

    )

    return sorted(cal["cal_date"].tolist())





def _prev_trade_date(pro, date: str) -> str | None:

    """给定 YYYY-MM-DD 或 YYYYMMDD，返回上一个交易日 YYYY-MM-DD。"""

    td = _format_yyyymmdd(date)

    cal = pro.trade_cal(

        exchange="SSE",

        start_date=(pd.Timestamp(td) - pd.Timedelta(days=30)).strftime("%Y%m%d"),

        end_date=td,

        is_open="1",

    )

    if cal is None or cal.empty:

        return None

    open_days = sorted(cal["cal_date"].tolist())

    prior = [d for d in open_days if d < td]

    if not prior:

        return None

    last = prior[-1]

    return f"{last[:4]}-{last[4:6]}-{last[6:8]}"





def _latest_trade_date(pro, *, end: str | None = None) -> str:
    """不晚于 end（默认今天）的最近一个 SSE 交易日，返回 YYYY-MM-DD。"""
    end_ts = pd.Timestamp(end) if end is not None else pd.Timestamp.today()
    cal = pro.trade_cal(
        exchange="SSE",
        start_date=(end_ts - pd.Timedelta(days=10)).strftime("%Y%m%d"),
        end_date=end_ts.strftime("%Y%m%d"),
        is_open="1",
    )
    last = cal["cal_date"].max()
    return f"{last[:4]}-{last[4:6]}-{last[6:8]}"


def _next_trade_date(pro, date: str) -> str | None:
    """给定 YYYY-MM-DD 或 YYYYMMDD，返回下一个交易日 YYYY-MM-DD。"""
    td = _format_yyyymmdd(date)
    cal = pro.trade_cal(
        exchange="SSE",
        start_date=td,
        end_date=(pd.Timestamp(td) + pd.Timedelta(days=30)).strftime("%Y%m%d"),
        is_open="1",
    )
    if cal is None or cal.empty:
        return None
    open_days = sorted(cal["cal_date"].tolist())
    later = [d for d in open_days if d > td]
    if not later:
        return None
    nxt = later[0]
    return f"{nxt[:4]}-{nxt[4:6]}-{nxt[6:8]}"


def _panel_missing_trade_dates(pro, panel: pd.DataFrame, latest: str) -> list[str]:
    """panel 覆盖区间 [min, latest] 内缺失的 SSE 交易日（含中间空洞），YYYY-MM-DD。"""
    dt = panel.index.get_level_values("datetime")
    panel_min = pd.Timestamp(dt.min()).normalize()
    latest_ts = pd.Timestamp(latest).normalize()
    if panel_min > latest_ts:
        return []

    all_trade = _fetch_trade_dates(pro, panel_min.strftime("%Y-%m-%d"), latest)
    existing = {pd.Timestamp(t).normalize() for t in dt.unique()}

    missing: list[str] = []
    for td in all_trade:
        ts = pd.Timestamp(f"{td[:4]}-{td[4:6]}-{td[6:8]}").normalize()
        if ts not in existing:
            missing.append(ts.strftime("%Y-%m-%d"))
    return missing


def _group_contiguous_trade_dates(pro, iso_dates: list[str]) -> list[tuple[str, str]]:
    """将缺失交易日列表合并为若干闭区间 [start, end]（单次 trade_cal，避免逐日查询）。"""
    if not iso_dates:
        return []
    sorted_iso = sorted(iso_dates)
    yyyymmdd_list = _fetch_trade_dates(pro, sorted_iso[0], sorted_iso[-1])
    trade_idx = {
        f"{d[:4]}-{d[4:6]}-{d[6:8]}": i for i, d in enumerate(yyyymmdd_list)
    }

    ranges: list[tuple[str, str]] = []
    start = end = sorted_iso[0]
    for d in sorted_iso[1:]:
        prev_i = trade_idx.get(end)
        cur_i = trade_idx.get(d)
        if prev_i is not None and cur_i is not None and cur_i == prev_i + 1:
            end = d
        else:
            ranges.append((start, end))
            start = end = d
    ranges.append((start, end))
    return ranges


def _expand_update_dates(pro, dates: list[str]) -> tuple[list[str], str | None]:

    """

    增量更新日期扩展：在 user dates 基础上加入最早日期的上一交易日。

    返回 (sorted fetch dates, backfill_since YYYY-MM-DD)。

    """

    normalized = sorted({_format_yyyymmdd(d) for d in dates})

    iso_dates = [f"{d[:4]}-{d[4:6]}-{d[6:8]}" for d in normalized]

    prev = _prev_trade_date(pro, iso_dates[0])

    fetch_set = set(normalized)

    if prev is not None:

        fetch_set.add(_format_yyyymmdd(prev))

    fetch_sorted = sorted(fetch_set)

    fetch_iso = [f"{d[:4]}-{d[4:6]}-{d[6:8]}" for d in fetch_sorted]

    backfill_since = prev if prev is not None else iso_dates[0]

    return fetch_iso, backfill_since





def _merge_raw_daily(

    daily: pd.DataFrame,

    adj: pd.DataFrame,

    basic: pd.DataFrame,

    st_table: pd.DataFrame,

) -> pd.DataFrame:

    """合并 daily + adj_factor + daily_basic + stock_st 为 hq 宽表行。"""

    if daily is None or daily.empty:

        return pd.DataFrame()



    df = daily.copy()

    if adj is not None and not adj.empty:

        df = df.merge(adj[["ts_code", "trade_date", "adj_factor"]], on=["ts_code", "trade_date"], how="left")

    else:

        df["adj_factor"] = 1.0



    if basic is not None and not basic.empty:

        df = df.merge(basic, on=["ts_code", "trade_date"], how="left")

    else:

        df["circ_mv"] = 0.0

        df["total_mv"] = 0.0



    df = apply_is_st(df, st_table)



    df["adjfactor"] = df["adj_factor"].fillna(1.0)

    df["volume"] = df["vol"]

    df["float_cap"] = df["circ_mv"].fillna(0) * 10000

    df["tot_cap"] = df["total_mv"].fillna(0) * 10000

    df["is_trade"] = (df["volume"] > 0).astype("int8")



    df["datetime"] = pd.to_datetime(df["trade_date"])

    df["instrument"] = df["ts_code"]



    cols = [

        "datetime",

        "instrument",

        "open",

        "high",

        "low",

        "close",

        "adjfactor",

        "volume",

        "amount",

        "float_cap",

        "tot_cap",

        "is_trade",

        "is_st",

        "not_st",

    ]

    return df[cols].set_index(["datetime", "instrument"])





def _fetch_one_day(pro, trade_date: str) -> pd.DataFrame:

    """拉取单个交易日全市场数据并合并为 hq 行。"""

    daily = pro.daily(trade_date=trade_date)

    if daily is None or daily.empty:

        return pd.DataFrame()



    adj = pro.adj_factor(trade_date=trade_date)

    basic = pro.daily_basic(trade_date=trade_date, fields="ts_code,trade_date,circ_mv,total_mv")

    st_table = fetch_st_table(pro, trade_date=trade_date)



    return _merge_raw_daily(daily, adj, basic, st_table)





def _year_chunks(start: str, end: str) -> list[tuple[str, str]]:

    """按自然年切分日期区间，避免单次 daily 行数超限。"""

    start_ts = pd.Timestamp(start)

    end_ts = pd.Timestamp(end)

    chunks: list[tuple[str, str]] = []

    for year in range(start_ts.year, end_ts.year + 1):

        chunk_start = max(start_ts, pd.Timestamp(f"{year}-01-01"))

        chunk_end = min(end_ts, pd.Timestamp(f"{year}-12-31"))

        if chunk_start <= chunk_end:

            chunks.append((chunk_start.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")))

    return chunks





def _select_daily_basic(basic: pd.DataFrame, codes: set[str] | list[str]) -> pd.DataFrame:

    """从按 trade_date 缓存的 daily_basic 中筛出指定股票。"""

    cols = ["ts_code", "trade_date", "circ_mv", "total_mv"]

    if basic is None or basic.empty:

        return pd.DataFrame(columns=cols)

    code_set = set(codes)

    return basic[basic["ts_code"].isin(code_set)].copy()





def _fetch_daily_basic_for_dates(

    pro,

    trade_dates: list[str],

    *,

    codes: set[str] | list[str] | None = None,

    sleep_sec: float = 0.35,

    verbose: bool = False,

) -> pd.DataFrame:

    """

    按 trade_date 拉 daily_basic。

    Tushare 的 daily_basic 不支持「多 ts_code + start/end 区间」组合，会返回空表。

    """

    cols = ["ts_code", "trade_date", "circ_mv", "total_mv"]

    if not trade_dates:

        return pd.DataFrame(columns=cols)



    code_set = set(codes) if codes is not None else None

    chunks: list[pd.DataFrame] = []

    n = len(trade_dates)

    for i, td in enumerate(trade_dates):

        if verbose and (i == 0 or i + 1 == n or (i + 1) % 50 == 0):

            print(f"    daily_basic [{i + 1}/{n}] {td}")

        df = pro.daily_basic(trade_date=td, fields="ts_code,trade_date,circ_mv,total_mv")

        if df is not None and not df.empty:

            if code_set is not None:

                df = df[df["ts_code"].isin(code_set)]

            if not df.empty:

                chunks.append(df)

        if sleep_sec > 0:

            time.sleep(sleep_sec)



    if not chunks:

        return pd.DataFrame(columns=cols)

    return pd.concat(chunks, ignore_index=True)





def fetch_hq_for_pool(

    start: str,

    end: str,

    members: list[str],

    *,

    batch_size: int = 40,

    sleep_sec: float = 0.35,

    verbose: bool = True,

) -> pd.DataFrame:

    """

    按股票池批量拉取 [start, end] 行情（daily + adj + basic + stock_st）。

    members: 成分股 ts_code 列表

    """

    pro = get_pro()

    if not members:

        raise ValueError("股票池为空")



    date_chunks = _year_chunks(start, end)

    batches = [members[i : i + batch_size] for i in range(0, len(members), batch_size)]

    total_steps = len(date_chunks) * len(batches)

    step = 0



    chunks: list[pd.DataFrame] = []

    member_set = set(members)

    for d_start, d_end in date_chunks:

        d0 = _format_yyyymmdd(d_start)

        d1 = _format_yyyymmdd(d_end)

        st_table = fetch_st_table(pro, start_date=d0, end_date=d1)

        trade_dates = _fetch_trade_dates(pro, d_start, d_end)

        if verbose:

            print(f"  daily_basic: {len(trade_dates)} 个交易日 ({d_start}~{d_end})")

        basic_all = _fetch_daily_basic_for_dates(

            pro,

            trade_dates,

            codes=member_set,

            sleep_sec=sleep_sec,

            verbose=verbose,

        )

        for batch in batches:

            step += 1

            ts_code = ",".join(batch)

            if verbose:

                print(f"  [{step}/{total_steps}] {d_start}~{d_end}  {len(batch)} 只股票")



            daily = pro.daily(ts_code=ts_code, start_date=d0, end_date=d1)

            adj = pro.adj_factor(ts_code=ts_code, start_date=d0, end_date=d1)

            basic_df = _select_daily_basic(basic_all, batch)

            hq = _merge_raw_daily(daily, adj, basic_df, st_table)

            if not hq.empty:

                chunks.append(hq)

            if sleep_sec > 0:

                time.sleep(sleep_sec)



    if not chunks:

        raise ValueError("股票池拉取未获得任何行情数据")



    return pd.concat(chunks).sort_index()





def fetch_hq_for_index(

    start: str,

    end: str,

    index: str = "zz1000",

    *,

    batch_size: int = 40,

    sleep_sec: float = 0.35,

    verbose: bool = True,

) -> pd.DataFrame:

    """拉取指数成分并集在 [start, end] 的全部股票行情。"""

    pro = get_pro()

    members = fetch_index_members(pro, index, start, end, sleep_sec=sleep_sec, verbose=verbose)

    if verbose:

        print(f"指数 {index}: {len(members)} 只股票（{start} ~ {end} 成分并集）")

    return fetch_hq_for_pool(

        start,

        end,

        members,

        batch_size=batch_size,

        sleep_sec=sleep_sec,

        verbose=verbose,

    )





def fetch_hq_from_tushare(

    start: str,

    end: str,

    *,

    sleep_sec: float = 0.35,

    verbose: bool = True,

) -> pd.DataFrame:

    """从 Tushare 按交易日拉取全市场行情（原始 hq 格式）。"""

    pro = get_pro()

    trade_dates = _fetch_trade_dates(pro, start, end)

    if not trade_dates:

        raise ValueError(f"区间 {start} ~ {end} 无交易日")



    chunks: list[pd.DataFrame] = []

    for i, td in enumerate(trade_dates):

        if verbose:

            print(f"  [{i + 1}/{len(trade_dates)}] {td}")

        day_df = _fetch_one_day(pro, td)

        if not day_df.empty:

            chunks.append(day_df)

        if sleep_sec > 0:

            time.sleep(sleep_sec)



    if not chunks:

        raise ValueError("未拉取到任何行情数据")



    hq = pd.concat(chunks).sort_index()

    return hq





def build_panel(

    *,

    start: str,

    end: str,

    out_path: Path | str | None = None,

    universe_mask: bool = True,

    universe: str | None = "zz1000",

    batch_size: int = 40,

    sleep_sec: float = 0.35,

    verbose: bool = True,

) -> pd.DataFrame:

    """Tushare 拉数 → 构建 panel → 可选写出 parquet。"""

    if verbose:

        mode = f"指数池 {universe}" if universe else "全市场按日"

        print(f"build_panel: {start} ~ {end} ({mode})")



    if universe:

        hq = fetch_hq_for_index(

            start,

            end,

            universe,

            batch_size=batch_size,

            sleep_sec=sleep_sec,

            verbose=verbose,

        )

    else:

        hq = fetch_hq_from_tushare(start, end, sleep_sec=sleep_sec, verbose=verbose)



    panel = build_panel_from_hq(hq, universe_mask=universe_mask)

    if out_path is not None:

        save_panel(panel, out_path)

        if verbose:

            n_inst = panel.index.get_level_values("instrument").nunique()

            print(f"已保存: {out_path} shape={panel.shape} 股票数={n_inst}")

    return panel





def load_panel(path: Path | str = DEFAULT_PANEL_PATH) -> pd.DataFrame:

    """加载 panel parquet。"""

    p = Path(path)

    if not p.is_file():

        raise FileNotFoundError(f"panel 不存在: {p}")

    panel = pd.read_parquet(p)

    if "instrument" not in panel.index.names and "code" in panel.index.names:

        panel = panel.rename_axis(index={"code": "instrument"})

    return _coerce_datetime_index(panel)





def save_panel(panel: pd.DataFrame, path: Path | str) -> Path:

    """写出 panel parquet。"""

    out = Path(path)

    out.parent.mkdir(parents=True, exist_ok=True)

    panel.to_parquet(out)

    return out





def update_panel(

    path: Path | str = DEFAULT_PANEL_PATH,

    *,

    dates: list[str] | None = None,

    universe: str | None = "zz1000",

    sleep_sec: float = 0.35,

    batch_size: int = 40,

    verbose: bool = True,

) -> pd.DataFrame:

    """

    增量更新 panel parquet。

    - dates: 指定交易日（按日拉取）；默认检测 [panel.min, 最新交易日] 内全部缺失日并批量回填

    - universe: 指数池时用 fetch_hq_for_index 按股票池批量拉取（与 build_panel 相同）

    - 自动在 merge 后从缺口首日前一交易日起重算 ret / label

    """

    path = Path(path)

    pro = get_pro()

    old: pd.DataFrame | None = None

    bulk_fill = False

    gap_ranges: list[tuple[str, str]] | None = None

    if dates is None:

        latest = _latest_trade_date(pro)

        if path.is_file():

            old = load_panel(path)

            dates = _panel_missing_trade_dates(pro, old, latest)

            if not dates:

                panel_max = old.index.get_level_values("datetime").max()

                if verbose:

                    print(

                        f"panel 已完整: 末行 {panel_max.date()}，"

                        f"最新交易日 {latest}，无缺失日"

                    )

                return old

            bulk_fill = True

            gap_ranges = _group_contiguous_trade_dates(pro, dates)

            if verbose:

                print(

                    f"检测到缺口: 共 {len(dates)} 个交易日，"

                    f"{len(gap_ranges)} 段 ({dates[0]} ~ {dates[-1]})，"

                    f"按股票池批量拉取"

                )

        else:

            dates = [latest]



    chunks: list[pd.DataFrame] = []

    backfill_since: str



    if bulk_fill:

        assert gap_ranges is not None

        backfill_since = _prev_trade_date(pro, dates[0]) or dates[0]

        for start, end in gap_ranges:

            if verbose:

                print(f"update_panel: 批量拉取 {start} ~ {end}")

            if universe:

                hq = fetch_hq_for_index(

                    start,

                    end,

                    universe,

                    batch_size=batch_size,

                    sleep_sec=sleep_sec,

                    verbose=verbose,

                )

            else:

                hq = fetch_hq_from_tushare(

                    start,

                    end,

                    sleep_sec=sleep_sec,

                    verbose=verbose,

                )

            gap_panel = _panel_base_from_hq(hq, universe_mask=bool(universe))

            if not gap_panel.empty:

                chunks.append(gap_panel)

    else:

        fetch_dates, backfill_since = _expand_update_dates(pro, dates)



        pool: set[str] | None = None

        if universe:

            pool = fetch_index_members_for_dates(
                pro,
                universe,
                fetch_dates,
                sleep_sec=sleep_sec,
                verbose=verbose,
            )



        for d in fetch_dates:

            td = _format_yyyymmdd(d)

            if verbose:

                tag = " (回填上一交易日)" if d == backfill_since and d not in dates else ""

                print(f"update_panel: 拉取 {td}{tag}")

            hq_day = _fetch_one_day(pro, td)

            if hq_day.empty:

                print(f"  警告: {td} 无数据，跳过")

                continue

            if pool is not None:

                inst = hq_day.index.get_level_values("instrument")

                hq_day = hq_day[inst.isin(pool)]

            day_panel = _panel_base_from_hq(hq_day, universe_mask=True)

            if not day_panel.empty:

                chunks.append(day_panel)

            if sleep_sec > 0:

                time.sleep(sleep_sec)



    if not chunks:

        raise ValueError("增量更新未获得任何数据")



    new_panel = pd.concat(chunks).sort_index()



    if path.is_file():

        if old is None:

            old = load_panel(path)

        merged = pd.concat([old, new_panel])

        merged = merged[~merged.index.duplicated(keep="last")]

        merged = merged.sort_index()

    else:

        merged = new_panel



    merged = _rederive_since(merged, pd.Timestamp(backfill_since))



    save_panel(merged, path)

    if verbose:

        print(f"已更新: {path} shape={merged.shape}（衍生列自 {backfill_since} 起重算）")

    return merged





def find_suspect_adjfactor_instruments(

    panel: pd.DataFrame,

    *,

    min_real_factor: float = 1.5,

) -> list[str]:

    """

    宽口径候选：曾有 adjfactor>min_real_factor，且仍存在 adjfactor≈1 的行。

    新股上市初期 adjfactor=1 也符合此条件，**误报多**；修补请用 find_adjfactor_jump_instruments。

    """

    if panel.empty:

        return []



    inst_max = panel.groupby(level="instrument")["adjfactor"].max()

    candidates = inst_max[inst_max > min_real_factor].index

    suspects: list[str] = []

    for inst in candidates:

        s = panel.xs(inst, level="instrument")["adjfactor"]

        if (s <= 1.0 + 1e-6).any():

            suspects.append(str(inst))

    return sorted(suspects)





def find_adjfactor_jump_instruments(

    panel: pd.DataFrame,

    *,

    low: float = 1.01,

    high: float = 1.5,

    max_close_move: float = 0.25,

) -> list[str]:

    """

    窄口径候选：相邻交易日 adjfactor 从≈1 跳到≥high（或反向），且 raw close 涨跌幅不大。

    对应 merge 失败导致的尺度断层（如 600601 的 1.0 → 5764）；正常上市/除权不会命中。

    """

    if panel.empty:

        return []



    suspects: list[str] = []

    for inst in panel.index.get_level_values("instrument").unique():

        s = panel.xs(inst, level="instrument").sort_index()

        adj = s["adjfactor"].to_numpy(dtype=float, copy=False)

        close = s["close"].to_numpy(dtype=float, copy=False)

        if len(adj) < 2:

            continue

        for i in range(len(adj) - 1):

            if close[i] <= 0:

                continue

            if abs(close[i + 1] / close[i] - 1.0) > max_close_move:

                continue

            if adj[i] <= low and adj[i + 1] >= high:

                suspects.append(str(inst))

                break

            if adj[i] >= high and adj[i + 1] <= low:

                suspects.append(str(inst))

                break

    return sorted(set(suspects))





def count_suspect_adjfactor_rows(

    panel: pd.DataFrame,

    instruments: list[str],

) -> int:

    """指定股票列表中 adjfactor≈1 的行数。"""

    if not instruments:

        return 0

    inst_idx = panel.index.get_level_values("instrument")

    mask = inst_idx.isin(instruments) & (panel["adjfactor"] <= 1.0 + 1e-6)

    return int(mask.sum())





def _rederive_adj_price_columns(panel: pd.DataFrame, *, dtype: str = "float32") -> pd.DataFrame:

    """按 adjfactor 重算 adj_* / adj_vwap。"""

    panel = panel.copy()

    for col in ("open", "high", "low", "close"):

        panel[f"adj_{col}"] = (panel[col] * panel["adjfactor"]).astype(dtype)

    panel["adj_vwap"] = (panel["vwap"] * panel["adjfactor"]).astype(dtype)

    return panel





def _fetch_adj_factor_for_instrument(

    pro,

    instrument: str,

    start: str,

    end: str,

) -> pd.Series:

    """拉取单股 adj_factor，返回 datetime 索引 Series。"""

    d0 = _format_yyyymmdd(start)

    d1 = _format_yyyymmdd(end)

    adj = pro.adj_factor(ts_code=instrument, start_date=d0, end_date=d1)

    if adj is None or adj.empty:

        return pd.Series(dtype=float)

    adj = adj.copy()

    adj["datetime"] = pd.to_datetime(adj["trade_date"])

    return adj.drop_duplicates(subset=["datetime"], keep="last").set_index("datetime")[

        "adj_factor"

    ].sort_index()





def repair_panel_adjfactor(

    panel: pd.DataFrame,

    *,

    instruments: list[str] | None = None,

    min_real_factor: float = 1.5,

    candidate_mode: str = "jump",

    sleep_sec: float = 0.35,

    verbose: bool = True,

    pro=None,

) -> tuple[pd.DataFrame, dict[str, int | float]]:

    """

    方案 B：对可疑股票按 Tushare 单股重拉 adj_factor，重算 adj/ret/label。

    candidate_mode:

    - ``jump``（默认）: find_adjfactor_jump_instruments，仅尺度断层

    - ``adj_one``: find_suspect_adjfactor_instruments，宽口径（易误报）

    仅覆盖 API 与 panel 不一致的单元格；已一致则更新数为 0。

    """

    if pro is None:

        pro = get_pro()



    panel = panel.copy()

    if instruments is not None:

        targets = instruments

    elif candidate_mode == "adj_one":

        targets = find_suspect_adjfactor_instruments(

            panel, min_real_factor=min_real_factor

        )

    else:

        targets = find_adjfactor_jump_instruments(panel)

    stats: dict[str, int | float] = {

        "n_target_instruments": len(targets),

        "n_rows_adj_one_before": count_suspect_adjfactor_rows(panel, targets),

        "n_cells_updated": 0,

        "n_instruments_patched": 0,

        "n_rows_adj_one_after": 0,

    }

    if not targets:

        if verbose:

            print("无可疑 adjfactor 股票，跳过修补（panel 与 API 可能已一致）")

        return panel, stats



    if verbose:

        print(

            f"修补 adjfactor: {len(targets)} 只股票，"

            f"adj≈1 行 {stats['n_rows_adj_one_before']} 条"

        )



    updated_cells = 0

    patched_inst = 0

    for i, inst in enumerate(targets, start=1):

        if inst not in panel.index.get_level_values("instrument"):

            continue

        sub = panel.xs(inst, level="instrument")

        start = sub.index.min().strftime("%Y-%m-%d")

        end = sub.index.max().strftime("%Y-%m-%d")

        api_adj = _fetch_adj_factor_for_instrument(pro, inst, start, end)

        if api_adj.empty:

            if verbose:

                print(f"  [{i}/{len(targets)}] {inst} API 无 adj_factor，跳过")

            if sleep_sec > 0:

                time.sleep(sleep_sec)

            continue



        common = sub.index.intersection(api_adj.index)

        if common.empty:

            if verbose:

                print(f"  [{i}/{len(targets)}] {inst} 与 panel 无交集，跳过")

            if sleep_sec > 0:

                time.sleep(sleep_sec)

            continue



        old = panel.loc[(common, inst), "adjfactor"].astype(float)

        new = api_adj.loc[common].astype(float)

        changed = ~np.isclose(old.values, new.values, rtol=0, atol=1e-6, equal_nan=True)

        n_changed = int(changed.sum())

        if n_changed:

            panel.loc[(common[changed], inst), "adjfactor"] = new.loc[common[changed]].values

            updated_cells += n_changed

            patched_inst += 1



        if verbose and (i % 50 == 0 or i == len(targets)):

            print(f"  [{i}/{len(targets)}] 已处理，累计更新 {updated_cells} 单元格")

        if sleep_sec > 0:

            time.sleep(sleep_sec)



    panel = _rederive_adj_price_columns(panel)

    since = panel.index.get_level_values("datetime").min()

    panel = _rederive_since(panel, since)



    stats["n_cells_updated"] = updated_cells

    stats["n_instruments_patched"] = patched_inst

    stats["n_rows_adj_one_after"] = count_suspect_adjfactor_rows(panel, targets)

    if verbose:

        print(

            f"完成: 更新 {patched_inst} 只股票 / {updated_cells} 个 adjfactor 单元格；"

            f"adj≈1 行 {stats['n_rows_adj_one_before']} → {stats['n_rows_adj_one_after']}"

        )

        if updated_cells == 0:

            print(

                "提示: 更新数为 0 通常表示 panel 已与 Tushare API 一致；"

                "宽口径 adj≈1 行可能是新股上市初期的正常值。"

            )

    return panel, stats


