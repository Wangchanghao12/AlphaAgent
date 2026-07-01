#!/usr/bin/env python3
"""
修补 panel 中异常的 adjfactor（单股重拉 Tushare adj_factor 并重算衍生列）。

默认用「adjfactor 断层」检测（adj≈1 跳到 >1.5 且 close 连续），避免把
新股上市初期 adjfactor=1 的正常行误当成 merge 失败。

用法:
  uv run python scripts/repair_panel_adjfactor.py --dry-run
  uv run python scripts/repair_panel_adjfactor.py
  uv run python scripts/repair_panel_adjfactor.py --mode adj_one   # 旧宽口径（易误报）
  uv run python scripts/repair_panel_adjfactor.py --instruments 600601.SH
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seekalpha.core.paths import PANEL_PATH  # noqa: E402
from seekalpha.data import tushare_client  # noqa: E402
from seekalpha.data.panel import (  # noqa: E402
    count_suspect_adjfactor_rows,
    find_adjfactor_jump_instruments,
    find_suspect_adjfactor_instruments,
    load_panel,
    repair_panel_adjfactor,
    save_panel,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="修补 panel 异常 adjfactor（方案 B）")
    parser.add_argument("--panel", type=Path, default=PANEL_PATH, help="输入 panel parquet")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="输出路径（默认覆盖 --panel）",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="写回前不备份原 panel 为 *.parquet.bak",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅统计可疑股票，不调用 Tushare、不写盘",
    )
    parser.add_argument(
        "--mode",
        choices=("jump", "adj_one"),
        default="jump",
        help="jump=adjfactor 断层（推荐）；adj_one=宽口径 adj≈1（易误报）",
    )
    parser.add_argument(
        "--instruments",
        type=str,
        nargs="+",
        default=None,
        help="仅修补指定 ts_code",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多修补前 N 只可疑股票（调试）",
    )
    parser.add_argument(
        "--min-real-factor",
        type=float,
        default=1.5,
        help="--mode adj_one 时判定「曾有真实复权」的 adjfactor 下限",
    )
    parser.add_argument("--sleep", type=float, default=0.35, help="Tushare 请求间隔秒")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="网络超时/限流时最大重试次数",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="单次 Tushare HTTP 请求超时秒数",
    )
    args = parser.parse_args()

    panel_path = args.panel
    out_path = args.out or panel_path

    panel = load_panel(panel_path)
    if args.instruments:
        suspects = args.instruments
    elif args.mode == "adj_one":
        suspects = find_suspect_adjfactor_instruments(
            panel, min_real_factor=args.min_real_factor
        )
    else:
        suspects = find_adjfactor_jump_instruments(panel)

    if args.limit is not None:
        suspects = suspects[: args.limit]

    n_adj_one = count_suspect_adjfactor_rows(panel, suspects) if suspects else 0
    print(f"panel: {panel_path} shape={panel.shape}")
    print(f"检测模式: {args.mode}")
    print(f"待检查股票: {len(suspects)} 只", end="")
    if args.mode == "adj_one":
        print(f"，其中 adj≈1 行: {n_adj_one} 条")
    else:
        print()
    if suspects[:10]:
        print(f"  样例: {', '.join(suspects[:10])}{' ...' if len(suspects) > 10 else ''}")
    if not suspects:
        print("未发现 adjfactor 断层，当前 panel 无需方案 B 修补。")

    if args.dry_run:
        print("dry-run: 未修改 panel")
        return

    if not suspects:
        return

    tushare_client.configure(max_retries=args.max_retries, timeout=args.timeout)
    panel, stats = repair_panel_adjfactor(
        panel,
        instruments=suspects,
        candidate_mode=args.mode,
        min_real_factor=args.min_real_factor,
        sleep_sec=args.sleep,
        verbose=True,
    )

    if stats["n_cells_updated"] == 0:
        print("未写入：panel 与 API 已全部一致。")
        return

    if out_path.resolve() == panel_path.resolve() and not args.no_backup:
        backup = panel_path.with_suffix(panel_path.suffix + ".bak")
        shutil.copy2(panel_path, backup)
        print(f"已备份: {backup}")

    save_panel(panel, out_path)
    print(f"已保存: {out_path} shape={panel.shape}")
    print(f"统计: {stats}")


if __name__ == "__main__":
    main()
