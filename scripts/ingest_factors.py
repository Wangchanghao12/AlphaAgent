#!/usr/bin/env python3
"""因子入库：registry / --expr-file / --expr-dir → DSL 求值 → 指标 → 查重 → factorzoo。

示例:
  uv run python scripts/ingest_factors.py --expr-file examples/factors/ma_dev.dsl
  uv run python scripts/ingest_factors.py --expr-dir artifacts/factorzoo/stock_1d/expressions
  uv run python scripts/ingest_factors.py --registry configs/factors/registry.example.json --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alphaagent.core.paths import FACTOR_REGISTRY_EXAMPLE, FACTORZOO_DIR  # noqa: E402
from alphaagent.data.panel import load_panel, slice_panel  # noqa: E402
from alphaagent.factor import (  # noqa: E402
    DEFAULT_INGEST_POLICY,
    FactorZoo,
    IngestPolicy,
    IngestResult,
    ingest_factor,
    list_factor_entries,
)
from alphaagent.factor.report import format_factor_report_json, print_factor_report  # noqa: E402


def _slug_factor_id(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", str(name).strip().lower())
    return re.sub(r"_+", "_", s).strip("_") or "factor"


def _load_expr(*, expr: str | None, expr_file: Path | None) -> str:
    if expr_file is not None:
        path = expr_file if expr_file.is_absolute() else ROOT / expr_file
        if not path.is_file():
            raise FileNotFoundError(f"表达式文件不存在: {path}")
        return path.read_text(encoding="utf-8").strip()
    if expr is None:
        raise ValueError("必须提供 --expr 或 --expr-file")
    return expr.strip()


def _resolve_entries(
    args: argparse.Namespace,
) -> list[tuple[str, str, str]]:
    if args.expr_dir is not None:
        expr_root = args.expr_dir if args.expr_dir.is_absolute() else ROOT / args.expr_dir
        from alphaagent.factor.expr_store import list_expr_dir_entries

        entries = list_expr_dir_entries(expr_root)
        if args.factor_id:
            entries = [e for e in entries if e[0] == args.factor_id]
            if not entries:
                raise SystemExit(f"目录中无因子: {args.factor_id}")
        return entries

    if args.expr_file is not None or args.expr is not None:
        expr = _load_expr(expr=args.expr, expr_file=args.expr_file)
        if args.factor_id:
            factor_id = args.factor_id
        elif args.name:
            factor_id = _slug_factor_id(args.name)
        elif args.expr_file is not None:
            path = args.expr_file if args.expr_file.is_absolute() else ROOT / args.expr_file
            factor_id = _slug_factor_id(path.stem)
        else:
            factor_id = "factor"
        name = args.name or factor_id
        return [(factor_id, name, expr)]

    entries = list_factor_entries(args.registry, repo_root=ROOT)
    if args.factor_id:
        entries = [e for e in entries if e[0] == args.factor_id]
        if not entries:
            raise SystemExit(f"registry 中无因子: {args.factor_id}")
    return entries


def _print_ingest_result(r: IngestResult, *, json_out: bool = False) -> None:
    if json_out:
        payload = {
            "factor_id": r.factor_id,
            "stored": r.stored,
            "col_idx": r.col_idx,
            "skipped_reason": r.skipped_reason,
            "metrics": r.metrics,
            "similarity": r.similarity,
            "extra": r.extra,
        }
        print(format_factor_report_json(payload))
        return

    print(f"\n因子: {r.factor_id}")
    print_factor_report(r.metrics)
    finite_ratio = r.metrics.get("finite_ratio")
    if finite_ratio is not None:
        print(f"  {'finite_ratio (全 panel)':<16} {float(finite_ratio):>34.4f}")
    skew = r.metrics.get("skew")
    kurt = r.metrics.get("kurt")
    if skew is not None and kurt is not None:
        print(f"  {'skew / kurt':<16} {float(skew):>15.4f} / {float(kurt):<15.4f}")

    if r.stored:
        print(f"\n入库结果: 已入库 (col_idx={r.col_idx})")
    else:
        print(f"\n入库结果: 未入库 ({r.skipped_reason or 'unknown'})")

    if r.similarity:
        max_corr = r.similarity.get("max_abs_corr")
        if max_corr is not None:
            print(f"  max_cs_corr: {float(max_corr):.4f}")
        for nb in r.similarity.get("top_neighbors") or []:
            print(f"    ~{nb.get('factor_id')} cs_corr={nb.get('cs_corr'):.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="因子入库（registry 或 --expr-file）")
    parser.add_argument("--lib", type=Path, default=FACTORZOO_DIR, help="因子库根目录")
    parser.add_argument(
        "--registry",
        type=Path,
        default=FACTOR_REGISTRY_EXAMPLE,
        help="因子清单 JSON（与 --expr-file 互斥）",
    )
    parser.add_argument("--panel", type=Path, default=None, help="panel 路径（默认读 manifest）")
    expr_group = parser.add_mutually_exclusive_group()
    expr_group.add_argument("--expr-file", type=Path, help="DSL 表达式文件路径")
    expr_group.add_argument("--expr", type=str, help="DSL 表达式字符串")
    expr_group.add_argument(
        "--expr-dir",
        type=Path,
        help="批量入库：目录下全部 *.dsl（factor_id=文件名 stem）",
    )
    parser.add_argument("--name", type=str, default=None, help="因子显示名（配合 --expr-file）")
    parser.add_argument("--factor-id", type=str, default=None, help="因子 ID；registry 模式下可筛选单个因子")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="只算指标与查重，不写入 factorzoo")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出指标与入库结果")
    parser.add_argument("--max-cs-corr", type=float, default=0.8)
    parser.add_argument("--similar-top-k", type=int, default=3)
    parser.add_argument("--label-col", type=str, default=DEFAULT_INGEST_POLICY.label_col)
    parser.add_argument("--train-start", type=str, default=DEFAULT_INGEST_POLICY.train_start)
    parser.add_argument("--eval-end", type=str, default=DEFAULT_INGEST_POLICY.val_end)
    parser.add_argument("--start-time", type=str, default=None)
    parser.add_argument("--end-time", type=str, default=None)
    parser.add_argument(
        "--clip",
        nargs=2,
        type=float,
        metavar=("LOWER", "UPPER"),
        default=None,
        help="入库前全局分位 clip，如 --clip 1 99",
    )
    args = parser.parse_args()

    zoo = FactorZoo.open(args.lib)
    panel_path = args.panel or Path(zoo.manifest.panel_path)
    panel = load_panel(panel_path)
    if args.start_time or args.end_time:
        panel = slice_panel(panel, start=args.start_time, end=args.end_time)
    if len(panel) != zoo.manifest.n_rows:
        raise SystemExit(
            f"panel 行数 {len(panel)} != 库 n_rows {zoo.manifest.n_rows}；"
            "请用全量 panel 初始化库，或去掉日期切片"
        )
    panel = panel.sort_index()

    try:
        entries = _resolve_entries(args)
    except FileNotFoundError as e:
        raise SystemExit(str(e)) from e
    if not entries:
        raise SystemExit("无待入库因子")

    clip_pct = (args.clip[0], args.clip[1]) if args.clip else None
    policy = IngestPolicy(
        train_start=args.train_start,
        val_end=args.eval_end,
        label_col=args.label_col,
        max_cs_corr=args.max_cs_corr,
        similar_top_k=args.similar_top_k,
        clip_pct=clip_pct,
    )
    t0 = time.perf_counter()
    results = []
    for fid, name, expr in entries:
        results.append(
            ingest_factor(
                zoo,
                factor_id=fid,
                name=name,
                expr=expr,
                panel=panel,
                policy=policy,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
            )
        )

    elapsed = time.perf_counter() - t0
    stored = sum(1 for r in results if r.stored)
    skipped = len(results) - stored
    if args.dry_run:
        print("模式: dry-run（不写入 factorzoo）")
    print(f"完成: stored={stored} skipped={skipped} elapsed={elapsed:.1f}s")
    for r in results:
        _print_ingest_result(r, json_out=args.json)


if __name__ == "__main__":
    main()
