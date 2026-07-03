#!/usr/bin/env python3
"""增量更新：一条命令完成「增量拉取行情 → 追加 hq 缓存 → panel 尾部增量重建 → 离线 re-enrich」。

流程:
  1. update_market_cache: 检测缺失交易日 → 从 Tushare 拉取 → 追加写入 daily_hq.parquet
  2. update_panel_from_hq: 新增行 merge 进 panel，从缺口前一交易日起重算 ret/label，
     并从本地缓存离线并入 funda_* / industry_sw_l1

示例:
  uv run python scripts/update_panel.py --universe zz1000 --with-fundamentals --with-industry
  uv run python scripts/update_panel.py --universe zz1000 --dates 2026-06-30
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alphaagent.core.paths import (  # noqa: E402
    DISCLOSURE_CALENDAR_PATH,
    FUNDAMENTAL_QUARTERLY_PATH,
    INDUSTRY_SW_PATH,
    MARKET_HQ_PATH,
    PANEL_PATH,
)
from alphaagent.data import tushare_client  # noqa: E402
from alphaagent.data.market_fetch import update_market_cache  # noqa: E402
from alphaagent.data.panel import update_panel_from_hq  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="增量更新 hq 缓存 + panel")
    parser.add_argument("--panel", type=Path, default=PANEL_PATH, help="panel parquet 路径")
    parser.add_argument("--market-cache", type=Path, default=MARKET_HQ_PATH, help="hq 缓存路径")
    parser.add_argument(
        "--universe",
        type=str,
        default="zz1000",
        help="指数成分池；传 none 表示全市场按日拉取",
    )
    parser.add_argument(
        "--dates",
        type=str,
        nargs="+",
        default=None,
        help="增量指定交易日，如 2026-06-30（默认自动检测缺失日）",
    )
    parser.add_argument(
        "--with-fundamentals",
        action="store_true",
        help="并入季频基本面（离线读缓存 PIT 展开）",
    )
    parser.add_argument(
        "--with-industry",
        action="store_true",
        help="并入申万一级行业码 industry_sw_l1（离线读缓存）",
    )
    parser.add_argument(
        "--no-disclosure-distance",
        action="store_true",
        help="不计算 funda_days_since_disclose 等披露距离特征",
    )
    parser.add_argument("--quarterly", type=Path, default=FUNDAMENTAL_QUARTERLY_PATH)
    parser.add_argument("--disclosure", type=Path, default=DISCLOSURE_CALENDAR_PATH)
    parser.add_argument("--industry-path", type=Path, default=INDUSTRY_SW_PATH)
    parser.add_argument("--sleep", type=float, default=0.35, help="Tushare 请求间隔秒")
    parser.add_argument("--batch-size", type=int, default=40)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    tushare_client.configure(max_retries=args.max_retries, timeout=args.timeout)
    universe = None if args.universe.lower() == "none" else args.universe

    print("== 步骤 1/2: 增量拉取行情 → hq 缓存 ==")
    new_hq, backfill_since = update_market_cache(
        out_path=args.market_cache,
        universe=universe,
        dates=args.dates,
        sleep_sec=args.sleep,
        batch_size=args.batch_size,
    )
    if new_hq.empty:
        print("无新交易日，panel 已是最新，无需更新")
        return

    print(f"== 步骤 2/2: panel 增量重建（backfill_since={backfill_since}）==")
    update_panel_from_hq(
        new_hq,
        backfill_since,
        out_path=args.panel,
        with_fundamentals=args.with_fundamentals,
        quarterly_path=args.quarterly,
        disclosure_path=args.disclosure,
        include_disclosure_features=not args.no_disclosure_distance,
        with_industry=args.with_industry,
        industry_path=args.industry_path,
    )


if __name__ == "__main__":
    main()
