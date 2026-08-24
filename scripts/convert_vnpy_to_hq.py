#!/usr/bin/env python3
"""从 vnpy 归档数据构建 AlphaAgent daily_hq.parquet（离线，不联网）。

数据来源（均在服务器上）：
  AlphaLab 按股 OHLCV（前复权）:
    {vnpy_root}/lab/allstock/daily/{symbol}.parquet
      列: datetime, open, high, low, close, volume(股), turnover(元), open_interest
  vnpy tushare 归档（download_tushare_archive.py 产出）:
    {vnpy_root}/lab/allstock/tushare/market/daily_basic/year=YYYY/trade_date=YYYYMMDD.parquet
    {vnpy_root}/lab/allstock/tushare/market/adj_factor/year=YYYY/trade_date=YYYYMMDD.parquet
    {vnpy_root}/lab/allstock/tushare/events/stock_st/year=YYYY/trade_date=YYYYMMDD.parquet

用法（在服务器 AlphaAgent 根目录）：
  python scripts/convert_vnpy_to_hq.py \
    --vnpy-root /mnt/recom/develop/wangchanghao/rtp_fg/vnpy/examples/alpha_research \
    --start 2010-01-01 --end 2026-08-22

输出：artifacts/market/daily_hq.parquet（与 fetch_market.py 格式完全兼容）
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alphaagent.core.paths import MARKET_HQ_PATH  # noqa: E402
from alphaagent.core.types import DAILY_BASIC_COLUMNS  # noqa: E402


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _vnpy_code_to_tushare(vnpy_code: str) -> str:
    """000001.SZSE → 000001.SZ；600519.SSE → 600519.SH"""
    symbol, exchange = vnpy_code.rsplit(".", 1)
    suffix = {"SZSE": "SZ", "SSE": "SH", "BSE": "BJ"}.get(exchange, exchange)
    return f"{symbol}.{suffix}"


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def _yyyymmdd(iso: str) -> str:
    return iso.replace("-", "")


# ---------------------------------------------------------------------------
# 第一步：读取 AlphaLab 按股 OHLCV → 宽表
# ---------------------------------------------------------------------------

def load_alphalab_ohlc(
    alphalab_dir: Path,
    start: str,
    end: str,
    *,
    verbose: bool = True,
) -> pd.DataFrame:
    """读取所有 AlphaLab 按股 parquet，返回 (datetime, instrument) 索引的 OHLCV 宽表。

    价格已是前复权，adjfactor 暂置 1.0，后续用 vnpy 归档 adj_factor 覆盖。
    """
    files = sorted(alphalab_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"AlphaLab 目录无 parquet 文件: {alphalab_dir}")

    t0 = time.perf_counter()
    frames: list[pd.DataFrame] = []
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)

    for i, f in enumerate(files, 1):
        instrument = _vnpy_code_to_tushare(f.stem)
        try:
            df = pd.read_parquet(f)
        except Exception:
            continue
        if df.empty or "datetime" not in df.columns:
            continue
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df[(df["datetime"] >= start_ts) & (df["datetime"] <= end_ts)]
        if df.empty:
            continue
        df["instrument"] = instrument
        # 单位换算：volume 股→手，turnover 元→千元
        df["volume"] = df["volume"].astype(float) / 100.0
        df["amount"] = df["turnover"].astype(float) / 1000.0
        df["is_trade"] = (df["volume"] > 0).astype("int8")
        cols = ["datetime", "instrument", "open", "high", "low", "close",
                "volume", "amount", "is_trade"]
        frames.append(df[cols])
        if verbose and (i % 500 == 0 or i == len(files)):
            print(f"  AlphaLab [{i}/{len(files)}] elapsed={_format_elapsed(time.perf_counter() - t0)}",
                  flush=True)

    if not frames:
        raise ValueError("AlphaLab 数据为空")

    hq = pd.concat(frames, ignore_index=True)
    hq = hq.set_index(["datetime", "instrument"]).sort_index()
    if verbose:
        print(f"  AlphaLab 读取完成: shape={hq.shape} "
              f"elapsed={_format_elapsed(time.perf_counter() - t0)}", flush=True)
    return hq


# ---------------------------------------------------------------------------
# 第二步：按日读取 vnpy tushare 归档（daily_basic / adj_factor / stock_st）
# ---------------------------------------------------------------------------

def _list_trade_dates_from_tree(base_dir: Path) -> list[str]:
    """扫描 year=YYYY/trade_date=YYYYMMDD.parquet 树，返回已有日期列表。"""
    if not base_dir.is_dir():
        return []
    dates = []
    for year_dir in sorted(base_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        for f in year_dir.glob("trade_date=*.parquet"):
            dates.append(f.stem.split("=", 1)[1])
    return sorted(dates)


def load_daily_basic_chunk(
    tushare_dir: Path,
    trade_dates: list[str],
    *,
    verbose: bool = True,
) -> pd.DataFrame:
    """按日读取 daily_basic，合并为一张表。"""
    base = tushare_dir / "market" / "daily_basic"
    frames: list[pd.DataFrame] = []
    n = len(trade_dates)
    t0 = time.perf_counter()
    for i, td in enumerate(trade_dates, 1):
        path = base / f"year={td[:4]}" / f"trade_date={td}.parquet"
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
        except Exception:
            continue
        if not df.empty:
            frames.append(df)
        if verbose and (i % 200 == 0 or i == n):
            print(f"  daily_basic [{i}/{n}] elapsed={_format_elapsed(time.perf_counter() - t0)}",
                  flush=True)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_adj_factor_chunk(
    tushare_dir: Path,
    trade_dates: list[str],
    *,
    verbose: bool = True,
) -> pd.DataFrame:
    """按日读取 adj_factor，合并为一张表。"""
    base = tushare_dir / "market" / "adj_factor"
    frames: list[pd.DataFrame] = []
    n = len(trade_dates)
    t0 = time.perf_counter()
    for i, td in enumerate(trade_dates, 1):
        path = base / f"year={td[:4]}" / f"trade_date={td}.parquet"
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
        except Exception:
            continue
        if not df.empty:
            frames.append(df)
        if verbose and (i % 200 == 0 or i == n):
            print(f"  adj_factor [{i}/{n}] elapsed={_format_elapsed(time.perf_counter() - t0)}",
                  flush=True)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_stock_st_chunk(
    tushare_dir: Path,
    trade_dates: list[str],
    *,
    verbose: bool = True,
) -> pd.DataFrame:
    """按日读取 stock_st，合并为一张表。"""
    base = tushare_dir / "events" / "stock_st"
    frames: list[pd.DataFrame] = []
    n = len(trade_dates)
    t0 = time.perf_counter()
    for i, td in enumerate(trade_dates, 1):
        path = base / f"year={td[:4]}" / f"trade_date={td}.parquet"
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
        except Exception:
            continue
        if not df.empty:
            frames.append(df)
        if verbose and (i % 200 == 0 or i == n):
            print(f"  stock_st [{i}/{n}] elapsed={_format_elapsed(time.perf_counter() - t0)}",
                  flush=True)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# 第三步：合并为 AlphaAgent daily_hq.parquet 格式
# ---------------------------------------------------------------------------

def merge_to_hq(
    hq: pd.DataFrame,
    daily_basic: pd.DataFrame,
    adj_factor: pd.DataFrame,
    stock_st: pd.DataFrame,
    *,
    verbose: bool = True,
) -> pd.DataFrame:
    """将 OHLCV + daily_basic + adj_factor + stock_st 合并为 hq 宽表。"""
    t0 = time.perf_counter()

    # --- adj_factor ---
    if not adj_factor.empty:
        adj = adj_factor[["ts_code", "trade_date", "adj_factor"]].copy()
        adj["trade_date"] = adj["trade_date"].astype(str)
        adj["ts_code"] = adj["ts_code"].astype(str)
        adj["datetime"] = pd.to_datetime(adj["trade_date"])
        adj = adj.set_index(["datetime", "ts_code"])["adj_factor"]
        adj = adj[~adj.index.duplicated(keep="last")]  # 去重，防止 non-unique multi-index
        # 对齐到 hq 索引
        hq_index = hq.index
        inst_level = hq_index.get_level_values("instrument")
        dt_level = hq_index.get_level_values("datetime")
        lookup_keys = pd.MultiIndex.from_arrays([dt_level, inst_level])
        hq["adjfactor"] = adj.reindex(lookup_keys).values
        # 缺失 adjfactor 填 1.0（前复权价格，adjfactor=1 不影响收益率计算）
        hq["adjfactor"] = hq["adjfactor"].fillna(1.0)
        if verbose:
            n_real = int((hq["adjfactor"] != 1.0).sum())
            print(f"  adjfactor: {n_real}/{len(hq)} 行有真实值", flush=True)
    else:
        hq["adjfactor"] = 1.0
        if verbose:
            print("  adj_factor 归档为空，adjfactor 全部置 1.0", flush=True)

    # --- daily_basic ---
    if not daily_basic.empty:
        db = daily_basic.copy()
        db["trade_date"] = db["trade_date"].astype(str)
        db["ts_code"] = db["ts_code"].astype(str)
        db["datetime"] = pd.to_datetime(db["trade_date"])
        db = db.set_index(["datetime", "ts_code"])

        # float_cap / tot_cap（circ_mv/total_mv 单位：万元 → 元）
        if "circ_mv" in db.columns:
            db["float_cap"] = db["circ_mv"].fillna(0) * 10000
        else:
            db["float_cap"] = np.nan
        if "total_mv" in db.columns:
            db["tot_cap"] = db["total_mv"].fillna(0) * 10000
        else:
            db["tot_cap"] = np.nan

        # 只保留需要的列
        keep_cols = ["float_cap", "tot_cap"] + [c for c in DAILY_BASIC_COLUMNS if c in db.columns]
        db = db[keep_cols]
        db = db[~db.index.duplicated(keep="last")]  # 去重

        hq_index = hq.index
        inst_level = hq_index.get_level_values("instrument")
        dt_level = hq_index.get_level_values("datetime")
        lookup_keys = pd.MultiIndex.from_arrays([dt_level, inst_level])
        for col in keep_cols:
            hq[col] = db[col].reindex(lookup_keys).values

        if verbose:
            print(f"  daily_basic: 并入 {len(keep_cols)} 列", flush=True)
    else:
        hq["float_cap"] = np.nan
        hq["tot_cap"] = np.nan
        for col in DAILY_BASIC_COLUMNS:
            hq[col] = np.nan
        if verbose:
            print("  daily_basic 归档为空，相关列置 NaN", flush=True)

    # --- stock_st ---
    if not stock_st.empty:
        st = stock_st.copy()
        st["trade_date"] = st["trade_date"].astype(str)
        st["ts_code"] = st["ts_code"].astype(str)
        st["datetime"] = pd.to_datetime(st["trade_date"])
        # stock_st API 返回 is_st 列（1=ST）
        if "is_st" in st.columns:
            st_flag = st.set_index(["datetime", "ts_code"])["is_st"]
            st_flag = st_flag[~st_flag.index.duplicated(keep="last")]  # 去重
        else:
            st_flag = pd.Series(dtype=float)

        hq_index = hq.index
        inst_level = hq_index.get_level_values("instrument")
        dt_level = hq_index.get_level_values("datetime")
        lookup_keys = pd.MultiIndex.from_arrays([dt_level, inst_level])
        is_st_raw = st_flag.reindex(lookup_keys).values
        hq["is_st"] = np.where(np.isnan(is_st_raw), 0, is_st_raw).astype("int8")
        hq["not_st"] = (hq["is_st"] == 0).astype("int8")
        if verbose:
            n_st = int(hq["is_st"].sum())
            print(f"  stock_st: {n_st} 行标记为 ST", flush=True)
    else:
        hq["is_st"] = 0
        hq["not_st"] = 1
        if verbose:
            print("  stock_st 归档为空，全部视为非 ST", flush=True)

    if verbose:
        print(f"  merge 完成: shape={hq.shape} "
              f"elapsed={_format_elapsed(time.perf_counter() - t0)}", flush=True)
    return hq


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="从 vnpy 归档构建 AlphaAgent daily_hq.parquet")
    parser.add_argument(
        "--vnpy-root",
        type=Path,
        required=True,
        help="vnpy alpha_research 目录，如 /mnt/.../vnpy/examples/alpha_research",
    )
    parser.add_argument("--start", type=str, default="2010-01-01")
    parser.add_argument("--end", type=str, default="2026-08-22")
    parser.add_argument("--out", type=Path, default=MARKET_HQ_PATH)
    parser.add_argument("--batch-size", type=int, default=500,
                        help="按日读取 daily_basic/adj_factor 时每批天数（控制内存）")
    args = parser.parse_args()

    alphalab_dir = args.vnpy_root / "lab" / "allstock" / "daily"
    tushare_dir = args.vnpy_root / "lab" / "allstock" / "tushare"

    if not alphalab_dir.is_dir():
        raise FileNotFoundError(
            f"AlphaLab 目录不存在: {alphalab_dir}\n"
            f"请确认 vnpy 数据路径，或先运行 import_stock_data.py 导入按股数据"
        )
    if not tushare_dir.is_dir():
        print(f"警告: tushare 归档目录不存在: {tushare_dir}，daily_basic/adj_factor 将为空")

    t_total = time.perf_counter()

    # 1. 读取 AlphaLab OHLCV
    print(f"\n[1/4] 读取 AlphaLab 按股数据: {alphalab_dir}")
    hq = load_alphalab_ohlc(alphalab_dir, args.start, args.end)

    # 2. 确定需要读取的交易日（从 hq 索引中提取）
    all_dates = sorted(
        {pd.Timestamp(d).strftime("%Y%m%d") for d in hq.index.get_level_values("datetime").unique()}
    )
    print(f"\n[2/4] 读取 vnpy tushare 归档（共 {len(all_dates)} 个交易日）")

    # 分批读取，避免一次性加载所有日期到内存
    batch_size = args.batch_size
    daily_basic_chunks: list[pd.DataFrame] = []
    adj_factor_chunks: list[pd.DataFrame] = []
    stock_st_chunks: list[pd.DataFrame] = []

    for i in range(0, len(all_dates), batch_size):
        chunk_dates = all_dates[i: i + batch_size]
        print(f"  批次 {i // batch_size + 1}: {chunk_dates[0]} ~ {chunk_dates[-1]}", flush=True)
        db = load_daily_basic_chunk(tushare_dir, chunk_dates, verbose=False)
        af = load_adj_factor_chunk(tushare_dir, chunk_dates, verbose=False)
        st = load_stock_st_chunk(tushare_dir, chunk_dates, verbose=False)
        if not db.empty:
            daily_basic_chunks.append(db)
        if not af.empty:
            adj_factor_chunks.append(af)
        if not st.empty:
            stock_st_chunks.append(st)

    daily_basic = pd.concat(daily_basic_chunks, ignore_index=True) if daily_basic_chunks else pd.DataFrame()
    adj_factor = pd.concat(adj_factor_chunks, ignore_index=True) if adj_factor_chunks else pd.DataFrame()
    stock_st = pd.concat(stock_st_chunks, ignore_index=True) if stock_st_chunks else pd.DataFrame()
    print(f"  daily_basic rows={len(daily_basic)}, adj_factor rows={len(adj_factor)}, "
          f"stock_st rows={len(stock_st)}")

    # 3. 合并
    print(f"\n[3/4] 合并为 hq 宽表")
    hq = merge_to_hq(hq, daily_basic, adj_factor, stock_st)

    # 4. 写出
    print(f"\n[4/4] 写出: {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    hq.sort_index().to_parquet(args.out)
    n_inst = hq.index.get_level_values("instrument").nunique()
    dt_min = hq.index.get_level_values("datetime").min()
    dt_max = hq.index.get_level_values("datetime").max()
    print(
        f"完成: shape={hq.shape} 股票数={n_inst} "
        f"日期范围={dt_min.date()}~{dt_max.date()} "
        f"total_elapsed={_format_elapsed(time.perf_counter() - t_total)}"
    )


if __name__ == "__main__":
    main()
