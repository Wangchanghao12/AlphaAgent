"""从 Tushare 拉取日频行情并写入 market hq 缓存。

与 ``fundamental_fetch`` 对称：本模块**只负责联网拉取 + 落盘 hq 缓存**，
不做 panel 构建。panel 由 ``alphaagent.data.panel`` 从 hq 缓存离线构建。

hq 宽表 schema：索引 (datetime, instrument)，列
``open/high/low/close/adjfactor/volume/amount/float_cap/tot_cap`` +
daily_basic 每日指标（turnover_rate/pe_ttm/pb/ps_ttm/dv_ttm/total_share/... 见
``DAILY_BASIC_COLUMNS``）+ ``is_trade/is_st/not_st``。
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from alphaagent.core.paths import MARKET_HQ_PATH
from alphaagent.core.types import DAILY_BASIC_COLUMNS
from alphaagent.data.index_members import append_snapshot, resolve_index_members_cached
from alphaagent.data.tushare_client import get_pro
from alphaagent.data.universe import (
    apply_is_st,
    fetch_index_members_for_dates,
    fetch_st_table,
)

# daily_basic 请求字段（circ_mv/total_mv → float_cap/tot_cap；其余原样入库）
DAILY_BASIC_FIELDS = ",".join(["ts_code", "trade_date", "circ_mv", "total_mv", *DAILY_BASIC_COLUMNS])

# merge 时只保留这些列，避免代理忽略 fields 时带回 close/vol 等与 daily 撞名
_BASIC_MERGE_COLUMNS = ("ts_code", "trade_date", "circ_mv", "total_mv", *DAILY_BASIC_COLUMNS)

# hq 缓存列顺序（含 is_st，供 build 侧 filter_universe 使用）
HQ_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "adjfactor",
    "volume",
    "amount",
    "float_cap",
    "tot_cap",
    *DAILY_BASIC_COLUMNS,
    "is_trade",
    "is_st",
    "not_st",
]


def _format_yyyymmdd(d: str) -> str:
    return d.replace("-", "")


# ---------------------------------------------------------------------------
# 交易日历
# ---------------------------------------------------------------------------
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


def _panel_missing_trade_dates(pro, frame: pd.DataFrame, latest: str) -> list[str]:
    """frame 覆盖区间 [min, latest] 内缺失的 SSE 交易日（含中间空洞），YYYY-MM-DD。

    frame 可以是 hq 缓存或 panel，只要索引含 datetime 层。
    """
    dt = frame.index.get_level_values("datetime")
    frame_min = pd.Timestamp(dt.min()).normalize()
    latest_ts = pd.Timestamp(latest).normalize()
    if frame_min > latest_ts:
        return []

    all_trade = _fetch_trade_dates(pro, frame_min.strftime("%Y-%m-%d"), latest)
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
    trade_idx = {f"{d[:4]}-{d[4:6]}-{d[6:8]}": i for i, d in enumerate(yyyymmdd_list)}

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
    """增量更新日期扩展：在 user dates 基础上加入最早日期的上一交易日。

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


# ---------------------------------------------------------------------------
# 原始行情拉取
# ---------------------------------------------------------------------------
def _prepare_basic_for_merge(basic: pd.DataFrame) -> pd.DataFrame:
    """裁剪 daily_basic 列，防止与 daily 的 close/vol 等字段冲突成 close_x。"""
    if basic is None or basic.empty:
        return pd.DataFrame(columns=list(_BASIC_MERGE_COLUMNS))
    cols = [c for c in _BASIC_MERGE_COLUMNS if c in basic.columns]
    out = basic.loc[:, cols].copy()
    if "trade_date" in out.columns:
        out["trade_date"] = out["trade_date"].astype(str)
    if "ts_code" in out.columns:
        out["ts_code"] = out["ts_code"].astype(str)
    return out


