#!/usr/bin/env python3
"""查看因子库 catalog 与抽样摘要。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alphaagent.core.paths import FACTORZOO_DIR  # noqa: E402
from alphaagent.factor import FactorZoo  # noqa: E402
from alphaagent.factor.zoo import SimilarityMatrix  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="因子库信息")
    parser.add_argument("--lib", type=Path, default=FACTORZOO_DIR)
    parser.add_argument("--factor-id", type=str, default=None)
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    zoo = FactorZoo.open(args.lib)
    sim = SimilarityMatrix(zoo.paths, zoo.manifest.max_factors)

    if args.factor_id:
        meta = zoo.catalog.get(args.factor_id)
        if meta is None:
            raise SystemExit(f"因子不存在: {args.factor_id}")
        payload = {
            "factor_id": meta.factor_id,
            "name": meta.name,
            "expr": meta.expr,
            "col_idx": meta.col_idx,
            "status": meta.status.value,
            "finite_count": meta.finite_count,
            "created_at": meta.created_at,
            "extra": meta.extra,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"factor_id: {meta.factor_id}")
            print(f"name: {meta.name}")
            print(f"col_idx: {meta.col_idx}")
            print(f"status: {meta.status.value}")
            print(f"finite_count: {meta.finite_count}")
            print(f"expr:\n{meta.expr}")
        return

    rows = []
    for fid in zoo.catalog.list_factor_ids():
        meta = zoo.catalog.get(fid)
        if meta is None:
            continue
        rows.append(
            {
                "factor_id": fid,
                "name": meta.name,
                "col_idx": meta.col_idx,
                "finite_count": meta.finite_count,
                "coverage": meta.finite_count / zoo.manifest.n_rows,
            }
        )

    if args.json:
        print(
            json.dumps(
                {
                    "lib": str(zoo.paths.root),
                    "n_rows": zoo.manifest.n_rows,
                    "n_factors": zoo.n_factors,
                    "index_hash": zoo.manifest.index_hash,
                    "factors": rows,
                    "similarity_meta": sim.load_meta(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"lib: {zoo.paths.root}")
        print(f"n_rows={zoo.manifest.n_rows} n_factors={zoo.n_factors}")
        print(f"index_hash={zoo.manifest.index_hash}")
        print(f"panel_path={zoo.manifest.panel_path}")
        for row in rows:
            print(
                f"  {row['factor_id']}: col={row['col_idx']} "
                f"coverage={row['coverage']:.4f} name={row['name']}"
            )


if __name__ == "__main__":
    main()
