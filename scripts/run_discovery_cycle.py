#!/usr/bin/env python3
"""一键完成因子挖掘、闸门、VNpy 导出、SmartX 对齐训练回测和结论报告。"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "artifacts/factorzoo/stock_1d/mining_delivered_registry.json"
PANEL = ROOT / "artifacts/panel/panel_1d.parquet"
FACTORLIB = ROOT / "artifacts/factorzoo/stock_1d"
MARKET_HQ = ROOT / "artifacts/market/daily_hq.parquet"


def _parse_args() -> argparse.Namespace:
    # 服务器生产路径优先；本机可回退到兄弟目录
    candidates = [
        Path("/mnt/recom/develop/wangchanghao/rtp_fg/em_ak/em_ak/examples/alpha_research"),
        ROOT.parent / "em_ak/em_ak/examples/alpha_research",
        ROOT.parent / "vnpy/examples/alpha_research",
    ]
    default_vnpy = next(
        (p for p in candidates if (p / "smallcap_live/config.py").is_file()),
        candidates[0],
    )
    p = argparse.ArgumentParser(description="AlphaAgent 一键因子挖掘与线上口径验收")
    p.add_argument("--panel", type=Path, default=PANEL)
    p.add_argument("--registry", type=Path, default=REGISTRY)
    p.add_argument(
        "--vnpy-root",
        type=Path,
        default=Path(os.environ.get("VNPY_ALPHA_RESEARCH", default_vnpy)),
        help="alpha_research 根目录（默认优先 em_ak 生产路径）",
    )
    p.add_argument("--alpha-python", default=os.environ.get("ALPHAAGENT_PYTHON", sys.executable))
    p.add_argument("--vnpy-python", default=os.environ.get("VNPY_PYTHON", sys.executable))
    p.add_argument("--lanes", default="momentum,volatility,volume,weekly,crosssectional")
    p.add_argument("--max-turns", type=int, default=8)
    p.add_argument("--capital", type=float, default=200_000)
    p.add_argument(
        "--no-auto-prepare-data",
        action="store_true",
        help="Panel 缺失时不从 VNpy 归档自动转换和构建",
    )
    p.add_argument("--skip-mining", action="store_true")
    p.add_argument(
        "--factor-ids",
        default=None,
        help="配合 --skip-mining：真实 factor_id 逗号分隔（不要填 id1,id2 占位符）",
    )
    p.add_argument("--dry-run", action="store_true", help="只检查并打印执行计划")
    p.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    p.add_argument(
        "positional",
        nargs="*",
        help="可省略开关名：第一个是 vnpy-root，第二个是 vnpy-python",
    )
    args = p.parse_args()
    extra = list(args.positional or [])
    if len(extra) > 2:
        p.error("位置参数最多两个：<vnpy-root> <vnpy-python>")
    if extra:
        args.vnpy_root = Path(extra[0])
    if len(extra) == 2:
        args.vnpy_python = extra[1]
    return args


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _load_dotenv() -> None:
    """加载仓库根 .env，不覆盖已有环境变量。"""
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None  # type: ignore[assignment]
    if load_dotenv is not None:
        load_dotenv(env_path, override=False)
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _ensure_llm_key(*, skip_mining: bool) -> None:
    if skip_mining:
        return
    if not os.environ.get("OPENAI_API_KEY"):
        for alt in ("AX_LLM_API_KEY", "LITELLM_API_KEY"):
            if os.environ.get(alt):
                os.environ["OPENAI_API_KEY"] = os.environ[alt]
                print(f"[preflight] 使用 {alt} 作为 OPENAI_API_KEY")
                break
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit(
            "缺少 LLM Key。\n"
            "你的 .env 里如果是 LITELLM_API_KEY，旧脚本不会自动加载；请先同步最新脚本，或执行：\n"
            "  set -a; source .env; set +a\n"
            "  export OPENAI_API_KEY=\"$LITELLM_API_KEY\""
        )
    os.environ.setdefault(
        "OPENAI_API_BASE",
        os.environ.get("AX_LLM_BASE_URL", "https://litellm.spaccez.com/v1"),
    )
    os.environ.setdefault("MODEL", os.environ.get("AX_LLM_MODEL", "deepseek-v4-flash"))
    key = os.environ["OPENAI_API_KEY"]
    print(f"[preflight] LLM MODEL={os.environ.get('MODEL')} KEY=***{key[-4:]}")


def _run(command: list[str], *, cwd: Path = ROOT, log: Path | None = None) -> None:
    print(f"\n$ {shlex.join(command)}", flush=True)
    if log is None:
        subprocess.run(command, cwd=cwd, check=True)
        return
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as fh:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            fh.write(line)
        if process.wait() != 0:
            raise subprocess.CalledProcessError(process.returncode, command)


def _changed_ids(before: dict, after: dict) -> list[str]:
    return sorted(k for k, value in after.items() if k not in before or before[k] != value)


def _ensure_panel_contract(panel: Path, *, mutate: bool) -> tuple[str, str]:
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    if not panel.is_file():
        raise SystemExit(f"Panel 不存在: {panel}")
    parquet = pq.ParquetFile(panel)
    if "datetime" not in parquet.schema_arrow.names:
        raise SystemExit("Panel parquet 缺少 datetime 索引列")
    dates = pq.read_table(panel, columns=["datetime"])["datetime"]
    min_raw, max_raw = pc.min(dates).as_py(), pc.max(dates).as_py()
    date_min = (min_raw.date() if hasattr(min_raw, "date") else min_raw).isoformat()
    date_max = (max_raw.date() if hasattr(max_raw, "date") else max_raw).isoformat()
    if date_min > "2010-01-31" or date_max < "2026-01-01":
        raise SystemExit(
            f"Panel 覆盖 {date_min}~{date_max}，不足以执行 2010~2023 训练和 2024~2026 测试"
        )
    if not mutate and "label_5d_close_to_close" not in parquet.schema_arrow.names:
        print("提示：正式运行会自动补算 label_5d_close_to_close")
    return date_min, date_max


def _prepare_panel(args: argparse.Namespace) -> None:
    if args.panel.is_file():
        return
    if args.no_auto_prepare_data:
        raise SystemExit(f"Panel 不存在且已关闭自动数据准备: {args.panel}")
    daily_dir = args.vnpy_root / "lab/allstock/daily"
    if not daily_dir.is_dir():
        raise SystemExit(f"Panel 不存在，且 VNpy 日线归档也不存在: {daily_dir}")
    print("[data] Panel 缺失：从 VNpy 归档构建 2010 至今行情与 Panel")
    MARKET_HQ.parent.mkdir(parents=True, exist_ok=True)
    args.panel.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            args.alpha_python,
            "scripts/convert_vnpy_to_hq.py",
            "--vnpy-root",
            str(args.vnpy_root),
            "--start",
            "2010-01-01",
            "--end",
            datetime.now().date().isoformat(),
            "--out",
            str(MARKET_HQ),
        ]
    )
    _run(
        [
            args.alpha_python,
            "scripts/build_panel.py",
            "--market-cache",
            str(MARKET_HQ),
            "--out",
            str(args.panel),
        ]
    )


def _ensure_label_5d(panel: Path, python: str) -> None:
    import pyarrow.parquet as pq

    if "label_5d_close_to_close" in pq.ParquetFile(panel).schema_arrow.names:
        return
    print("[preflight] 补算 SmartX T+5 label（一次性 panel schema 升级）")
    code = (
        "from pathlib import Path;"
        "from alphaagent.data.panel import load_panel,save_panel,backfill_panel_derived_columns;"
        f"p=Path({str(panel)!r});d=backfill_panel_derived_columns(load_panel(p));"
        "save_panel(d,p);print('label_5d_close_to_close added')"
    )
    _run([python, "-c", code])


def _ensure_factorlib(panel: Path, python: str) -> None:
    if not (FACTORLIB / "manifest.json").is_file():
        _run([python, "scripts/init_factorlib.py", "--panel", str(panel)])
    expressions = FACTORLIB / "expressions"
    if any(expressions.glob("*.dsl")) and not (FACTORLIB / "meta/factors.parquet").is_file():
        _run(
            [
                python,
                "scripts/ingest_factors.py",
                "--expr-dir",
                str(expressions),
                "--overwrite",
                "--label-col",
                "label_5d_close_to_close",
                "--train-start",
                "2010-01-01",
                "--eval-end",
                "2023-12-31",
            ]
        )


def _markdown_report(combined: dict) -> str:
    bt = combined.get("backtest") or {}
    lines = [
        f"# 因子挖掘轮次 {combined['run_id']}",
        "",
        f"- 本轮候选：{len(combined.get('candidate_factor_ids', []))}",
        f"- 项目闸门通过：{len(combined.get('passed_factor_ids', []))}",
        "- 选择期：2010–2023；2024/2025/2026 未参与挖掘或闸门",
        "- 模型：Alpha158 T+5，BASE 与 MINING 同数据同参数重训",
        "- 回测：CSI300 PIT / S30-daily / 线上择时 / 20万真实费率",
        "",
    ]
    if not bt:
        lines += ["## 结论", "", "本轮没有通过项目闸门的新增因子，未进入模型回测。", ""]
        return "\n".join(lines)
    delta = bt.get("delta") or {}
    lines += [
        "## BASE vs MINING",
        "",
        f"- 全期 ΔReturn：{float(delta.get('return_pct', 0)):+.2f}pp",
        f"- 全期 ΔSharpe：{float(delta.get('sharpe', 0)):+.3f}",
    ]
    for year, row in (bt.get("yearly") or {}).items():
        lines.append(
            f"- {year}：ΔReturn {float(row.get('delta_return_pct', 0)):+.2f}pp，"
            f"ΔSharpe {float(row.get('delta_sharpe', 0)):+.3f}"
        )
    lines += [
        "",
        "## 结论",
        "",
        (
            "本轮挖掘因子在预先固定的稳定增益规则下通过，可进入影子观察。"
            if bt.get("effective")
            else "本轮未证明存在稳定增益，不应接入线上。"
        ),
        "",
        f"判定规则：{bt.get('decision_rule', '')}",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    _load_dotenv()
    args = _parse_args()
    run_dir = ROOT / "artifacts/mining_runs" / args.run_id
    eval_json = run_dir / "gate_eval.json"
    factor_table = run_dir / "mining_factors.parquet"
    backtest_json = run_dir / "smartx_compare.json"

    if args.skip_mining and not args.factor_ids:
        raise SystemExit("--skip-mining 时必须指定 --factor-ids，避免误把历史因子当作本轮产物")
    if args.skip_mining and args.factor_ids:
        requested = [x.strip() for x in args.factor_ids.split(",") if x.strip()]
        if set(requested) <= {"id1", "id2", "id3"}:
            raise SystemExit(
                "--factor-ids 不能用文档占位符 id1,id2。\n"
                "先在服务器执行：\n"
                "  python -c \"import json;from pathlib import Path;"
                "r=json.loads(Path('artifacts/factorzoo/stock_1d/mining_delivered_registry.json').read_text());"
                "[print(k) for k in sorted(r)]\"\n"
                "再把真实 factor_id 填进 --factor-ids"
            )
        registry = _load_json(args.registry)
        missing = [x for x in requested if x not in registry]
        if missing:
            available = "\n".join(f"  {k}" for k in sorted(registry))
            raise SystemExit(
                f"--factor-ids 在 registry 中不存在: {missing}\n可用 factor_id:\n{available}"
            )
    if not (args.vnpy_root / "smallcap_live/config.py").is_file():
        raise SystemExit(f"找不到 VNpy alpha_research: {args.vnpy_root}")

    print("固定实验协议：")
    print("  因子探索 train=2010~2020, val=2021~2022, holdout gate=2023")
    print("  模型 train=2010~2023, test=2024/2025/2026")
    print("  label=T+5；测试年份绝不参与因子选择")
    if args.dry_run:
        _ensure_llm_key(skip_mining=args.skip_mining)
        if args.panel.is_file():
            _ensure_panel_contract(args.panel, mutate=False)
        elif args.no_auto_prepare_data:
            raise SystemExit(f"Panel 不存在且已关闭自动数据准备: {args.panel}")
        elif not (args.vnpy_root / "lab/allstock/daily").is_dir():
            raise SystemExit("Panel 与 VNpy 日线归档均不存在，无法自动准备数据")
        else:
            print("提示：正式运行会从 VNpy 归档自动构建 2010 至今 Panel")
        print("dry-run 完成：数据来源、VNpy 路径和执行协议检查通过")
        return 0

    _ensure_llm_key(skip_mining=args.skip_mining)
    run_dir.mkdir(parents=True, exist_ok=True)
    _prepare_panel(args)
    panel_range = _ensure_panel_contract(args.panel, mutate=True)
    _ensure_label_5d(args.panel, args.alpha_python)
    _ensure_factorlib(args.panel, args.alpha_python)

    if args.skip_mining:
        candidates = [x.strip() for x in args.factor_ids.split(",") if x.strip()]
    else:
        before = _load_json(args.registry)
        _run(
            [
                "bash",
                "scripts/run_factor_mining_parallel.sh",
                "--panel",
                str(args.panel),
                "--lanes",
                args.lanes,
                "--max-turns",
                str(args.max_turns),
                "--label-col",
                "label_5d_close_to_close",
                "--train-start",
                "2010-01-01",
                "--train-end",
                "2020-12-31",
                "--val-start",
                "2021-01-01",
                "--val-end",
                "2022-12-31",
                "--holdout-start",
                "2023-01-01",
                "--holdout-end",
                "2023-12-31",
            ],
            log=run_dir / "mining.log",
        )
        candidates = _changed_ids(before, _load_json(args.registry))

    if candidates:
        _run(
            [
                args.alpha_python,
                "scripts/eval_mining_batch.py",
                "--registry",
                str(args.registry),
                "--panel",
                str(args.panel),
                "--source-filter",
                "all",
                "--factor-ids",
                ",".join(candidates),
                "--label-col",
                "label_5d_close_to_close",
                "--train-start",
                "2010-01-01",
                "--train-end",
                "2020-12-31",
                "--val-start",
                "2021-01-01",
                "--val-end",
                "2022-12-31",
                "--holdout-start",
                "2023-01-01",
                "--holdout-end",
                "2023-12-31",
                "--json-out",
                str(eval_json),
            ],
            log=run_dir / "gate.log",
        )
        gate = _load_json(eval_json)
        passed = [r["factor_id"] for r in gate.get("rows", []) if r.get("ho_pass")]
    else:
        gate, passed = {"rows": [], "errors": []}, []

    backtest: dict = {}
    if passed:
        _run(
            [
                args.alpha_python,
                "scripts/export_factors_to_vnpy.py",
                "--registry",
                str(args.registry),
                "--panel",
                str(args.panel),
                "--label-col",
                "label_5d_close_to_close",
                "--factor-ids",
                ",".join(passed),
                "--out",
                str(factor_table),
                "--no-merge",
                "--keep-all-rows",
            ],
            log=run_dir / "export.log",
        )
        _run(
            [
                args.vnpy_python,
                str(ROOT / "scripts/vnpy_smartx_compare.py"),
                "--vnpy-root",
                str(args.vnpy_root),
                "--factor-table",
                str(factor_table),
                "--report-json",
                str(backtest_json),
                "--capital",
                str(args.capital),
                "--run-id",
                args.run_id,
            ],
            cwd=args.vnpy_root,
            log=run_dir / "backtest.log",
        )
        backtest = _load_json(backtest_json)

    combined = {
        "run_id": args.run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "panel": {"path": str(args.panel), "range": panel_range},
        "candidate_factor_ids": candidates,
        "passed_factor_ids": passed,
        "gate": gate,
        "backtest": backtest,
        "effective": bool(backtest.get("effective", False)),
    }
    (run_dir / "result.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = _markdown_report(combined)
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"\n完整产物: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
