#!/usr/bin/env python3
"""
DSL 因子调试求值
- python scripts/eval_factor.py --expr "TS_MEAN($adj_close, 20)"
- python scripts/eval_factor.py --expr-file examples/ma20.dsl
注意: PowerShell 请用单引号包裹 --expr，或用 --expr-file
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seekalpha.core.paths import PANEL_PATH  # noqa: E402
from seekalpha.data.panel import load_panel, slice_panel  # noqa: E402
from seekalpha.dsl import eval_factor  # noqa: E402
from seekalpha.dsl.eval import collect_aux_intervals_from_expr  # noqa: E402
from seekalpha.factor import evaluate_factor  # noqa: E402
from seekalpha.factor.report import format_factor_report_json, print_factor_report  # noqa: E402
from seekalpha.factor.types import DEFAULT_LABEL_COL  # noqa: E402

_SHELL_STRIPPED_DOLLAR_RE = re.compile(r"(?<![A-Za-z0-9_])@[A-Za-z0-9_]+\b")


def load_expr(*, expr: str | None, expr_file: Path | None) -> str:
    if expr_file is not None:
        path = expr_file if expr_file.is_absolute() else ROOT / expr_file
        if not path.is_file():
            raise FileNotFoundError(f"表达式文件不存在: {path}")
        return path.read_text(encoding="utf-8").strip()
    if expr is None:
        raise ValueError("必须提供 --expr 或 --expr-file")
    if expr == "-":
        return sys.stdin.read().strip()
    return expr.strip()


def _warn_if_shell_stripped(expr: str) -> None:
    if _SHELL_STRIPPED_DOLLAR_RE.search(expr):
        print(
            "警告: 表达式里出现孤立的 @周期，可能是 shell 吃掉了 $列名。\n"
            "  推荐: python scripts/eval_factor.py --expr-file examples/ma20.dsl",
            file=sys.stderr,
        )


def _summary(series: pd.Series, sample: int) -> None:
    vals = series.to_numpy(dtype=float, copy=False)
    finite = pd.notna(vals)
    coverage = float(finite.mean()) if len(vals) else 0.0
    print(f"shape: {series.shape}")
    print(f"coverage: {coverage:.4f}")
    print(f"sample (后 {sample} 行):")
    for key, val in series.iloc[-sample:].items():
        dt, inst = key
        shown = "NaN" if pd.isna(val) else f"{float(val):.6g}"
        print(f"  {dt} {inst} -> {shown}")


def main() -> None:
    parser = argparse.ArgumentParser(description="DSL 表达式调试求值 / IC 报告")
    parser.add_argument("--panel", type=Path, default=PANEL_PATH)
    parser.add_argument("--report", action="store_true", help="输出 IC/ICIR/RANKIC/MLS 报告")
    parser.add_argument("--json", action="store_true", help="--report 时以 JSON 输出")
    parser.add_argument(
        "--label-col",
        type=str,
        default=DEFAULT_LABEL_COL,
        help="--report 时使用的标签列",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--expr", type=str)
    group.add_argument("--expr-file", type=Path)
    parser.add_argument("--sample", type=int, default=5)
    parser.add_argument(
        "--start-time",
        type=str,
        default=None,
        help="metrics 切片起始（DSL 仍在全量 panel 上求值）",
    )
    parser.add_argument(
        "--end-time",
        type=str,
        default=None,
        help="metrics 切片结束（DSL 仍在全量 panel 上求值）",
    )
    args = parser.parse_args()

    if args.expr is None and args.expr_file is None:
        args.expr = "TS_MEAN($adj_close, 20)"

    expr = load_expr(expr=args.expr, expr_file=args.expr_file)
    _warn_if_shell_stripped(expr)

    t_panel_load = time.perf_counter()
    panel_full = load_panel(args.panel)
    print(f"panel loaded in {(time.perf_counter() - t_panel_load) * 1000:.1f}ms")
    print(f"panel: {args.panel} shape={panel_full.shape}")

    aux_tags = collect_aux_intervals_from_expr(expr)
    if aux_tags:
        print(f"辅频: {aux_tags}")

    print(f"expr:\n{expr}\n")

    if args.report:
        t0 = time.perf_counter()
        metrics = evaluate_factor(
            expr,
            panel_full,
            label_col=args.label_col,
            start=args.start_time,
            end=args.end_time,
        )
        if args.json:
            print(format_factor_report_json(metrics))
        else:
            print_factor_report(metrics)
        print(f"elapsed_ms: {(time.perf_counter() - t0) * 1000:.1f}")
        return

    panel = slice_panel(panel_full, start=args.start_time, end=args.end_time)
    if args.start_time or args.end_time:
        print(f"eval slice: shape={panel.shape}")

    t0 = time.perf_counter()
    out = eval_factor(expr, panel)
    _summary(out, args.sample)
    print(f"elapsed_ms: {(time.perf_counter() - t0) * 1000:.1f}")


if __name__ == "__main__":
    main()
    # good
    r"""
    D:\AlphaAgent-Stock\data\factors\expressions\intraday_overnight_gap.dsl
    D:\AlphaAgent-Stock\data\factors\expressions\crowd_eff_fluency_vol18.dsl
    D:\AlphaAgent-Stock\data\factors\expressions\hl_div_amt_smooth20.dsl
    D:\AlphaAgent-Stock\data\factors\expressions\shadow_corr_diff_30.dsl
    D:\AlphaAgent-Stock\data\factors\expressions\cs_mom60_w_amt_filter.dsl # 多头不明显，空头明显，但排序还可以
    D:\AlphaAgent-Stock\data\factors\expressions\near_extreme_rev_min10.dsl # 头部明显，排序不行
    D:\AlphaAgent-Stock\data\factors\expressions\idio_qspread_win_20.dsl # good
    D:\AlphaAgent-Stock\data\factors\expressions\idio_tail_asym_20.dsl
    D:\AlphaAgent-Stock\data\factors\expressions\gap_streak_weighted_rank.dsl
    D:\AlphaAgent-Stock\data\factors\expressions\chip_peak_10_win_neut.dsl # 头部组一般

    # 分布近似
    D:\AlphaAgent-Stock\data\factors\expressions\massasym_z_crowd_meanratio_z.dsl 

    """