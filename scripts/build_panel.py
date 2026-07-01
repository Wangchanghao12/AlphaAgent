#!/usr/bin/env python3
"""
构建 Panel
- ZZ1000 全量: python scripts/build_panel.py --start 2024-01-01 --end 2024-06-30 --universe zz1000
- 全市场按日: python scripts/build_panel.py --start 2024-01-01 --end 2024-01-31
- 增量: python scripts/build_panel.py --update --universe zz1000
  （自动从 panel 末日起补至最新交易日，填 gap）
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seekalpha.core.paths import PANEL_PATH  # noqa: E402
from seekalpha.data import tushare_client  # noqa: E402
from seekalpha.data.panel import build_panel, update_panel  # noqa: E402


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
    args = parser.parse_args()

    tushare_client.configure(max_retries=args.max_retries, timeout=args.timeout)

    universe = None if args.universe.lower() == "none" else args.universe

    if args.update:
        update_panel(
            args.out,
            dates=args.dates,
            sleep_sec=args.sleep,
            batch_size=args.batch_size,
            universe=universe,
        )
        return

    if not args.start or not args.end:
        parser.error("全量构建需指定 --start 和 --end；增量请用 --update")
        return

    build_panel(
        start=args.start,
        end=args.end,
        out_path=args.out,
        sleep_sec=args.sleep,
        universe=universe,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
