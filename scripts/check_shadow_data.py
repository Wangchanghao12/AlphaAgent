#!/usr/bin/env python3
"""检查影子训练所需数据是否覆盖到指定截止日。

检查项：
  1) AlphaAgent panel
  2) vnpy 日线最新 bar（bars_probe_latest）
  3) 可选：某 run 的因子 parquet / Alpha158 缓存

用法:
  python scripts/check_shadow_data.py --data-end 2026-09-01 \\
    --vnpy-root /mnt/recom/develop/wangchanghao/rtp_fg/em_ak/em_ak/examples/alpha_research

  python scripts/check_shadow_data.py --data-end 2026-09-01 \\
    --run-id 20260910_184033 --check-alpha158-cache
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PANEL = ROOT / "artifacts/panel/panel_1d.parquet"
RUNS_DIR = ROOT / "artifacts/mining_runs"


def _parse_args() -> argparse.Namespace:
    candidates = [
        Path("/mnt/recom/develop/wangchanghao/rtp_fg/em_ak/em_ak/examples/alpha_research"),
        ROOT.parent / "em_ak/em_ak/examples/alpha_research",
    ]
    default_vnpy = next(
        (p for p in candidates if (p / "smallcap_live/config.py").is_file()),
        candidates[0],
    )
    p = argparse.ArgumentParser(description="检查影子训练数据覆盖")
    p.add_argument("--data-end", default="2026-09-01")
    p.add_argument("--train-start", default="2010-01-04")
    p.add_argument("--panel", type=Path, default=PANEL)
    p.add_argument("--vnpy-root", type=Path, default=Path(os.environ.get("VNPY_ALPHA_RESEARCH", default_vnpy)))
    p.add_argument("--run-id", default=None, help="检查该轮的 shadow 因子表（若已 export）")
    p.add_argument("--check-alpha158-cache", action="store_true")
    p.add_argument("--cache-name", default="alpha158_t2_cache")
    return p.parse_args()


def _status(ok: bool) -> str:
    return "OK" if ok else "FAIL"


def _check_panel(panel: Path, need_end: datetime.date, need_start: datetime.date) -> tuple[bool, str, str]:
    if not panel.is_file():
        return False, "missing", f"panel 不存在: {panel}"
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(panel)
    schema_names = pf.schema_arrow.names
    if "datetime" in schema_names:
        import pyarrow.compute as pc

        table = pf.read(columns=["datetime"])
        col = table.column("datetime")
        lo = pc.min(col).as_py()
        hi = pc.max(col).as_py()
    else:
        # MultiIndex 存 parquet 时可能是 index level 列
        lo = hi = None
        for name in ("datetime", "level_0"):
            if name in schema_names:
                import pyarrow.compute as pc

                col = pf.read(columns=[name]).column(name)
                lo = pc.min(col).as_py()
                hi = pc.max(col).as_py()
                break
    if lo is None or hi is None:
        return False, "unknown", "无法读取 panel 日期列"

    lo_d = lo.date() if hasattr(lo, "date") else datetime.strptime(str(lo)[:10], "%Y-%m-%d").date()
    hi_d = hi.date() if hasattr(hi, "date") else datetime.strptime(str(hi)[:10], "%Y-%m-%d").date()
    ok = lo_d <= need_start and hi_d >= need_end
    detail = f"{lo_d} ~ {hi_d}（需要 {need_start} ~ {need_end}）"
    return ok, _status(ok), detail


def _check_vnpy_bars(vnpy_root: Path, need_end: datetime.date) -> tuple[bool, str, str]:
    if not (vnpy_root / "smallcap_live/config.py").is_file():
        return False, "missing", f"无效 vnpy-root: {vnpy_root}"
    os.chdir(vnpy_root)
    sys.path.insert(0, str(vnpy_root))
    sys.path.insert(0, str(vnpy_root.parent.parent))
    from buyable import EXCLUDED_PREFIXES
    from multihorizon_neutral.research_workflow_multihorizon_neutral import LAB_PATH, TURNOVER_THRESHOLD, filter_liquid
    from multihorizon_neutral.research_workflow_multihorizon_neutral_v2 import get_csi300_symbols_v2
    from multihorizon_neutral.research_workflow_multihorizon_neutral import CSI300_LAB_PATH
    from smallcap_live.daily_signal_smallcap import bars_probe_latest
    from vnpy.alpha import AlphaLab

    lab = AlphaLab(LAB_PATH)
    csi300_lab = AlphaLab(CSI300_LAB_PATH)
    liquid = filter_liquid(lab, "2024-01-01", threshold=TURNOVER_THRESHOLD)
    hist, current = get_csi300_symbols_v2(csi300_lab)
    available = {
        f.stem
        for f in lab.daily_path.glob("*.parquet")
        if not f.stem.startswith("._") and "." in f.stem
    }
    symbols = sorted((set(liquid) | set(hist) | set(current)) & available)
    symbols = [s for s in symbols if s[:3] not in EXCLUDED_PREFIXES]
    latest, detail = bars_probe_latest(lab, symbols[:20])
    if latest is None:
        return False, "FAIL", f"bars_probe_latest 失败: {detail}"
    latest_d = latest.date() if hasattr(latest, "date") else datetime.strptime(str(latest)[:10], "%Y-%m-%d").date()
    ok = latest_d >= need_end
    return ok, _status(ok), f"vnpy 日线最新 {latest_d}（需要 >= {need_end}）"


def _check_parquet_dates(path: Path, need_end: datetime.date, need_start: datetime.date) -> tuple[bool, str, str]:
    if not path.is_file():
        return False, "missing", f"文件不存在: {path}"
    import polars as pl

    row = (
        pl.scan_parquet(path)
        .select(pl.col("datetime").min().alias("lo"), pl.col("datetime").max().alias("hi"))
        .collect()
        .row(0, named=True)
    )
    lo = row["lo"]
    hi = row["hi"]
    lo_d = lo.date() if hasattr(lo, "date") else datetime.strptime(str(lo)[:10], "%Y-%m-%d").date()
    hi_d = hi.date() if hasattr(hi, "date") else datetime.strptime(str(hi)[:10], "%Y-%m-%d").date()
    ok = lo_d <= need_start and hi_d >= need_end
    return ok, _status(ok), f"{lo_d} ~ {hi_d}（需要 {need_start} ~ {need_end}）"


def main() -> int:
    args = _parse_args()
    need_end = datetime.strptime(args.data_end, "%Y-%m-%d").date()
    need_start = datetime.strptime(args.train_start, "%Y-%m-%d").date()
    compact = args.data_end.replace("-", "")

    print(f"目标数据截止: {args.data_end}  train_start={args.train_start}\n")

    all_ok = True
    ok, st, detail = _check_panel(args.panel, need_end, need_start)
    print(f"[panel]           {st:7s}  {detail}")
    all_ok &= ok

    ok, st, detail = _check_vnpy_bars(args.vnpy_root, need_end)
    print(f"[vnpy 日线]       {st:7s}  {detail}")
    all_ok &= ok

    if args.run_id:
        factor_path = RUNS_DIR / args.run_id / f"mining_factors_shadow_{compact}.parquet"
        if not factor_path.is_file():
            factor_path = RUNS_DIR / args.run_id / "mining_factors.parquet"
        ok, st, detail = _check_parquet_dates(factor_path, need_end, need_start)
        print(f"[因子表 {args.run_id}] {st:7s}  {detail}")
        if st == "missing":
            print("                   提示: 尚未 export；train_shadow 会先导出")
        all_ok &= ok or st == "missing"

    if args.check_alpha158_cache:
        os.chdir(args.vnpy_root)
        sys.path.insert(0, str(args.vnpy_root))
        from multihorizon_neutral.research_workflow_multihorizon_neutral import LAB_PATH
        from vnpy.alpha import AlphaLab
        import polars as pl

        cache = AlphaLab(LAB_PATH).dataset_path / f"{args.cache_name}.parquet"
        ok, st, detail = _check_parquet_dates(cache, need_end, need_start)
        print(f"[Alpha158 缓存]   {st:7s}  {cache}")
        print(f"                   {detail}")
        if not ok and cache.is_file():
            print("                   提示: 训练时加 --recompute-alpha158 或先重算缓存")
        all_ok &= ok

    print()
    if all_ok:
        print("结论: 数据覆盖满足影子训练要求。")
        return 0
    print("结论: 数据不足。请先 update_panel / 更新 vnpy 归档 / 重算 Alpha158 缓存后再训。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
