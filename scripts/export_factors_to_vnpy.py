#!/usr/bin/env python3
"""把 AlphaAgent 挖掘的因子导出为 vnpy 可注入的特征长表。

输出：parquet，列 = datetime, vt_symbol, <factor_id>...，每行一个 (datetime, vt_symbol)。
vt_symbol 采用 vnpy 格式（Tushare ts_code 映射：.SZ→.SZSE / .SH→.SSE / .BJ→.BSE）。

在 vnpy 侧用 ``inject_mining_factors`` 把这张表左连进 Alpha158 的 raw_df/infer_df/learn_df，
因子列即自动成为 LightGBM 特征（fetch_infer 只剔 datetime/vt_symbol/label 之外全当特征）。

用法（AlphaAgent 环境，服务器上）：
  uv run python scripts/export_factors_to_vnpy.py \
      --registry artifacts/factorzoo/stock_1d/mining_delivered_registry.json \
      --out /mnt/recom/develop/wangchanghao/rtp_fg/em_ak/em_ak/examples/alpha_research/lab/factor_tables/mining_factors.parquet

  # 只导出指定因子（用 holdout 通过的那几个）
  uv run python scripts/export_factors_to_vnpy.py \
      --factor-ids wk_mom5_ma12_dev,mom_resi60_wk_ma13 --out .../mining_factors.parquet
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alphaagent.core.paths import PANEL_PATH  # noqa: E402
from alphaagent.data.panel import load_panel  # noqa: E402
from alphaagent.factor.eval import _eval_values  # noqa: E402
from alphaagent.factor.mining.registry_io import load_mining_registry  # noqa: E402
from alphaagent.factor.types import DEFAULT_LABEL_COL  # noqa: E402

# Tushare ts_code → vnpy vt_symbol 交易所后缀
_EXCHANGE_MAP = {"SH": "SSE", "SZ": "SZSE", "BJ": "BSE"}


def to_vt_symbol(inst: str) -> str:
    """把 AlphaAgent panel 的 instrument（Tushare ts_code）映射为 vnpy vt_symbol。

    兼容两种输入：带交易所后缀（"000001.SZ"）或纯 6 位代码（"000001"，按前缀推断）。
    """
    inst = str(inst).strip()
    if "." in inst:
        code, ex = inst.rsplit(".", 1)
        return f"{code}.{_EXCHANGE_MAP.get(ex.upper(), ex.upper())}"
    # 纯数字代码：6 开头/688/689 → 沪，其余多深（含 8 开头北交按 深处理，可后续校正）
    code = inst.zfill(6)
    if code[0] in ("6", "9") or code.startswith("688") or code.startswith("689"):
        return f"{code}.SSE"
    return f"{code}.SZSE"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="导出 AlphaAgent 因子为 vnpy 特征长表")
    p.add_argument("--registry", type=Path,
                   default=ROOT / "artifacts/factorzoo/stock_1d/mining_delivered_registry.json")
    p.add_argument("--panel", type=Path, default=PANEL_PATH)
    p.add_argument("--label-col", default=DEFAULT_LABEL_COL)
    p.add_argument("--factor-ids", default=None,
                   help="逗号分隔的 factor_id；默认导出 registry 里全部 source=submit 的因子")
    p.add_argument("--out", type=Path, required=True, help="输出 parquet 路径")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    registry = load_mining_registry(args.registry)
    if not registry:
        print("错误：registry 为空", file=sys.stderr)
        return 1

    if args.factor_ids:
        ids = [s.strip() for s in args.factor_ids.split(",") if s.strip()]
        missing = [i for i in ids if i not in registry]
        if missing:
            print(f"错误：registry 不存在因子 {missing}", file=sys.stderr)
            return 1
    else:
        ids = [k for k, v in registry.items() if v.get("source") == "submit"]
        if not ids:
            ids = list(registry.keys())
    ids = [i for i in ids if registry[i].get("expression_file")]
    if not ids:
        print("没有可导出的因子（缺 expression_file）", file=sys.stderr)
        return 1
    print(f"导出 {len(ids)} 个因子: {ids}")

    print("加载 panel...", end=" ", flush=True)
    t0 = time.perf_counter()
    panel = load_panel(args.panel).sort_index()
    print(f"shape={panel.shape} ({time.perf_counter()-t0:.1f}s)")

    # 逐因子求值 DSL，对齐到 panel 索引，纵向拼接成 (datetime,instrument) x 因子列
    t1 = time.perf_counter()
    series_list: list[pd.Series] = []
    for i, fid in enumerate(ids, 1):
        expr_file = registry[fid]["expression_file"]
        dsl_path = expr_file if Path(expr_file).is_absolute() else ROOT / expr_file
        expr = dsl_path.read_text(encoding="utf-8").strip()
        values = _eval_values(expr, panel, label_col=args.label_col)
        series_list.append(pd.Series(values, index=panel.index, name=fid))
        print(f"  [{i}/{len(ids)}] {fid} ({time.perf_counter()-t1:.1f}s)", flush=True)

    factor_df = pd.concat(series_list, axis=1)
    out = factor_df.reset_index()[["datetime", "instrument", *ids]]
    out["vt_symbol"] = out["instrument"].map(to_vt_symbol)
    out = out[["datetime", "vt_symbol", *ids]]
    out = out.dropna(how="all", subset=ids)  # 去掉全因子 NaN 的行（无数据的时间/票）

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    print(f"\n已导出 {len(out):,} 行 → {args.out} ({time.perf_counter()-t1:.1f}s)")
    print(f"列: {list(out.columns)}")
    print(f"vt_symbol 示例: {out['vt_symbol'].drop_duplicates().head(5).tolist()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())