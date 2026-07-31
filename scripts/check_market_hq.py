#!/usr/bin/env python3
"""检查 artifacts/market/daily_hq.parquet 是否可用来建 panel。

示例:
  python scripts/check_market_hq.py
  python scripts/check_market_hq.py --path /mnt/.../artifacts/market/daily_hq.parquet
  python scripts/check_market_hq.py --build-smoke   # 额外试建一小段 panel
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alphaagent.core.paths import MARKET_HQ_PATH  # noqa: E402
from alphaagent.data.market_fetch import HQ_COLUMNS, load_market_hq  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="校验 market hq 缓存")
    p.add_argument("--path", type=Path, default=MARKET_HQ_PATH)
    p.add_argument(
        "--build-smoke",
        action="store_true",
        help="用该 hq 试跑 build_panel（写出到临时路径，不覆盖正式 panel）",
    )
    args = p.parse_args()

    path = args.path
    if not path.is_file():
        print(f"FAIL: 文件不存在: {path}")
        return 2

    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"path: {path}")
    print(f"size: {size_mb:.1f} MB")

    hq = load_market_hq(path)
    if hq.empty:
        print("FAIL: parquet 为空")
        return 1

    print(f"shape: {hq.shape}")
    print(f"index names: {list(hq.index.names)}")
    print(f"columns ({len(hq.columns)}): {list(hq.columns)}")

    ok = True
    if list(hq.index.names) != ["datetime", "instrument"]:
        print(f"FAIL: 索引应为 (datetime, instrument)，实际 {hq.index.names}")
        ok = False
    if hq.index.duplicated().any():
        n_dup = int(hq.index.duplicated().sum())
        print(f"FAIL: 重复索引 {n_dup} 行")
        ok = False

    missing = [c for c in HQ_COLUMNS if c not in hq.columns]
    extra = [c for c in hq.columns if c not in HQ_COLUMNS]
    if missing:
        print(f"FAIL: 缺列 {missing}")
        ok = False
    if extra:
        print(f"WARN: 多余列 {extra}")

    dt = hq.index.get_level_values("datetime")
    inst = hq.index.get_level_values("instrument")
    print(f"dates: {pd_min_max(dt)}  n_days={dt.nunique()}")
    print(f"instruments: n={inst.nunique()}  sample={sorted(inst.unique()[:5].tolist())}")

    key_cols = ["open", "high", "low", "close", "adjfactor", "volume", "amount", "float_cap", "pe_ttm", "pb"]
    print("null_rate:")
    for col in key_cols:
        if col not in hq.columns:
            continue
        rate = float(hq[col].isna().mean())
        flag = "WARN" if rate > 0.3 else "ok"
        print(f"  {col}: {rate:.2%} [{flag}]")

    # 抽样一天行数（全市场约 3000~5000）
    one_day = dt.min()
    n_one = int((dt == one_day).sum())
    print(f"rows_on_first_day ({one_day.date()}): {n_one}")
    if n_one < 100:
        print("WARN: 单日股票数过少，可能不是全市场按日结果")

    if args.build_smoke:
        from alphaagent.data.panel import build_panel_from_hq

        smoke_out = path.parent.parent / "panel" / "_smoke_panel_1d.parquet"
        print(f"build_smoke → {smoke_out}")
        panel = build_panel_from_hq(hq, universe_mask=False)
        smoke_out.parent.mkdir(parents=True, exist_ok=True)
        panel.to_parquet(smoke_out)
        label_cols = [c for c in panel.columns if c.startswith("label_")]
        print(f"panel shape={panel.shape} labels={label_cols}")
        if "adj_close" not in panel.columns or "label_1d_close_to_close" not in panel.columns:
            print("FAIL: panel 缺少 adj_close / label")
            ok = False
        else:
            print("build_smoke: OK")

    if ok:
        print("RESULT: OK — 可用（价量+daily_basic 建 panel）")
        return 0
    print("RESULT: FAIL — 见上方错误")
    return 1


def pd_min_max(dt) -> str:
    return f"{dt.min().date()} ~ {dt.max().date()}"


if __name__ == "__main__":
    raise SystemExit(main())
