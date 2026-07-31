#!/usr/bin/env python3
"""从 Tushare 拉取日频行情并写入 market hq 缓存（artifacts/market/daily_hq.parquet）。

与 fetch_fundamentals.py 对称：本脚本**只拉取行情、落盘 hq 缓存**，不建 panel。
建 panel 请随后运行 scripts/build_panel.py（离线，从 hq 缓存构建）。

示例:
  # ZZ1000 成分并集全量:
  uv run python scripts/fetch_market.py --start 2015-01-01 --end 2026-06-30 --universe zz1000
  # 全市场按日:
  uv run python scripts/fetch_market.py --start 2024-01-01 --end 2024-01-31 --universe none
  # 增量补最新交易日:
  uv run python scripts/fetch_market.py --update --universe zz1000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alphaagent.core.paths import MARKET_HQ_PATH  # noqa: E402
from alphaagent.data import tushare_client  # noqa: E402
from alphaagent.data.market_fetch import fetch_and_save_market, update_market_cache  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="拉取 Tushare 日频行情 → hq 缓存")
    parser.add_argument("--start", type=str, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--out", type=Path, default=MARKET_HQ_PATH, help="hq 缓存 parquet 输出路径")
    parser.add_argument(
        "--universe",
        type=str,
        default="zz1000",
        help="指数成分池，如 zz1000 / zz500 / hs300；传 none 表示全市场按日拉取",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="增量更新：从缓存末日起补至最新交易日（自动填 gap）",
    )
    parser.add_argument(
        "--dates",
        type=str,
        nargs="+",
        default=None,
        help="增量指定交易日，如 2026-06-28（配合 --update）",
    )
    parser.add_argument("--sleep", type=float, default=0.35, help="Tushare 请求间隔秒")
    parser.add_argument("--batch-size", type=int, default=40, help="按股票池拉取时每批股票数（已弃用，保留兼容）")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="全市场按日拉取时的并发天数（V1 建议 2~4；过大易限流）",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=5,
        help="全市场按日拉取时每 N 个交易日落盘一次（中断可续跑）",
    )
    parser.add_argument(
        "--refresh-members",
        action="store_true",
        help="忽略成分缓存，重新从 Tushare 拉取指数成分（artifacts/index/）",
    )
    parser.add_argument("--max-retries", type=int, default=5, help="网络超时/限流最大重试次数")
    parser.add_argument("--timeout", type=int, default=60, help="单次 Tushare HTTP 请求超时秒数")
    args = parser.parse_args()

    tushare_client.configure(max_retries=args.max_retries, timeout=args.timeout)
    universe = None if args.universe.lower() == "none" else args.universe

    if args.update:
        new_hq, backfill_since = update_market_cache(
            out_path=args.out,
            universe=universe,
            dates=args.dates,
            sleep_sec=args.sleep,
            batch_size=args.batch_size,
        )
        if new_hq.empty:
            print("无新交易日，hq 缓存已是最新")
        else:
            print(f"增量完成: +{new_hq.shape[0]} 行（backfill_since={backfill_since}）")
        return

    if not args.start or not args.end:
        parser.error("全量拉取需指定 --start 和 --end；增量请用 --update")

    fetch_and_save_market(
        args.start,
        args.end,
        out_path=args.out,
        universe=universe,
        batch_size=args.batch_size,
        sleep_sec=args.sleep,
        refresh_members=args.refresh_members,
        workers=args.workers,
        checkpoint_every=args.checkpoint_every,
    )


if __name__ == "__main__":
    main()