def _merge_raw_daily(
    daily: pd.DataFrame,
    adj: pd.DataFrame,
    basic: pd.DataFrame,
    st_table: pd.DataFrame,
    *,
    fill_adj: bool = True,
) -> pd.DataFrame:
    """合并 daily + adj_factor + daily_basic + stock_st 为 hq 宽表行。

    fill_adj=True 时，缺失 adj_factor 直接填 1.0（历史行为，适用于按日拉取）；
    fill_adj=False 时保留 NaN，交由调用方按单股 ffill/bfill（避免伪造尺度断层）。
    """
    if daily is None or daily.empty:
        return pd.DataFrame()

    df = daily.copy()
    if "trade_date" in df.columns:
        df["trade_date"] = df["trade_date"].astype(str)
    if "ts_code" in df.columns:
        df["ts_code"] = df["ts_code"].astype(str)

    if adj is not None and not adj.empty:
        adj_use = adj[["ts_code", "trade_date", "adj_factor"]].copy()
        adj_use["trade_date"] = adj_use["trade_date"].astype(str)
        adj_use["ts_code"] = adj_use["ts_code"].astype(str)
        df = df.merge(adj_use, on=["ts_code", "trade_date"], how="left")
    else:
        df["adj_factor"] = 1.0

    basic_use = _prepare_basic_for_merge(basic)
    if not basic_use.empty:
        df = df.merge(basic_use, on=["ts_code", "trade_date"], how="left")
    else:
        df["circ_mv"] = 0.0
        df["total_mv"] = 0.0

    # 防御：若仍出现 pandas merge 后缀，优先保留 daily 侧
    for col in ("open", "high", "low", "close", "vol", "amount"):
        if col not in df.columns and f"{col}_x" in df.columns:
            df[col] = df[f"{col}_x"]

    df = apply_is_st(df, st_table)

    df["adjfactor"] = df["adj_factor"].fillna(1.0) if fill_adj else df["adj_factor"]
    df["volume"] = df["vol"]
    df["float_cap"] = df["circ_mv"].fillna(0) * 10000
    df["tot_cap"] = df["total_mv"].fillna(0) * 10000
    df["is_trade"] = (df["volume"] > 0).astype("int8")

    # daily_basic 每日指标：缺失（basic 为空或未返回该字段）时置 NaN
    for col in DAILY_BASIC_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    df["datetime"] = pd.to_datetime(df["trade_date"])
    df["instrument"] = df["ts_code"]

    missing = [c for c in ("datetime", "instrument", *HQ_COLUMNS) if c not in df.columns]
    if missing:
        raise KeyError(
            f"合并行情缺少列 {missing}；daily列={list(daily.columns)} "
            f"basic列={list(basic.columns) if basic is not None else []}"
        )

    cols = ["datetime", "instrument", *HQ_COLUMNS]
    return df[cols].set_index(["datetime", "instrument"])


def _fetch_one_day(pro, trade_date: str) -> pd.DataFrame:
    """拉取单个交易日全市场数据并合并为 hq 行。"""
    daily = pro.daily(trade_date=trade_date)
    if daily is None or daily.empty:
        return pd.DataFrame()

    adj = pro.adj_factor(trade_date=trade_date)
    basic = pro.daily_basic(trade_date=trade_date, fields=DAILY_BASIC_FIELDS)
    st_table = fetch_st_table(pro, trade_date=trade_date)

    return _merge_raw_daily(daily, adj, basic, st_table)


