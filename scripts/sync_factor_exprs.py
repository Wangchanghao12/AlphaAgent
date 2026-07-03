#!/usr/bin/env python3
"""从 factorzoo catalog 同步 DSL 到 {lib}/expressions/。

示例:
  uv run python scripts/sync_factor_exprs.py
  uv run python scripts/sync_factor_exprs.py --lib artifacts/factorzoo/stock_1d --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alphaagent.core.paths import FACTORZOO_DIR  # noqa: E402
from alphaagent.factor import FactorZoo  # noqa: E402
from alphaagent.factor.expr_store import export_zoo_expressions  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 factorzoo → {lib}/expressions")
    parser.add_argument("--lib", type=Path, default=FACTORZOO_DIR, help="因子库根目录")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="DSL 输出目录（默认 {lib}/expressions）",
    )
    parser.add_argument("--no-overwrite", action="store_true", help="已存在 .dsl 时跳过")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    args = parser.parse_args()

    zoo = FactorZoo.open(args.lib)
    out_dir = args.out or (args.lib / "expressions")
    factor_ids = zoo.catalog.list_factor_ids()
    if not factor_ids:
        print("因子库为空，无 DSL 可导出")
        return 0

    if args.dry_run:
        for fid in factor_ids:
            meta = zoo.catalog.get(fid)
            path = out_dir / f"{fid}.dsl"
            print(f"  {fid} -> {path}")
        print(f"共 {len(factor_ids)} 个（dry-run）")
        return 0

    written = export_zoo_expressions(
        zoo,
        expr_dir=out_dir,
        overwrite=not args.no_overwrite,
    )
    print(f"已写入 {len(written)} 个 DSL -> {out_dir.resolve()}")
    for fid, path in written:
        print(f"  {fid}.dsl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
