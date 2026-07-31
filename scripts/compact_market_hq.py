#!/usr/bin/env python3
"""合并 daily_hq_parts → daily_hq.parquet，或快速检查缺失交易日（不整表合并）。

示例:
  # 只看缺哪些天（快，不 compact）
  python scripts/compact_market_hq.py --gaps --start 2018-01-01 --end 2026-07-31

  # 合并分片到主文件（一次性 concat，比旧逐片 merge 快很多）
  python scripts/compact_market_hq.py
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alphaagent.core.paths import MARKET_HQ_PATH  # noqa: E402
from alphaagent.data.market_fetch import (  # noqa: E402
    _collect_cached_trade_dates,
    _fetch_trade_dates,
    compact_market_hq,
    get_pro,
    hq_parts_dir,
    _list_hq_part_files,
)


def main() -> int:
    p = argparse.ArgumentParser(description="compact market hq / 检查缺口")
    p.add_argument("--path", type=Path, default=MARKET_HQ_PATH)
    p.add_argument("--gaps", action="store_true", help="只扫描缺失交易日，不合并")
    p.add_argument("--start", default="2018-01-01")
    p.add_argument("--end", default="2026-07-31")
    args = p.parse_args()

    out = args.path
    parts = _list_hq_part_files(hq_parts_dir(out))
    print(f"main: {out} exists={out.is_file()}")
    print(f"parts: {hq_parts_dir(out)} n={len(parts)}")

    if args.gaps:
        print("scanning dates (no compact)...")
        have = _collect_cached_trade_dates(out)
        all_days = _fetch_trade_dates(get_pro(), args.start, args.end)
        missing = [d for d in all_days if d not in have]
        print(f"have={len(have)} missing={len(missing)} range={args.start}~{args.end}")
        print(missing)
        print("by year:", dict(sorted(Counter(d[:4] for d in missing).items())))
        return 0

    if not parts and out.is_file():
        print("no parts to compact; main already stands alone")
        return 0

    compact_market_hq(out, verbose=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
