"""从 Tushare 拉取季频财务指标并写入 quarterly / disclosure 缓存。"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from seekalpha.core.paths import DISCLOSURE_CALENDAR_PATH, FUNDAMENTAL_DIR, FUNDAMENTAL_QUARTERLY_PATH
from seekalpha.data.fundamental import validate_quarter_report_ends
from seekalpha.data.tushare_client import call_with_retry, get_pro

# fina_indicator 字段 → panel 列名
FINA_INDICATOR_COLUMN_MAP: dict[str, str] = {
    "roe": "funda_roe",
    "roa": "funda_roa",
    "debt_to_assets": "funda_debt_to_assets",
    "netprofit_yoy": "funda_netprofit_yoy",
    "or_yoy": "funda_or_yoy",
    "tr_yoy": "funda_tr_yoy",
    "bps": "funda_bps",
    "eps": "funda_eps",
    "grossprofit_margin": "funda_grossprofit_margin",
    "netprofit_margin": "funda_netprofit_margin",
    "ocfps": "funda_ocfps",
    "working_capital": "funda_fs_working_capital",
    "ebit": "funda_fs_ebit",
    "rd_exp": "funda_fs_rd_exp",
    "profit_dedt": "funda_profit_dedt",
    "current_ratio": "funda_current_ratio",
    "quick_ratio": "funda_quick_ratio",
}

FINA_INDICATOR_API_FIELDS = (
    "ts_code,ann_date,end_date,"
    + ",".join(FINA_INDICATOR_COLUMN_MAP.keys())
)

_STANDARD_QUARTER_ENDS = ("0331", "0630", "0930", "1231")
_QUARTER_END_MD = ((3, 31), (6, 30), (9, 30), (12, 31))


def quarter_periods_between(start: str, end: str) -> list[str]:
    """返回 [start, end] 内所有标准 A 股季报季末（YYYYMMDD）。"""
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    if start_ts > end_ts:
        raise ValueError(f"start 不能晚于 end: {start} > {end}")

    periods: list[str] = []
    for year in range(start_ts.year, end_ts.year + 1):
        for month, day in _QUARTER_END_MD:
            qe = pd.Timestamp(year=year, month=month, day=day)
            if start_ts <= qe <= end_ts:
                periods.append(qe.strftime("%Y%m%d"))
    return periods


def _normalize_period(period: str) -> str:
    p = period.replace("-", "")
    if len(p) != 8:
        raise ValueError(f"period 须为 YYYYMMDD，收到: {period!r}")
    if p[4:] not in _STANDARD_QUARTER_ENDS:
        raise ValueError(f"非标准季报季末: {period!r}")
    return p


def _dedupe_fina_raw(df: pd.DataFrame) -> pd.DataFrame:
    """同一 (ts_code, end_date) 保留 ann_date 最新的一条。"""
    if df.empty:
        return df
    out = df.copy()
    out["ann_date"] = pd.to_datetime(out["ann_date"], errors="coerce")
    out["end_date"] = pd.to_datetime(out["end_date"], errors="coerce")
    out = out.dropna(subset=["ts_code", "end_date", "ann_date"])
    out = out.sort_values(["ts_code", "end_date", "ann_date"])
    return out.groupby(["ts_code", "end_date"], as_index=False).tail(1)


def fetch_fina_indicator_period(
    period: str,
    *,
    ts_codes: list[str] | None = None,
    sleep_sec: float = 0.35,
    verbose: bool = True,
    use_vip: bool = True,
) -> pd.DataFrame:
    """拉取单个报告期的 fina_indicator 原始表。

    use_vip=True 时用 ``fina_indicator_vip`` 拉**全市场**（每期 1 次请求，完整落盘）。
    use_vip=False 时按 ts_codes 逐股拉取（须指定股票列表）。
    """
    period = _normalize_period(period)
    pro = get_pro()

    if use_vip:
        if verbose:
            print(f"  fina_indicator_vip period={period}（全市场）")
        raw = call_with_retry(
            pro.fina_indicator_vip,
            period=period,
            fields=FINA_INDICATOR_API_FIELDS,
            label=f"fina_indicator_vip_{period}",
        )
        time.sleep(sleep_sec)
        return _dedupe_fina_raw(raw)

    if not ts_codes:
        raise ValueError("无 VIP 权限时须指定 ts_codes（--no-vip 且 --universe）")

    chunks: list[pd.DataFrame] = []
    n = len(ts_codes)
    for i, code in enumerate(ts_codes):
        if verbose and (i == 0 or (i + 1) % 50 == 0 or i + 1 == n):
            print(f"  fina_indicator [{i + 1}/{n}] {code} period={period}")
        part = call_with_retry(
            pro.fina_indicator,
            ts_code=code,
            period=period,
            fields=FINA_INDICATOR_API_FIELDS,
            label=f"fina_indicator_{code}_{period}",
        )
        if part is not None and not part.empty:
            chunks.append(part)
        time.sleep(sleep_sec)

    if not chunks:
        return pd.DataFrame()
    non_empty = [c for c in chunks if not c.empty]
    if not non_empty:
        return pd.DataFrame()
    return _dedupe_fina_raw(pd.concat(non_empty, ignore_index=True))


def raw_fina_to_quarterly(raw: pd.DataFrame) -> pd.DataFrame:
    """fina_indicator 原始表 → (report_end, instrument) 索引的 panel 列。"""
    if raw.empty:
        return pd.DataFrame()

    df = raw.copy()
    df["instrument"] = df["ts_code"]
    df["report_end"] = pd.to_datetime(df["end_date"])
    rename = {k: v for k, v in FINA_INDICATOR_COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)
    value_cols = list(rename.values())
    out = df.set_index(["report_end", "instrument"])[value_cols]
    return out.sort_index()


def raw_fina_to_disclosure_events(raw: pd.DataFrame) -> pd.DataFrame:
    """从 fina_indicator 提取披露日历 long 表。"""
    if raw.empty:
        return pd.DataFrame(columns=["report_end", "instrument", "disclosure"])

    df = raw.copy()
    df["report_end"] = pd.to_datetime(df["end_date"])
    df["instrument"] = df["ts_code"]
    df["disclosure"] = pd.to_datetime(df["ann_date"], errors="coerce")
    return df[["report_end", "instrument", "disclosure"]].dropna()


def disclosure_events_to_wide(events: pd.DataFrame) -> pd.DataFrame:
    """long 披露表 → 宽表 (report_end × instrument)。"""
    if events.empty:
        return pd.DataFrame()
    wide = events.pivot_table(
        index="report_end",
        columns="instrument",
        values="disclosure",
        aggfunc="last",
    )
    wide.index = pd.to_datetime(wide.index)
    return wide.sort_index()


def merge_quarterly(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """合并季频缓存，同键以 new 为准。"""
    if existing.empty:
        return new.sort_index()
    if new.empty:
        return existing.sort_index()
    combined = pd.concat([existing, new])
    return combined[~combined.index.duplicated(keep="last")].sort_index()


def merge_disclosure_wide(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """合并披露宽表：新数据覆盖同 (report_end, instrument) 单元格。"""
    if existing.empty:
        return new.sort_index()
    if new.empty:
        return existing.sort_index()

    all_index = existing.index.union(new.index)
    all_cols = existing.columns.union(new.columns)
    base = existing.reindex(index=all_index, columns=all_cols)
    overlay = new.reindex(index=all_index, columns=all_cols)
    return base.combine_first(overlay).sort_index()


def save_quarterly(df: pd.DataFrame, path: Path | str = FUNDAMENTAL_QUARTERLY_PATH) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out)
    return out


def save_disclosure_calendar(wide: pd.DataFrame, path: Path | str = DISCLOSURE_CALENDAR_PATH) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wide.to_parquet(out)
    if not wide.empty:
        validate_quarter_report_ends(out)
    return out


def load_quarterly_cache(path: Path | str = FUNDAMENTAL_QUARTERLY_PATH) -> pd.DataFrame:
    p = Path(path)
    if not p.is_file():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    if df.index.names != ["report_end", "instrument"]:
        if "datetime" in df.index.names:
            df = df.rename_axis(index={"datetime": "report_end"})
        if "code" in df.index.names:
            df = df.rename_axis(index={"code": "instrument"})
    return df.sort_index()


def load_disclosure_wide(path: Path | str = DISCLOSURE_CALENDAR_PATH) -> pd.DataFrame:
    p = Path(path)
    if not p.is_file():
        return pd.DataFrame()
    wide = pd.read_parquet(p)
    wide.index = pd.to_datetime(wide.index)
    return wide.sort_index()


def fetch_and_save_periods(
    periods: list[str],
    *,
    ts_codes: list[str] | None = None,
    quarterly_path: Path | str = FUNDAMENTAL_QUARTERLY_PATH,
    disclosure_path: Path | str = DISCLOSURE_CALENDAR_PATH,
    sleep_sec: float = 0.35,
    verbose: bool = True,
    use_vip: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """拉取多个报告期并增量写入缓存。"""
    quarterly_acc = load_quarterly_cache(quarterly_path)
    disclosure_acc = load_disclosure_wide(disclosure_path)

    for period in periods:
        period = _normalize_period(period)
        if verbose:
            print(f"拉取 fina_indicator: {period}")
        raw = fetch_fina_indicator_period(
            period,
            ts_codes=ts_codes,
            sleep_sec=sleep_sec,
            verbose=verbose,
            use_vip=use_vip,
        )
        if raw.empty:
            if verbose:
                print(f"  警告: {period} 无数据")
            continue

        q = raw_fina_to_quarterly(raw)
        events = raw_fina_to_disclosure_events(raw)
        wide = disclosure_events_to_wide(events)

        quarterly_acc = merge_quarterly(quarterly_acc, q)
        disclosure_acc = merge_disclosure_wide(disclosure_acc, wide)
        save_quarterly(quarterly_acc, quarterly_path)
        save_disclosure_calendar(disclosure_acc, disclosure_path)
        if verbose:
            n_inst = q.index.get_level_values("instrument").nunique()
            print(
                f"  本期 +{len(q)} 条（{n_inst} 只股票）"
                f" → 已落盘 cumulative={quarterly_acc.shape}"
            )

    if verbose:
        print(f"季频缓存: {quarterly_path} shape={quarterly_acc.shape}")
        print(f"披露缓存: {disclosure_path} shape={disclosure_acc.shape}")
    return quarterly_acc, disclosure_acc


def ensure_fundamental_dir() -> Path:
    FUNDAMENTAL_DIR.mkdir(parents=True, exist_ok=True)
    return FUNDAMENTAL_DIR
