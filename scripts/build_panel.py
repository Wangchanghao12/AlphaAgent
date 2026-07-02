#!/usr/bin/env python3
"""
构建 Panel
- ZZ1000 全量: python scripts/build_panel.py --start 2024-01-01 --end 2024-06-30 --universe zz1000
- 全市场按日: python scripts/build_panel.py --start 2024-01-01 --end 2024-01-31
- 增量: python scripts/build_panel.py --update --universe zz1000
- 基本面: python scripts/fetch_fundamentals.py --periods 20240331 && python scripts/build_panel.py --with-fundamentals ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seekalpha.core.paths import (  # noqa: E402
    DISCLOSURE_CALENDAR_PATH,
    FUNDAMENTAL_QUARTERLY_PATH,
    PANEL_PATH,
)
from seekalpha.data import tushare_client  # noqa: E402
from seekalpha.data.fundamental import enrich_panel_fundamentals, list_funda_columns  # noqa: E402
from seekalpha.data.panel import build_panel, load_panel, save_panel, update_panel  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="构建 / 增量更新 Panel")
    parser.add_argument("--start", type=str, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--out", type=Path, default=PANEL_PATH, help="输出 parquet 路径")
    parser.add_argument(
        "--universe",
        type=str,
        default="zz1000",
        help="指数成分池，如 zz1000 / zz500 / hs300；传 none 表示全市场按日拉取",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="增量更新：从 panel 末日起补至最新交易日（自动填 gap）",
    )
    parser.add_argument(
        "--dates",
        type=str,
        nargs="+",
        default=None,
        help="增量指定交易日，如 2024-06-28",
    )
    parser.add_argument("--sleep", type=float, default=0.35, help="Tushare 请求间隔秒")
    parser.add_argument("--batch-size", type=int, default=40, help="按股票池拉取时每批股票数")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="网络超时/限流时最大重试次数（0 表示不重试）",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="单次 Tushare HTTP 请求超时秒数",
    )
    parser.add_argument(
        "--with-fundamentals",
        action="store_true",
        help="构建后 PIT 并入季频基本面（需先 fetch_fundamentals）",
    )
    parser.add_argument(
        "--enrich-only",
        action="store_true",
        help="仅对已有 panel 做基本面 enrich（不拉行情）",
    )
    parser.add_argument(
        "--quarterly",
        type=Path,
        default=FUNDAMENTAL_QUARTERLY_PATH,
        help="季频基本面缓存路径",
    )
    parser.add_argument(
        "--disclosure",
        type=Path,
        default=DISCLOSURE_CALENDAR_PATH,
        help="披露日历缓存路径",
    )
    parser.add_argument(
        "--no-disclosure-distance",
        action="store_true",
        help="不计算 funda_days_since_disclose 等披露距离特征",
    )
    args = parser.parse_args()

    tushare_client.configure(max_retries=args.max_retries, timeout=args.timeout)

    universe = None if args.universe.lower() == "none" else args.universe

    if args.enrich_only:
        panel = load_panel(args.out)
        panel = enrich_panel_fundamentals(
            panel,
            quarterly_path=args.quarterly,
            disclosure_path=args.disclosure,
            include_disclosure_features=not args.no_disclosure_distance,
        )
        save_panel(panel, args.out)
        funda_cols = list_funda_columns(panel.columns)
        print(f"已 enrich: {args.out} shape={panel.shape}")
        if funda_cols:
            print(f"基本面列 ({len(funda_cols)}): {funda_cols[:8]}{'...' if len(funda_cols) > 8 else ''}")
        return

    if args.update:
        panel = update_panel(
            args.out,
            dates=args.dates,
            sleep_sec=args.sleep,
            batch_size=args.batch_size,
            universe=universe,
        )
        if args.with_fundamentals:
            panel = enrich_panel_fundamentals(
                panel,
                quarterly_path=args.quarterly,
                disclosure_path=args.disclosure,
                include_disclosure_features=not args.no_disclosure_distance,
            )
            save_panel(panel, args.out)
        return

    if not args.start or not args.end:
        parser.error("全量构建需指定 --start 和 --end；增量请用 --update")

    build_panel(
        start=args.start,
        end=args.end,
        out_path=args.out,
        sleep_sec=args.sleep,
        universe=universe,
        batch_size=args.batch_size,
        with_fundamentals=args.with_fundamentals,
        quarterly_path=args.quarterly,
        disclosure_path=args.disclosure,
        include_disclosure_features=not args.no_disclosure_distance,
    )


if __name__ == "__main__":
    main()
