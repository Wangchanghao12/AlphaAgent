#!/usr/bin/env python3
"""训练两包 SmartX 通过因子的影子 MINING 模型（数据训到指定截止日）。

模型名格式：shadow_mining__{train_start}_{data_end}__{run_id}
例：shadow_mining__20100104_20260901__20260910_184033

用法（服务器）:
  set -a; source .env; set +a
  python scripts/train_shadow_mining_models.py \\
    --vnpy-root /mnt/recom/develop/wangchanghao/rtp_fg/em_ak/em_ak/examples/alpha_research \\
    --alpha-python /root/miniconda3/envs/vn311py/bin/python \\
    --vnpy-python /root/miniconda3/envs/vn311py/bin/python \\
    --data-end 2026-09-01
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "artifacts/mining_runs"
REGISTRY = ROOT / "artifacts/factorzoo/stock_1d/mining_delivered_registry.json"
PANEL = ROOT / "artifacts/panel/panel_1d.parquet"

# 已知 SmartX effective 轮次（也可用 --runs 覆盖）
DEFAULT_RUNS = ("20260910_184033", "20260918_020822")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="训练影子 MINING 模型（两包 effective）")
    p.add_argument("--vnpy-root", type=Path, required=True)
    p.add_argument("--alpha-python", default=os.environ.get("ALPHAAGENT_PYTHON", sys.executable))
    p.add_argument("--vnpy-python", default=os.environ.get("VNPY_PYTHON", sys.executable))
    p.add_argument("--panel", type=Path, default=PANEL)
    p.add_argument("--registry", type=Path, default=REGISTRY)
    p.add_argument("--runs", default=",".join(DEFAULT_RUNS), help="effective run_id，逗号分隔")
    p.add_argument("--train-start", default="2010-01-04")
    p.add_argument(
        "--train-end",
        default="2026-06-30",
        help="LGB 训练段截止（valid 为 train_end+1 ~ valid_end）",
    )
    p.add_argument("--valid-end", default=None, help="默认等于 --data-end")
    p.add_argument("--data-end", default="2026-09-01", help="因子与 Alpha158 数据截止日")
    p.add_argument(
        "--cache-name",
        default="alpha158_t2_cache",
        help="Alpha158 缓存名；若覆盖不足请加 --recompute-alpha158",
    )
    p.add_argument("--recompute-alpha158", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _compact_date(s: str) -> str:
    return s.replace("-", "")


def _model_name(train_start: str, data_end: str, run_id: str) -> str:
    return f"shadow_mining__{_compact_date(train_start)}_{_compact_date(data_end)}__{run_id}"


def _run(cmd: list[str], *, cwd: Path = ROOT) -> None:
    print(f"\n$ {shlex.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def _factor_ids(run_id: str) -> list[str]:
    result = _load_json(RUNS_DIR / run_id / "result.json")
    passed = result.get("passed_factor_ids") or []
    if passed:
        return list(passed)
    gate = _load_json(RUNS_DIR / run_id / "gate_eval.json")
    passed = [r["factor_id"] for r in gate.get("rows", []) if r.get("ho_pass")]
    if passed:
        return passed
    raise SystemExit(f"{run_id}: 找不到 passed_factor_ids（需 result.json 或 gate_eval.json）")


def main() -> int:
    args = _parse_args()
    valid_end = args.valid_end or args.data_end
    run_ids = [x.strip() for x in args.runs.split(",") if x.strip()]
    if not run_ids:
        raise SystemExit("--runs 为空")

    print("影子 MINING 训练协议")
    print(f"  train : {args.train_start} ~ {args.train_end}")
    print(f"  valid : ~ {valid_end}")
    print(f"  data  : ~ {args.data_end}")
    print(f"  runs  : {', '.join(run_ids)}")

    summaries: list[dict[str, Any]] = []
    for run_id in run_ids:
        factor_ids = _factor_ids(run_id)
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        factor_table = run_dir / f"mining_factors_shadow_{_compact_date(args.data_end)}.parquet"
        report_json = run_dir / f"shadow_train_{_compact_date(args.data_end)}.json"
        model_name = _model_name(args.train_start, args.data_end, run_id)

        export_cmd = [
            args.alpha_python,
            str(ROOT / "scripts/export_factors_to_vnpy.py"),
            "--registry",
            str(args.registry),
            "--panel",
            str(args.panel),
            "--label-col",
            "label_5d_close_to_close",
            "--factor-ids",
            ",".join(factor_ids),
            "--out",
            str(factor_table),
            "--no-merge",
            "--keep-all-rows",
        ]
        train_cmd = [
            args.vnpy_python,
            str(ROOT / "scripts/vnpy_smartx_compare.py"),
            "--vnpy-root",
            str(args.vnpy_root),
            "--factor-table",
            str(factor_table),
            "--report-json",
            str(report_json),
            "--run-id",
            run_id,
            "--train-start",
            args.train_start,
            "--train-end",
            args.train_end,
            "--valid-end",
            valid_end,
            "--data-end",
            args.data_end,
            "--train-only",
            "--mining-only",
            "--mining-model-name",
            model_name,
            "--cache-name",
            args.cache_name,
        ]
        if args.recompute_alpha158:
            train_cmd.append("--recompute-alpha158")

        print(f"\n=== {run_id} | {len(factor_ids)} 因子 -> {model_name} ===")
        if args.dry_run:
            print(f"  export: {shlex.join(export_cmd)}")
            print(f"  train : {shlex.join(train_cmd)}")
            summaries.append(
                {
                    "run_id": run_id,
                    "model_name": model_name,
                    "factor_ids": factor_ids,
                    "factor_table": str(factor_table),
                }
            )
            continue

        _run(export_cmd)
        _run(train_cmd, cwd=ROOT)

        report = _load_json(report_json)
        summaries.append(
            {
                "run_id": run_id,
                "model_name": model_name,
                "factor_ids": factor_ids,
                "factor_table": str(factor_table),
                "report": str(report_json),
                "vnpy_model": report.get("models", {}).get("mining", model_name),
            }
        )

    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "train_start": args.train_start,
        "train_end": args.train_end,
        "valid_end": valid_end,
        "data_end": args.data_end,
        "bundles": summaries,
    }
    manifest_path = RUNS_DIR / f"shadow_models_{_compact_date(args.data_end)}.json"
    if not args.dry_run:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n完成。影子 MINING 模型：")
    for item in summaries:
        print(f"  {item['model_name']}")
        print(f"    run_id={item['run_id']}  factors={len(item['factor_ids'])}")
    if not args.dry_run:
        print(f"\n清单: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
