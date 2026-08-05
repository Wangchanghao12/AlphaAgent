#!/usr/bin/env python3
"""批量评估本轮 submit 因子在 train / val / holdout 三个窗上的表现。

用法:
  uv run python scripts/eval_mining_batch.py --registry artifacts/factorzoo/stock_1d/mining_delivered_registry.json

  # 只看本轮 submit 的因子（默认过滤 source=submit）
  uv run python scripts/eval_mining_batch.py --source-filter submit

  # 全部因子（包括 seed 导入）
  uv run python scripts/eval_mining_batch.py --source-filter all
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alphaagent.core.paths import PANEL_PATH  # noqa: E402
from alphaagent.data.panel import load_panel  # noqa: E402
from alphaagent.factor.eval import evaluate_factor  # noqa: E402
from alphaagent.factor.mining.registry_io import load_mining_registry  # noqa: E402
from alphaagent.factor.mining.submit import check_holdout_metrics  # noqa: E402
from alphaagent.factor.types import DEFAULT_LABEL_COL  # noqa: E402


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="批量评估挖掘因子的 train/val/holdout 表现")
    p.add_argument("--registry", type=Path, default=ROOT / "artifacts/factorzoo/stock_1d/mining_delivered_registry.json")
    p.add_argument("--panel", type=Path, default=PANEL_PATH)
    p.add_argument("--label-col", default=DEFAULT_LABEL_COL)
    p.add_argument("--train-start", default="2019-01-01")
    p.add_argument("--train-end", default="2023-12-31")
    p.add_argument("--val-start", default="2024-01-01")
    p.add_argument("--val-end", default="2025-12-31")
    p.add_argument("--holdout-start", default="2026-01-01")
    p.add_argument("--holdout-end", default="2026-07-31")
    p.add_argument(
        "--source-filter",
        default="submit",
        help="'submit'(默认)—只看挖掘 submit 的因子；'all'—全部注册的因子；逗号列表—指定来源",
    )
    p.add_argument("--min-holdout-ic", type=float, default=0.005, help="holdout 最小 |IC|（默认 0.005）")
    p.add_argument("--min-holdout-icir", type=float, default=0.05, help="holdout 最小 |ICIR|（默认 0.05）")
    p.add_argument("--panel-cache", type=Path, default=None, help="预加载 panel 的 pickle（加速多次评测）")
    return p.parse_args()


def _resolve(root: Path, expr_file: str) -> Path:
    p = Path(expr_file)
    return p if p.is_absolute() else root / p


def _pass_thresholds(
    summary: dict,
    min_ic: float,
    min_icir: float,
) -> tuple[bool, str]:
    """检查 holdout 门槛（同 check_holdout_metrics 但可调参）。"""
    ic = summary.get("ic")
    icir = summary.get("icir")
    reasons: list[str] = []
    if ic is None or abs(float(ic)) < min_ic:
        reasons.append(f"|ic|={abs(ic) if ic else 'NA'}")
    if icir is None or abs(float(icir)) <= min_icir:
        reasons.append(f"|icir|={abs(icir) if icir else 'NA'}")
    mls = summary.get("mls_fmb") or {}
    mean_ls = mls.get("mean_ls")
    if ic is not None and mean_ls is not None:
        ic_f, ls_f = float(ic), float(mean_ls)
        if ic_f > 0 and ls_f <= 0:
            reasons.append("ls_sign")
        if ic_f < 0 and ls_f >= 0:
            reasons.append("ls_sign")
    return len(reasons) == 0, ",".join(reasons) if reasons else "ok"


def _short(s: str | None, width: int = 10) -> str:
    if s is None:
        return "NA".rjust(width)
    return f"{float(s):.{max(4, width-4)}f}".rjust(width)


def _pct(v: float | None, width: int = 7) -> str:
    if v is None:
        return "NA".rjust(width)
    return f"{float(v)*100:.1f}%".rjust(width)


def main() -> int:
    args = _parse_args()

    registry = load_mining_registry(args.registry)
    if not registry:
        print("错误：registry 为空或找不到", file=sys.stderr)
        return 1
    print(f"registry: {args.registry}  ({len(registry)} 个记录)")

    # 过滤 source
    if args.source_filter == "all":
        selected = list(registry.items())
    elif args.source_filter == "submit":
        selected = [(k, v) for k, v in registry.items() if v.get("source") == "submit"]
    else:
        sources = set(s.strip() for s in args.source_filter.split(","))
        selected = [(k, v) for k, v in registry.items() if v.get("source") in sources]
    print(f"筛选 source={args.source_filter!r} → {len(selected)} 个因子\n")

    if not selected:
        print("没有符合筛选条件的因子。")
        return 0

    print("加载 panel...", end=" ", flush=True)
    t0 = time.perf_counter()
    if args.panel_cache and Path(args.panel_cache).is_file():
        import pickle
        panel = pickle.loads(Path(args.panel_cache).read_bytes())
        print(f"pickle cache ({time.perf_counter()-t0:.1f}s) shape={panel.shape}")
    else:
        panel = load_panel(args.panel)
        print(f"parquet ({time.perf_counter()-t0:.1f}s) shape={panel.shape}")

    rows: list[dict] = []
    errors: list[str] = []

    for factor_id, entry in selected:
        expr_file = entry.get("expression_file", "")
        if not expr_file:
            errors.append(f"{factor_id}: expression_file 为空")
            continue
        dsl_path = _resolve(ROOT, expr_file)
        if not dsl_path.is_file():
            errors.append(f"{factor_id}: 找不到表达式文件 {dsl_path}")
            continue
        expr = dsl_path.read_text(encoding="utf-8").strip()
        if not expr:
            errors.append(f"{factor_id}: 空表达式")
            continue

        # --- holdout ---
        ho_metrics = evaluate_factor(
            expr, panel,
            label_col=args.label_col,
            start=args.holdout_start, end=args.holdout_end,
        )
        ho_ok, ho_reason = _pass_thresholds(
            ho_metrics, args.min_holdout_ic, args.min_holdout_icir,
        )
        ho_summary = ho_metrics

        # --- val ---
        val_metrics = evaluate_factor(
            expr, panel,
            label_col=args.label_col,
            start=args.val_start, end=args.val_end,
        )
        val_summary = val_metrics

        # --- train ---
        train_metrics = evaluate_factor(
            expr, panel,
            label_col=args.label_col,
            start=args.train_start, end=args.train_end,
        )
        train_summary = train_metrics

        rows.append({
            "factor_id": factor_id,
            "name": entry.get("name", factor_id),
            "source": entry.get("source", "?"),
            "train_ic": train_summary.get("ic"),
            "train_icir": train_summary.get("icir"),
            "train_coverage": train_summary.get("coverage"),
            "val_ic": val_summary.get("ic"),
            "val_icir": val_summary.get("icir"),
            "val_coverage": val_summary.get("coverage"),
            "ho_ic": ho_summary.get("ic"),
            "ho_icir": ho_summary.get("icir"),
            "ho_coverage": ho_summary.get("coverage"),
            "ho_pass": ho_ok,
            "ho_reason": ho_reason,
        })

    # --- 打印表格 ---
    sep = "-" * 130
    header = (
        f"{'factor_id':22s} {'source':8s} "
        f"{'train_IC':10s} {'ICIR':8s} {'cov':7s}  "
        f"{'val_IC':10s} {'ICIR':8s} {'cov':7s}  "
        f"{'ho_IC':10s} {'ICIR':8s} {'cov':7s}  {'ho_pass?':10s}"
    )
    print(sep)
    print(header)
    print(sep)
    for r in rows:
        fname = r["factor_id"][:20]
        line = (
            f"{fname:22s} {r['source']:8s} "
            f"{_short(r['train_ic'])} {_short(r['train_icir'],8)} {_pct(r['train_coverage'])}  "
            f"{_short(r['val_ic'])} {_short(r['val_icir'],8)} {_pct(r['val_coverage'])}  "
            f"{_short(r['ho_ic'])} {_short(r['ho_icir'],8)} {_pct(r['ho_coverage'])}  "
            f"{'PASS' if r['ho_pass'] else 'FAIL':10s}"
        )
        print(line)
    print(sep)

    # --- 汇总 ---
    n_pass = sum(1 for r in rows if r["ho_pass"])
    print(f"\n共 {len(rows)} 个因子，holdout 通过 {n_pass} 个")
    if errors:
        print(f"\n跳过 {len(errors)} 个（因表达式文件缺失/空）：")
        for e in errors:
            print(f"  {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
