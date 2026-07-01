#!/usr/bin/env python3
"""panel 更新后增量/全量 realign 因子库。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seekalpha.core.paths import FACTORZOO_DIR, PANEL_PATH  # noqa: E402
from seekalpha.data.panel import load_panel  # noqa: E402
from seekalpha.factor.types import DEFAULT_INGEST_POLICY, IngestPolicy  # noqa: E402
from seekalpha.factor.zoo.realign import (  # noqa: E402
    DEFAULT_OVERLAP_VERIFY_DAYS,
    DEFAULT_WARMUP_DAYS,
    DEFAULT_WARMUP_RETRY_DAYS,
    incremental_realign_factorlib_to_panel,
    realign_factorlib_to_panel,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="panel 更新后 realign 因子库")
    parser.add_argument("--lib", type=Path, default=FACTORZOO_DIR, help="因子库根目录")
    parser.add_argument("--panel", type=Path, default=None, help="panel 路径（默认读 manifest）")
    parser.add_argument(
        "--full",
        action="store_true",
        help="跳过错量路径，强制全量 realign",
    )
    parser.add_argument("--warmup-days", type=int, default=DEFAULT_WARMUP_DAYS)
    parser.add_argument("--warmup-retry-days", type=int, default=DEFAULT_WARMUP_RETRY_DAYS)
    parser.add_argument(
        "--overlap-verify-days",
        type=int,
        default=DEFAULT_OVERLAP_VERIFY_DAYS,
        help="update 前最后 K 个交易日做 overlap 精确校验（默认 20）",
    )
    parser.add_argument("--train-start", type=str, default=DEFAULT_INGEST_POLICY.train_start)
    parser.add_argument("--eval-end", type=str, default=DEFAULT_INGEST_POLICY.val_end)
    parser.add_argument("--label-col", type=str, default=DEFAULT_INGEST_POLICY.label_col)
    parser.add_argument("--dry-run", action="store_true", help="只校验 overlap，不写 memmap/index")
    args = parser.parse_args()

    from seekalpha.factor import FactorZoo

    zoo = FactorZoo.open(args.lib, verify_hash=False)
    panel_path = args.panel or Path(zoo.manifest.panel_path)
    panel = load_panel(panel_path).sort_index()

    policy = IngestPolicy(
        train_start=args.train_start,
        val_end=args.eval_end,
        label_col=args.label_col,
    )

    t0 = time.perf_counter()
    if args.full:
        info = realign_factorlib_to_panel(
            args.lib,
            panel=panel,
            panel_path=panel_path,
            policy=policy,
        )
    else:
        info = incremental_realign_factorlib_to_panel(
            args.lib,
            panel=panel,
            panel_path=panel_path,
            policy=policy,
            warmup_days=args.warmup_days,
            warmup_retry_days=args.warmup_retry_days,
            overlap_verify_days=args.overlap_verify_days,
            dry_run=args.dry_run,
        )
    elapsed = time.perf_counter() - t0

    print(json.dumps(info, ensure_ascii=False, indent=2, default=str))
    print(f"elapsed={elapsed:.1f}s")
    mode = info.get("mode", "?")
    if args.dry_run:
        print("dry-run: 未写入 factorzoo")
    print(f"mode={mode}")


if __name__ == "__main__":
    main()
