#!/usr/bin/env python3
"""在外部 vnpy 数据上做 Alpha158 BASE vs 本轮因子的 SmartX 同口径对照。

本脚本由 run_discovery_cycle.py 调用。模型只训练到 2023 年，2024/2025/2026
严格作为测试集；回测使用生产 CSI300 PIT、S30-daily、择时和真实费率。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SmartX 口径 BASE vs MINING 对照")
    p.add_argument("--vnpy-root", type=Path, required=True)
    p.add_argument("--factor-table", type=Path, required=True)
    p.add_argument("--report-json", type=Path, required=True)
    p.add_argument("--train-end", default="2023-09-30")
    p.add_argument("--valid-end", default="2023-12-31")
    p.add_argument("--test-start", default="2024-01-01")
    p.add_argument("--capital", type=float, default=200_000)
    p.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    return p.parse_args()


def _num(value: Any) -> float:
    return float(value or 0.0)


def _as_date(value: Any):
    if value is None:
        return None
    if hasattr(value, "date") and not isinstance(value, datetime):
        try:
            return value.date()
        except Exception:  # noqa: BLE001
            pass
    if isinstance(value, datetime):
        return value.date()
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _year_stats(daily_df, periods: list[tuple[str, str, str]]) -> dict[str, dict]:
    from label_timing.train_label_timing import subperiod_return_stats

    return subperiod_return_stats(daily_df, periods)


def _summary(stats: dict) -> dict[str, float]:
    ret = _num(stats.get("total_return"))
    dd = _num(stats.get("max_ddpercent"))
    return {
        "return_pct": ret,
        "sharpe": _num(stats.get("sharpe_ratio")),
        "max_drawdown_pct": dd,
        "calmar": ret / abs(dd) if dd else 0.0,
        "commission": _num(stats.get("total_commission")),
        "turnover": _num(stats.get("total_turnover")),
    }


def _signal(dataset, model, test_start: str, st_symbols: set[str]):
    import polars as pl
    from buyable import EXCLUDED_PREFIXES
    from vnpy.alpha import Segment

    pred = model.predict(dataset, Segment.TEST)
    infer = dataset.fetch_infer(Segment.TEST)
    signal = infer.select(["datetime", "vt_symbol"]).with_columns(
        pl.Series(pred).alias("signal")
    )
    signal = signal.filter(pl.col("datetime") >= datetime.strptime(test_start, "%Y-%m-%d"))
    signal = signal.filter(
        ~pl.col("vt_symbol").str.slice(0, 3).is_in(list(EXCLUDED_PREFIXES))
        & ~pl.col("vt_symbol").is_in(list(st_symbols))
    )
    if getattr(signal["datetime"].dtype, "time_zone", None):
        signal = signal.with_columns(pl.col("datetime").dt.replace_time_zone(None))
    return signal


def _production_filter(lab, signal):
    from multihorizon_neutral.research_workflow_multihorizon_neutral import CSI300_LAB_PATH
    from pit_pool import apply_pit_filter, load_csi300_snapshots
    from small_capital_check import attach_timing
    from vnpy.alpha import AlphaLab

    csi300_lab = AlphaLab(CSI300_LAB_PATH)
    snapshots = load_csi300_snapshots(csi300_lab)
    signal, symbols = apply_pit_filter(signal, snapshots, "POOL=csi300(cycle)")
    return attach_timing(lab, signal, symbols), symbols


def _backtest(lab, signal, symbols: list[str], start: str, end: str, capital: float):
    from label_timing.equity_filter_strategy import EquityFilterStrategy
    from smallcap_live.config import CLOSE_RATE, MIN_COMMISSION, MIN_DAYS, N_DROP, OPEN_RATE, TOP_K
    from vnpy.alpha.strategy.backtesting import BacktestingEngine
    from vnpy.trader.constant import Interval

    contracts: dict = {}
    original = lab.contract_path.read_text(encoding="UTF-8") if lab.contract_path.exists() else ""
    if original.strip():
        try:
            contracts = json.loads(original)
        except json.JSONDecodeError:
            contracts = {}
    for symbol in symbols:
        contracts[symbol] = {
            "long_rate": OPEN_RATE,
            "short_rate": CLOSE_RATE,
            "size": 1,
            "pricetick": 0.01,
        }
    lab.contract_path.write_text(
        json.dumps(contracts, ensure_ascii=False, indent=2), encoding="UTF-8"
    )
    try:
        engine = BacktestingEngine(lab)
        engine.set_parameters(
            vt_symbols=symbols,
            interval=Interval.DAILY,
            start=datetime.strptime(start, "%Y-%m-%d"),
            end=datetime.strptime(end, "%Y-%m-%d"),
            capital=capital,
            min_commission=MIN_COMMISSION,
        )
        engine.add_strategy(
            EquityFilterStrategy,
            {
                "top_k": TOP_K,
                "n_drop": N_DROP,
                "min_days": MIN_DAYS,
                "open_rate": OPEN_RATE,
                "close_rate": CLOSE_RATE,
                "min_commission": MIN_COMMISSION,
            },
            signal,
        )
        engine.load_data()
        engine.run_backtesting()
        engine.calculate_result()
        return engine.calculate_statistics(), engine.daily_df
    finally:
        lab.contract_path.write_text(original, encoding="UTF-8")


def main() -> int:
    args = _parse_args()
    research = args.vnpy_root.resolve()
    if not (research / "smallcap_live" / "config.py").is_file():
        raise SystemExit(f"不是有效的 alpha_research 路径: {research}")
    # 下面会 chdir 到 vnpy 目录，相对路径必须先钉死成绝对路径
    args.factor_table = args.factor_table.expanduser().resolve()
    args.report_json = args.report_json.expanduser().resolve()
    if not args.factor_table.is_file():
        raise SystemExit(f"因子表不存在: {args.factor_table}")

    os.chdir(research)
    sys.path[:0] = [str(research), str(research.parent.parent)]

    import polars as pl
    from buyable import EXCLUDED_PREFIXES, get_st_symbols
    from label_timing.train_label_timing import build_variant_dataset
    from mining_inject import inject_mining_factors
    from multihorizon_neutral.research_workflow_multihorizon_neutral import (
        CSI300_LAB_PATH,
        LAB_PATH,
        TURNOVER_THRESHOLD,
        filter_liquid,
    )
    from multihorizon_neutral.research_workflow_multihorizon_neutral_v2 import (
        get_csi300_symbols_v2,
    )
    from smallcap_live.daily_signal_smallcap import bars_probe_latest
    from vnpy.alpha import AlphaLab, Segment
    from vnpy.alpha.model.models.lgb_model import LgbModel

    schema = pl.read_parquet_schema(args.factor_table)
    factor_cols = [c for c in schema if c not in ("datetime", "vt_symbol")]
    if not factor_cols or "label" in factor_cols or any(c.startswith("label_t") for c in factor_cols):
        raise SystemExit("因子表为空或含 label 列，拒绝训练")

    lab = AlphaLab(LAB_PATH)
    csi300_lab = AlphaLab(CSI300_LAB_PATH)
    st_symbols = get_st_symbols()
    liquid = filter_liquid(lab, "2024-01-01", threshold=TURNOVER_THRESHOLD)
    hist, current = get_csi300_symbols_v2(csi300_lab)
    available = {
        f.stem
        for f in lab.daily_path.glob("*.parquet")
        if not f.stem.startswith("._") and "." in f.stem
    }
    train_symbols = sorted((set(liquid) | set(hist) | set(current)) & available)
    train_symbols = [s for s in train_symbols if s[:3] not in EXCLUDED_PREFIXES]
    latest, _ = bars_probe_latest(lab, train_symbols[:20])
    if latest is None:
        raise SystemExit("无法探测 VNpy 最新行情日期")

    ft_dates = (
        pl.scan_parquet(args.factor_table)
        .select(pl.col("datetime").min().alias("lo"), pl.col("datetime").max().alias("hi"))
        .collect()
        .row(0, named=True)
    )
    factor_lo = _as_date(ft_dates["lo"])
    factor_hi = _as_date(ft_dates["hi"])
    train_lo = datetime.strptime("2010-01-04", "%Y-%m-%d").date()
    train_hi = datetime.strptime(args.train_end, "%Y-%m-%d").date()
    if factor_lo is None or factor_hi is None:
        raise SystemExit("因子表日期为空")
    if factor_lo > train_lo or factor_hi < train_hi:
        raise SystemExit(
            f"因子表未覆盖训练段: 因子 {factor_lo}~{factor_hi}，"
            f"训练需要 {train_lo}~{train_hi}。请更新 AlphaAgent panel 后重新导出。"
        )

    bar_end = latest if not hasattr(latest, "isoformat") else latest
    bar_end = _as_date(bar_end) or latest
    test_end_date = min(bar_end, factor_hi)
    if test_end_date < datetime.strptime(args.test_start, "%Y-%m-%d").date():
        raise SystemExit("因子表未覆盖任何测试日")
    if test_end_date < bar_end:
        print(
            f"[compare] 因子表止于 {factor_hi}，行情止于 {bar_end}；"
            f"测试截止日期对齐到因子表，避免训练段覆盖不足误报"
        )
    test_end = test_end_date.isoformat()

    print(
        f"[compare] Alpha158 T+5 train=2010-01-01~{args.train_end} "
        f"valid~{args.valid_end} test={args.test_start}~{test_end}"
    )
    print(f"[compare] 因子表覆盖 {factor_lo} ~ {factor_hi}  列={len(factor_cols)}")
    t0 = time.time()
    dataset = build_variant_dataset(
        lab,
        train_symbols,
        st_symbols,
        do_buyable=False,
        do_winsor=True,
        label_horizon=5,
        train_end=args.train_end,
        valid_end=args.valid_end,
        data_end=test_end,
        cache_name=None,
    )
    required_lo = _as_date(dataset.fetch_infer(Segment.TRAIN)["datetime"].min())
    required_hi = _as_date(dataset.fetch_infer(Segment.TEST)["datetime"].max())
    if required_lo is None or required_hi is None or factor_lo > required_lo or factor_hi < required_hi:
        raise SystemExit(
            f"因子覆盖不足: {factor_lo}~{factor_hi}，模型需要 {required_lo}~{required_hi}"
        )

    base_model = LgbModel()
    base_model.fit(dataset)
    base_signal = _signal(dataset, base_model, args.test_start, st_symbols)

    rows_before = dataset.fetch_infer(Segment.TEST).height
    inject_mining_factors(dataset, args.factor_table)
    if dataset.fetch_infer(Segment.TEST).height != rows_before:
        raise SystemExit("因子 join 改变样本行数")
    if dataset.fetch_infer(Segment.TEST).columns[-1] != "label":
        raise SystemExit("注入后 label 不在最后一列")

    mining_model = LgbModel()
    mining_model.fit(dataset)
    mining_signal = _signal(dataset, mining_model, args.test_start, st_symbols)
    lab.save_model(f"cycle_base__{args.run_id}", base_model)
    lab.save_model(f"cycle_mining__{args.run_id}", mining_model)

    base_signal, base_symbols = _production_filter(lab, base_signal)
    mining_signal, mining_symbols = _production_filter(lab, mining_signal)
    symbols = sorted(set(base_symbols) | set(mining_symbols))
    base_stats, base_daily = _backtest(
        lab, base_signal, symbols, args.test_start, test_end, args.capital
    )
    mining_stats, mining_daily = _backtest(
        lab, mining_signal, symbols, args.test_start, test_end, args.capital
    )

    periods = [(str(y), f"{y}-01-01", f"{y}-12-31") for y in (2024, 2025, 2026)]
    base_years = _year_stats(base_daily, periods)
    mining_years = _year_stats(mining_daily, periods)
    yearly: dict[str, dict] = {}
    for year, _, _ in periods:
        b, m = base_years.get(year) or {}, mining_years.get(year) or {}
        if not b or not m:
            continue
        yearly[year] = {
            "base": b,
            "mining": m,
            "delta_return_pct": _num(m.get("total_return%")) - _num(b.get("total_return%")),
            "delta_sharpe": _num(m.get("sharpe")) - _num(b.get("sharpe")),
        }

    base = _summary(base_stats)
    mining = _summary(mining_stats)
    deltas = [v["delta_sharpe"] for v in yearly.values()]
    stable_gain = (
        len(deltas) == 3
        and mining["sharpe"] - base["sharpe"] >= 0.05
        and mining["return_pct"] > base["return_pct"]
        and sum(v > 0 for v in deltas) >= 2
        and min(deltas) >= -0.10
    )
    report = {
        "run_id": args.run_id,
        "contract": {
            "features": f"Alpha158 + {len(factor_cols)} mined factors",
            "label": "T+5 close-to-close",
            "train": ["2010-01-01", args.train_end],
            "valid_end": args.valid_end,
            "test": [args.test_start, test_end],
            "portfolio": "CSI300 PIT / S30-daily / timing MA60 shift(1)",
            "capital": args.capital,
            "cost": "buy 1.5bp / sell 6.5bp / min CNY5",
        },
        "factor_ids": factor_cols,
        "base": base,
        "mining": mining,
        "delta": {
            "return_pct": mining["return_pct"] - base["return_pct"],
            "sharpe": mining["sharpe"] - base["sharpe"],
        },
        "yearly": yearly,
        "effective": stable_gain,
        "decision_rule": "全期ΔSharpe>=0.05且ΔRet>0；三年中至少两年ΔSharpe>0；最差年ΔSharpe>=-0.10",
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
