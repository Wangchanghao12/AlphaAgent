#!/usr/bin/env python3
"""滚动 probe：模拟多个 append 窗口下的增量 realign overlap 校验（只读，不写盘）。

panel 与因子库已对齐（manifest.n_rows == len(panel)）时，用历史 memmap 前缀
假装「刚 append 了 K 个交易日」，测试增量路径能否通过 overlap。

非 pytest 用例；在仓库根目录运行：

  uv run python tests/test_factor/rolling_probe_incremental_realign.py
  uv run python tests/test_factor/rolling_probe_incremental_realign.py --windows 1,3,5,10,20
  uv run python tests/test_factor/rolling_probe_incremental_realign.py --factor-id idio_qspread_win_20
  uv run python tests/test_factor/rolling_probe_incremental_realign.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from alphaagent.core.paths import FACTORZOO_DIR  # noqa: E402
from alphaagent.data.panel import load_panel  # noqa: E402
from alphaagent.factor.types import DEFAULT_INGEST_POLICY, IngestPolicy  # noqa: E402
from alphaagent.factor.zoo.realign import (  # noqa: E402
    DEFAULT_OVERLAP_VERIFY_DAYS,
    DEFAULT_WARMUP_DAYS,
    DEFAULT_WARMUP_RETRY_DAYS,
    rolling_probe_incremental_realign,
)


def _parse_int_list(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def _print_summary(report: dict) -> None:
    print("=" * 72)
    print(f"lib: {report['lib']}")
    print(
        f"n_rows={report['n_rows']} n_factors={report['n_factors']} "
        f"overlap_verify_days={report['overlap_verify_days']} "
        f"warmup={report['warmup_days']}/{report['warmup_retry_days']}"
    )
    print("-" * 72)
    print(
        f"{'K_days':>6} {'append_rows':>11} {'update_start':>12} "
        f"{'inc':>4} {'fallback':>8} {'status':>12}"
    )
    for w in report["windows"]:
        n_inc = len(w.get("incremental_factors") or [])
        n_fb = len(w.get("fallback_factors") or [])
        n_f = w.get("n_factors") or 0
        if n_f == 0:
            status = "empty"
        elif n_fb == 0:
            status = "ALL_OK"
        elif n_inc == 0:
            status = "ALL_FAIL"
        else:
            status = "PARTIAL"
        print(
            f"{w.get('append_trade_days', '?'):>6} "
            f"{w.get('append_rows', '?'):>11} "
            f"{w.get('update_start', '?'):>12} "
            f"{n_inc:>4} {n_fb:>8} {status:>12}"
        )

    print("-" * 72)
    print("因子明细（仅列出 fallback 窗口）:")
    for w in report["windows"]:
        fb = w.get("fallback_factors") or []
        if not fb:
            continue
        print(
            f"  K={w.get('append_trade_days')} update={w.get('update_start')} "
            f"fallback={fb}"
        )
        for fid in fb[:3]:
            fr = (w.get("factor_reports") or {}).get(fid, {})
            samples = fr.get("samples") or []
            if samples:
                s0 = samples[0]
                print(
                    f"    ~{fid}: n_mismatch={fr.get('n_mismatch')} "
                    f"sample={s0.get('datetime')} {s0.get('instrument')} "
                    f"stored={s0.get('stored')} computed={s0.get('computed')}"
                )
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description="滚动 probe 增量 realign（只读）")
    parser.add_argument("--lib", type=Path, default=FACTORZOO_DIR)
    parser.add_argument("--panel", type=Path, default=None)
    parser.add_argument(
        "--windows",
        type=str,
        default="1,2,3,5,10,20",
        help="模拟尾部追加的交易日个数，逗号分隔",
    )
    parser.add_argument("--warmup-days", type=int, default=DEFAULT_WARMUP_DAYS)
    parser.add_argument("--warmup-retry-days", type=int, default=DEFAULT_WARMUP_RETRY_DAYS)
    parser.add_argument("--overlap-verify-days", type=int, default=DEFAULT_OVERLAP_VERIFY_DAYS)
    parser.add_argument("--train-start", type=str, default=DEFAULT_INGEST_POLICY.train_start)
    parser.add_argument("--factor-id", type=str, default=None, help="仅测指定因子")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = parser.parse_args()

    from alphaagent.factor import FactorZoo

    zoo = FactorZoo.open(args.lib, verify_hash=False)
    panel_path = args.panel or Path(zoo.manifest.panel_path)
    panel = load_panel(panel_path).sort_index()

    policy = IngestPolicy(train_start=args.train_start)
    factor_ids = [args.factor_id] if args.factor_id else None

    t0 = time.perf_counter()
    report = rolling_probe_incremental_realign(
        args.lib,
        panel=panel,
        append_trade_days=_parse_int_list(args.windows),
        policy=policy,
        warmup_days=args.warmup_days,
        warmup_retry_days=args.warmup_retry_days,
        overlap_verify_days=args.overlap_verify_days,
        factor_ids=factor_ids,
    )
    report["elapsed_sec"] = round(time.perf_counter() - t0, 1)
    report["panel_path"] = str(panel_path)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        _print_summary(report)
        print(f"elapsed={report['elapsed_sec']}s（只读 probe，未修改 factorzoo）")


if __name__ == "__main__":
    main()
