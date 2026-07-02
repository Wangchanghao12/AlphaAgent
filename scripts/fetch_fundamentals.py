#!/usr/bin/env python3
"""从 Tushare 拉取季频 fina_indicator 并写入 fundamental 缓存。

默认（VIP）：每期 fina_indicator_vip 拉**全 A 股**，合并后**每期落盘**。
panel enrich 时按 panel 内 instrument 自然 join，无需在拉数阶段指定 universe。

示例:
  uv run python scripts/fetch_fundamentals.py --start 2015-01-01 --end 2026-12-31
  uv run python scripts/fetch_fundamentals.py --periods 20240331 20240630
  # 积分不足、无 VIP 时逐股慢拉（须指定 universe）:
  uv run python scripts/fetch_fundamentals.py --start 2023-01-01 --end 2024-06-30 --universe zz1000 --no-vip
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seekalpha.core.paths import DISCLOSURE_CALENDAR_PATH, FUNDAMENTAL_QUARTERLY_PATH  # noqa: E402
from seekalpha.data import tushare_client  # noqa: E402
from seekalpha.data.fundamental_fetch import (  # noqa: E402
    fetch_and_save_periods,
    quarter_periods_between,
)
from seekalpha.data.tushare_client import get_pro  # noqa: E402
from seekalpha.data.universe import fetch_index_members, resolve_index_code  # noqa: E402


def _resolve_ts_codes(universe: str, start: str, end: str) -> list[str]:
    pro = get_pro()
    return fetch_index_members(pro, resolve_index_code(universe), start, end)


def _resolve_periods(args: argparse.Namespace) -> list[str]:
    if args.periods and (args.start or args.end):
        raise SystemExit("请只使用 --periods 或 --start/--end 之一")
    if args.periods:
        return sorted(args.periods)
    if args.start and args.end:
        periods = quarter_periods_between(args.start, args.end)
        if not periods:
            raise SystemExit(f"区间 {args.start} ~ {args.end} 内无标准季报季末")
        return periods
    raise SystemExit("须指定 --start/--end 或 --periods")


def main() -> None:
    parser = argparse.ArgumentParser(description="拉取 Tushare 季频财务指标缓存")
    parser.add_argument("--start", type=str, help="起始日期 YYYY-MM-DD（含区间内全部季报季末）")
    parser.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--periods",
        type=str,
        nargs="+",
        default=None,
        help="显式报告期列表，如 20240331 20240630（与 --start/--end 二选一）",
    )
    parser.add_argument(
        "--quarterly-out",
        type=Path,
        default=FUNDAMENTAL_QUARTERLY_PATH,
        help="季频 parquet 输出路径",
    )
    parser.add_argument(
        "--disclosure-out",
        type=Path,
        default=DISCLOSURE_CALENDAR_PATH,
        help="披露日历 parquet 输出路径",
    )
    parser.add_argument(
        "--universe",
        type=str,
        default=None,
        help="仅 --no-vip 时生效：限定逐股拉取的成分池",
    )
    parser.add_argument("--sleep", type=float, default=0.35, help="Tushare 请求间隔秒")
    parser.add_argument(
        "--no-vip",
        action="store_true",
        help="禁用 fina_indicator_vip，强制按股票逐只拉取（慢，仅积分不足时用）",
    )
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    tushare_client.configure(max_retries=args.max_retries, timeout=args.timeout)

    periods = _resolve_periods(args)
    range_start = args.start or f"{periods[0][:4]}-{periods[0][4:6]}-{periods[0][6:8]}"
    range_end = args.end or f"{periods[-1][:4]}-{periods[-1][4:6]}-{periods[-1][6:8]}"

    print(f"报告期共 {len(periods)} 个: {periods[0]} ~ {periods[-1]}")

    use_vip = not args.no_vip
    if use_vip:
        if args.universe:
            print(
                f"提示: VIP 模式忽略 --universe {args.universe!r}，"
                "全市场落盘；build_panel enrich 时按 panel 成分 join"
            )
        ts_codes = None
        print("拉取模式: vip 全市场（每期 1 次请求，每期合并后落盘）")
    else:
        if not args.universe:
            parser.error("--no-vip 须配合 --universe 指定成分池")
        ts_codes = _resolve_ts_codes(args.universe, range_start, range_end)
        print(f"拉取模式: 逐股（{len(ts_codes)} 只 × {len(periods)} 期）")

    fetch_and_save_periods(
        periods,
        ts_codes=ts_codes,
        quarterly_path=args.quarterly_out,
        disclosure_path=args.disclosure_out,
        sleep_sec=args.sleep,
        verbose=True,
        use_vip=use_vip,
    )


if __name__ == "__main__":
    main()