def _existing_trade_dates_yyyymmdd(hq: pd.DataFrame) -> set[str]:
    if hq is None or hq.empty:
        return set()
    dt = hq.index.get_level_values("datetime")
    return {pd.Timestamp(x).strftime("%Y%m%d") for x in dt.unique()}


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
    """按 trade_date 拉 daily_basic。

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
        df = pro.daily_basic(trade_date=td, fields=DAILY_BASIC_FIELDS)
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
    """按股票池拉取 [start, end] 行情（daily + adj + basic + stock_st）。

    **逐只股票、全区间**拉取 daily / adj_factor / daily_basic，避免「多 ts_code × 长区间」
    单次请求超过 Tushare 6000 行上限被静默截断（截断会丢失约 35% 行情行）。
    参数 batch_size 已弃用（保留以兼容旧调用），当前按单股拉取。
    """
    del batch_size  # 兼容旧签名，当前逐股拉取
    pro = get_pro()
    if not members:
        raise ValueError("股票池为空")

    d0 = _format_yyyymmdd(start)
    d1 = _format_yyyymmdd(end)
    st_table = fetch_st_table(pro, start_date=d0, end_date=d1)

    n = len(members)
    chunks: list[pd.DataFrame] = []
    total_rows = 0
    for i, code in enumerate(members, start=1):
        daily = pro.daily(ts_code=code, start_date=d0, end_date=d1)
        if daily is None or daily.empty:
            if verbose and (i % 100 == 0 or i == n):
                print(f"  [{i}/{n}] 逐股拉取，累计 {total_rows} 行")
            if sleep_sec > 0:
                time.sleep(sleep_sec)
            continue

        adj = pro.adj_factor(ts_code=code, start_date=d0, end_date=d1)
        basic_df = pro.daily_basic(
            ts_code=code,
            start_date=d0,
            end_date=d1,
            fields=DAILY_BASIC_FIELDS,
        )
        hq = _merge_raw_daily(daily, adj, basic_df, st_table, fill_adj=False)
        if not hq.empty:
            hq = hq.sort_index()
            # 单股内 adjfactor 前后向填充；整只缺失才退回 1.0（避免伪造尺度断层）
            hq["adjfactor"] = hq["adjfactor"].ffill().bfill().fillna(1.0)
            chunks.append(hq)
            total_rows += len(hq)

        if verbose and (i % 100 == 0 or i == n):
            print(f"  [{i}/{n}] 逐股拉取，累计 {total_rows} 行")
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
    refresh_members: bool = False,
) -> pd.DataFrame:
    """拉取指数成分并集在 [start, end] 的全部股票行情（成分股按月快照缓存到 artifacts/index/）。"""
    pro = get_pro()
    members = resolve_index_members_cached(
        index,
        start,
        end,
        pro=pro,
        refresh=refresh_members,
        sleep_sec=sleep_sec,
        verbose=verbose,
    )
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
    out_path: Path | str | None = None,
    checkpoint_every: int = 5,
    workers: int = 1,
    skip_existing: bool = True,
) -> pd.DataFrame:
    """从 Tushare 按交易日拉取全市场行情（原始 hq 格式）。

    - out_path 非空时：按日 checkpoint 落盘，崩溃可续跑
    - skip_existing：跳过 out_path 里已有交易日
    - workers>1：按日小并发（V1 建议 2~4，过大易限流）
    """
    pro = get_pro()
    trade_dates = _fetch_trade_dates(pro, start, end)
    if not trade_dates:
        raise ValueError(f"区间 {start} ~ {end} 无交易日")

    cache_path = Path(out_path) if out_path is not None else None
    existing = load_market_hq(cache_path) if cache_path is not None else pd.DataFrame()
    if skip_existing and not existing.empty:
        have = _existing_trade_dates_yyyymmdd(existing)
        before = len(trade_dates)
        trade_dates = [d for d in trade_dates if d not in have]
        if verbose and before != len(trade_dates):
            print(f"  跳过已缓存交易日 {before - len(trade_dates)} 天，待拉 {len(trade_dates)} 天")

    if not trade_dates:
        if verbose:
            print("  区间内交易日均已在缓存中，无需重拉")
        return existing.sort_index() if not existing.empty else pd.DataFrame()

    workers = max(1, int(workers))
    checkpoint_every = max(1, int(checkpoint_every))
    state_lock = threading.Lock()
    pending: list[pd.DataFrame] = []
    done = 0
    total = len(trade_dates)

    def _flush_locked(*, force: bool = False) -> None:
        nonlocal pending, existing
        if not pending:
            return
        if not force and len(pending) < checkpoint_every:
            return
        batch = pd.concat(pending).sort_index()
        pending = []
        if cache_path is None:
            # 无落盘路径时暂存在 existing 容器语义里（实际是内存累加）
            existing = merge_market_hq(existing, batch)
            return
        existing = merge_market_hq(existing, batch)
        save_market_hq(existing, cache_path)
        if verbose:
            print(f"  checkpoint → {cache_path} rows={len(existing)}")

    def _consume(td: str, day_df: pd.DataFrame) -> None:
        nonlocal done
        with state_lock:
            done += 1
            if verbose:
                print(f"  [{done}/{total}] {td}")
            if day_df is not None and not day_df.empty:
                pending.append(day_df)
            _flush_locked(force=False)

    def _pull(td: str, *, local_pro=None) -> tuple[str, pd.DataFrame]:
        # 并发时每任务独立 pro，避免多线程共享同一 client
        client = local_pro if local_pro is not None else get_pro()
        day_df = _fetch_one_day(client, td)
        if sleep_sec > 0:
            time.sleep(sleep_sec)
        return td, day_df

    if workers == 1:
        for td in trade_dates:
            _, day_df = _pull(td, local_pro=pro)
            _consume(td, day_df)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_pull, td) for td in trade_dates]
            for fut in as_completed(futures):
                td, day_df = fut.result()
                _consume(td, day_df)

    with state_lock:
        _flush_locked(force=True)

    if cache_path is not None:
        out = load_market_hq(cache_path)
    else:
        out = existing

    if out is None or out.empty:
        raise ValueError("未拉取到任何行情数据")
    return out.sort_index()


# ---------------------------------------------------------------------------
# hq 缓存 IO
# ---------------------------------------------------------------------------
def save_market_hq(hq: pd.DataFrame, path: Path | str = MARKET_HQ_PATH) -> Path:
    """写出 hq 缓存 parquet。"""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    hq.sort_index().to_parquet(out)
    return out


def load_market_hq(path: Path | str = MARKET_HQ_PATH) -> pd.DataFrame:
    """加载 hq 缓存 parquet；不存在时返回空表。"""
    p = Path(path)
    if not p.is_file():
        return pd.DataFrame()
    hq = pd.read_parquet(p)
    if "instrument" not in hq.index.names and "code" in hq.index.names:
        hq = hq.rename_axis(index={"code": "instrument"})
    dt = hq.index.get_level_values("datetime")
    if not pd.api.types.is_datetime64_any_dtype(dt):
        inst = hq.index.get_level_values("instrument")
        hq.index = pd.MultiIndex.from_arrays(
            [pd.to_datetime(dt), inst], names=["datetime", "instrument"]
        )
    return hq.sort_index()


def merge_market_hq(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """合并 hq 缓存，同 (datetime, instrument) 以 new 为准。"""
    if old is None or old.empty:
        return new.sort_index()
    if new is None or new.empty:
        return old.sort_index()
    merged = pd.concat([old, new])
    merged = merged[~merged.index.duplicated(keep="last")]
    return merged.sort_index()


# ---------------------------------------------------------------------------
# 编排：全量 / 增量
# ---------------------------------------------------------------------------
def fetch_and_save_market(
    start: str,
    end: str,
    *,
    out_path: Path | str = MARKET_HQ_PATH,
    universe: str | None = "zz1000",
    batch_size: int = 40,
    sleep_sec: float = 0.35,
    verbose: bool = True,
    refresh_members: bool = False,
    workers: int = 1,
    checkpoint_every: int = 5,
) -> pd.DataFrame:
    """全量/区间拉取行情并写入 hq 缓存（与已有缓存 merge，同键 keep last）。

    全市场按日模式会边拉边 checkpoint，中断后重跑自动跳过已有日期。
    """
    if verbose:
        mode = f"指数池 {universe}" if universe else "全市场按日"
        print(f"fetch_market: {start} ~ {end} ({mode})")

    if universe:
        hq = fetch_hq_for_index(
            start,
            end,
            universe,
            batch_size=batch_size,
            sleep_sec=sleep_sec,
            verbose=verbose,
            refresh_members=refresh_members,
        )
        existing = load_market_hq(out_path)
        merged = merge_market_hq(existing, hq)
        save_market_hq(merged, out_path)
    else:
        # 按日拉取内部已 skip_existing + checkpoint 落盘
        merged = fetch_hq_from_tushare(
            start,
            end,
            sleep_sec=sleep_sec,
            verbose=verbose,
            out_path=out_path,
            checkpoint_every=checkpoint_every,
            workers=workers,
            skip_existing=True,
        )

    if verbose:
        n_inst = merged.index.get_level_values("instrument").nunique()
        print(f"已保存 hq 缓存: {out_path} shape={merged.shape} 股票数={n_inst}")
    return merged


def update_market_cache(
    *,
    out_path: Path | str = MARKET_HQ_PATH,
    universe: str | None = "zz1000",
    dates: list[str] | None = None,
    sleep_sec: float = 0.35,
    batch_size: int = 40,
    verbose: bool = True,
) -> tuple[pd.DataFrame, str | None]:
    """增量拉取新交易日并追加写入 hq 缓存。

    - dates=None：检测 [缓存最早日, 最新交易日] 内全部缺失日并批量回填。
    - 返回 (new_hq, backfill_since)；无新数据时返回 (空表, None)。
    """
    pro = get_pro()
    existing = load_market_hq(out_path)

    bulk_fill = False
    gap_ranges: list[tuple[str, str]] | None = None

    if dates is None:
        latest = _latest_trade_date(pro)
        if not existing.empty:
            dates = _panel_missing_trade_dates(pro, existing, latest)
            if not dates:
                if verbose:
                    hq_max = existing.index.get_level_values("datetime").max()
                    print(f"hq 缓存已完整: 末日 {hq_max.date()}，最新交易日 {latest}，无缺失")
                return pd.DataFrame(), None
            bulk_fill = True
            gap_ranges = _group_contiguous_trade_dates(pro, dates)
            if verbose:
                print(
                    f"检测到缺口: 共 {len(dates)} 个交易日，{len(gap_ranges)} 段"
                    f" ({dates[0]} ~ {dates[-1]})，按股票池批量拉取"
                )
        else:
            dates = [latest]

    chunks: list[pd.DataFrame] = []
    backfill_since: str | None

    if bulk_fill:
        assert gap_ranges is not None
        backfill_since = _prev_trade_date(pro, dates[0]) or dates[0]
        for start, end in gap_ranges:
            if verbose:
                print(f"update_market_cache: 批量拉取 {start} ~ {end}")
            if universe:
                hq = fetch_hq_for_index(
                    start, end, universe, batch_size=batch_size, sleep_sec=sleep_sec, verbose=verbose
                )
            else:
                hq = fetch_hq_from_tushare(start, end, sleep_sec=sleep_sec, verbose=verbose)
            if not hq.empty:
                chunks.append(hq)
    else:
        fetch_dates, backfill_since = _expand_update_dates(pro, dates)

        pool: set[str] | None = None
        if universe:
            pool = fetch_index_members_for_dates(
                pro, universe, fetch_dates, sleep_sec=sleep_sec, verbose=verbose
            )
            # 持久化本次成分快照，日期取增量区间末日
            append_snapshot(universe, fetch_dates[-1], pool)

        for d in fetch_dates:
            td = _format_yyyymmdd(d)
            if verbose:
                tag = " (回填上一交易日)" if d == backfill_since and d not in dates else ""
                print(f"update_market_cache: 拉取 {td}{tag}")
            hq_day = _fetch_one_day(pro, td)
            if hq_day.empty:
                print(f"  警告: {td} 无数据，跳过")
                continue
            if pool is not None:
                inst = hq_day.index.get_level_values("instrument")
                hq_day = hq_day[inst.isin(pool)]
            if not hq_day.empty:
                chunks.append(hq_day)
            if sleep_sec > 0:
                time.sleep(sleep_sec)

    if not chunks:
        raise ValueError("增量拉取未获得任何数据")

    new_hq = pd.concat(chunks).sort_index()
    new_hq = new_hq[~new_hq.index.duplicated(keep="last")]

    merged = merge_market_hq(existing, new_hq)
    save_market_hq(merged, out_path)
    if verbose:
        print(f"已增量更新 hq 缓存: {out_path} +{new_hq.shape[0]} 行 → {merged.shape}")
    return new_hq, backfill_since


# ---------------------------------------------------------------------------
# adjfactor 修补（联网重拉单股 adj_factor）
# ---------------------------------------------------------------------------
def _fetch_adj_factor_for_instrument(pro, instrument: str, start: str, end: str) -> pd.Series:
    """拉取单股 adj_factor，返回 datetime 索引 Series。"""
    d0 = _format_yyyymmdd(start)
    d1 = _format_yyyymmdd(end)
    adj = pro.adj_factor(ts_code=instrument, start_date=d0, end_date=d1)
    if adj is None or adj.empty:
        return pd.Series(dtype=float)
    adj = adj.copy()
    adj["datetime"] = pd.to_datetime(adj["trade_date"])
    return (
        adj.drop_duplicates(subset=["datetime"], keep="last")
        .set_index("datetime")["adj_factor"]
        .sort_index()
    )


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
    """对可疑股票按 Tushare 单股重拉 adj_factor，重算 adj/ret/label。

    candidate_mode:
    - ``jump``（默认）: 仅尺度断层
    - ``adj_one``: 宽口径（易误报）
    """
    from alphaagent.data.panel import (
        _rederive_adj_price_columns,
        _rederive_since,
        count_suspect_adjfactor_rows,
        find_adjfactor_jump_instruments,
        find_suspect_adjfactor_instruments,
    )

    if pro is None:
        pro = get_pro()

    panel = panel.copy()
    if instruments is not None:
        targets = instruments
    elif candidate_mode == "adj_one":
        targets = find_suspect_adjfactor_instruments(panel, min_real_factor=min_real_factor)
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
    return panel, stats
