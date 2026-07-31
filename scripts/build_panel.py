#!/usr/bin/env python3
"""从本地 hq 缓存**离线**构建 Panel（不联网）。

前置：先用 scripts/fetch_market.py 拉取行情写入 hq 缓存，
      用 scripts/fetch_fundamentals.py 拉取基本面缓存。

示例:
  # 从 hq 缓存全量构建（含基本面 + 行业）:
  uv run python scripts/build_panel.py --with-fundamentals --with-industry
  # 仅量价 panel（不 enrich）:
  uv run python scripts/build_panel.py
  # 对已有 panel 仅补 enrich（不重建量价）:
  uv run python scripts/build_panel.py --enrich-only --with-industry
  # 增量更新（新交易日）请用: scripts/update_panel.py

默认同时写 logs/build_panel/*.log（可用 --no-log-file 关闭）。
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
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
from alphaagent.data.fundamental import enrich_panel_fundamentals, list_funda_columns  # noqa: E402
from alphaagent.data.industry import enrich_panel_industry  # noqa: E402
from alphaagent.data.panel import build_panel, load_panel, save_panel  # noqa: E402

DEFAULT_LOG_DIR = ROOT / "logs" / "build_panel"


class _Tee:
    def __init__(self, *streams) -> None:
        self._streams = streams

    def write(self, data: str) -> int:
        for s in self._streams:
            s.write(data)
            s.flush()
        return len(data)

    def flush(self) -> None:
        for s in self._streams:
            s.flush()

    def isatty(self) -> bool:
        return False


def _resolve_log_file(args: argparse.Namespace) -> Path | None:
    if args.no_log_file:
        return None
    if args.log_file is not None:
        path = Path(args.log_file)
        return path if path.is_absolute() else ROOT / path
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_LOG_DIR / f"build_panel_{stamp}.log"


def main() -> None:
    # 重定向到文件时默认块缓冲，强制行缓冲以便 nohup/tail 能看到进度
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
        sys.stderr.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="离线构建 Panel（从 hq 缓存）")
    parser.add_argument("--start", type=str, help="切片起始日期 YYYY-MM-DD（默认全量）")
    parser.add_argument("--end", type=str, help="切片结束日期 YYYY-MM-DD（默认全量）")
    parser.add_argument("--out", type=Path, default=PANEL_PATH, help="输出 panel parquet 路径")
    parser.add_argument(
        "--market-cache",
        type=Path,
        default=MARKET_HQ_PATH,
        help="hq 行情缓存路径（由 fetch_market.py 生成）",
    )
    parser.add_argument(
        "--no-universe-mask",
        action="store_true",
        help="不做可交易/非ST过滤（默认过滤）",
    )
    parser.add_argument(
        "--with-fundamentals",
        action="store_true",
        help="构建后 PIT 并入季频基本面（需先 fetch_fundamentals）",
    )
    parser.add_argument(
        "--enrich-only",
        action="store_true",
        help="仅对已有 panel 做 enrich（不重建量价）",
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
    parser.add_argument(
        "--with-industry",
        action="store_true",
        help="并入申万一级行业码 industry_sw_l1（缓存缺失时会联网拉取）",
    )
    parser.add_argument(
        "--refresh-industry",
        action="store_true",
        help="强制重新从 Tushare 拉取行业成员（忽略本地缓存）",
    )
    parser.add_argument(
        "--industry-path",
        type=Path,
        default=INDUSTRY_SW_PATH,
        help="申万一级行业成员缓存路径",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="日志路径（默认 logs/build_panel/build_panel_<ts>.log）",
    )
    parser.add_argument("--no-log-file", action="store_true", help="不写日志文件")
    args = parser.parse_args()

    log_path = _resolve_log_file(args)
    log_fp = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fp = log_path.open("a", encoding="utf-8")
        sys.stdout = _Tee(sys.__stdout__, log_fp)
        sys.stderr = _Tee(sys.__stderr__, log_fp)
        print(f"log_file: {log_path}", flush=True)

    t0 = time.perf_counter()
    try:
        if args.enrich_only:
            if not args.with_fundamentals and not args.with_industry:
                raise SystemExit(
                    "--enrich-only 须至少指定 --with-fundamentals 或 --with-industry"
                )
            print(f"enrich-only: loading {args.out} ...", flush=True)
            panel = load_panel(args.out)
            if args.with_fundamentals:
                print("enrich-only: fundamentals ...", flush=True)
                panel = enrich_panel_fundamentals(
                    panel,
                    quarterly_path=args.quarterly,
                    disclosure_path=args.disclosure,
                    include_disclosure_features=not args.no_disclosure_distance,
                )
            if args.with_industry:
                print("enrich-only: industry ...", flush=True)
                panel = enrich_panel_industry(
                    panel,
                    membership_path=args.industry_path,
                    refresh=args.refresh_industry,
                )
            save_panel(panel, args.out)
            funda_cols = list_funda_columns(panel.columns)
            print(f"已 enrich: {args.out} shape={panel.shape}", flush=True)
            if funda_cols:
                print(
                    f"基本面列 ({len(funda_cols)}): {funda_cols[:8]}"
                    f"{'...' if len(funda_cols) > 8 else ''}",
                    flush=True,
                )
            if args.with_industry:
                print("已并入行业列: industry_sw_l1", flush=True)
        else:
            build_panel(
                start=args.start,
                end=args.end,
                out_path=args.out,
                market_path=args.market_cache,
                universe_mask=not args.no_universe_mask,
                with_fundamentals=args.with_fundamentals,
                quarterly_path=args.quarterly,
                disclosure_path=args.disclosure,
                include_disclosure_features=not args.no_disclosure_distance,
                with_industry=args.with_industry,
                industry_path=args.industry_path,
                refresh_industry=args.refresh_industry,
            )
        print(f"total_elapsed: {time.perf_counter() - t0:.1f}s", flush=True)
    finally:
        if log_fp is not None:
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            log_fp.close()


if __name__ == "__main__":
    main()
