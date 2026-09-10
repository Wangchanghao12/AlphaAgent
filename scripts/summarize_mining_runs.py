#!/usr/bin/env python3
"""汇总 discovery cycle 历史轮次，便于判断该继续堆轮次还是调整挖掘策略。

扫描 artifacts/mining_runs/<run_id>/，优先读 result.json；缺失时尝试从
gate_eval.json + smartx_compare.json 拼装。

用法:
  uv run python scripts/summarize_mining_runs.py
  uv run python scripts/summarize_mining_runs.py --last 10
  uv run python scripts/summarize_mining_runs.py --json-out artifacts/mining_runs/summary.json
  uv run python scripts/summarize_mining_runs.py --csv-out artifacts/mining_runs/summary.csv
  uv run python scripts/summarize_mining_runs.py --update-discovery-user
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS_DIR = ROOT / "artifacts" / "mining_runs"
DISCOVERY_USER_FILE = ROOT / "configs/mining_user_discovery.txt"
DISCOVERY_CONSTRAINTS_FILE = ROOT / "configs/mining_user_discovery_constraints.txt"
AUTO_BEGIN = "# --- AUTO-GENERATED (summarize_mining_runs.py --update-discovery-user) ---"
AUTO_END = "# --- END AUTO-GENERATED ---"
MANUAL_BEGIN = "# --- MANUAL CONSTRAINTS (edit configs/mining_user_discovery_constraints.txt) ---"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="汇总 mining_runs 历史轮次")
    p.add_argument(
        "--runs-dir",
        type=Path,
        default=DEFAULT_RUNS_DIR,
        help="mining_runs 根目录",
    )
    p.add_argument("--last", type=int, default=0, help="只显示最近 N 轮（0=全部）")
    p.add_argument("--effective-only", action="store_true", help="只显示 SmartX effective 轮次")
    p.add_argument("--gate-pass-only", action="store_true", help="只显示 gate 至少通过 1 个因子的轮次")
    p.add_argument("--json-out", type=Path, default=None, help="写出机器可读汇总 JSON")
    p.add_argument("--csv-out", type=Path, default=None, help="写出 CSV 表")
    p.add_argument(
        "--update-discovery-user",
        action="store_true",
        help="根据 mining_runs 重写 configs/mining_user_discovery.txt（供下一轮挖掘 --user-file）",
    )
    p.add_argument(
        "--discovery-user-file",
        type=Path,
        default=DISCOVERY_USER_FILE,
        help="--update-discovery-user 的输出路径",
    )
    return p.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _round_num(value: Any, ndigits: int = 3) -> float | None:
    f = _num(value)
    return None if f is None else round(f, ndigits)


def _parse_run_id_ts(run_id: str) -> datetime | None:
    if len(run_id) >= 15 and run_id[8] == "_":
        try:
            return datetime.strptime(run_id[:15], "%Y%m%d_%H%M%S")
        except ValueError:
            pass
    if len(run_id) >= 8 and run_id[:8].isdigit():
        try:
            return datetime.strptime(run_id[:8], "%Y%m%d")
        except ValueError:
            pass
    return None


def _sort_key(run_dir: Path, payload: dict[str, Any]) -> tuple:
    run_id = str(payload.get("run_id") or run_dir.name)
    generated = payload.get("generated_at")
    if isinstance(generated, str) and generated:
        return (generated, run_id)
    parsed = _parse_run_id_ts(run_id)
    if parsed is not None:
        return (parsed.isoformat(), run_id)
    return (run_id, run_id)


def load_run(run_dir: Path) -> dict[str, Any] | None:
    """读取单轮产物；缺失字段时从 gate / smartx 文件补齐。"""
    combined = _load_json(run_dir / "result.json")
    gate = combined.get("gate") if combined else {}
    backtest = combined.get("backtest") if combined else {}
    if not gate:
        gate = _load_json(run_dir / "gate_eval.json")
    if not backtest:
        backtest = _load_json(run_dir / "smartx_compare.json")

    if not combined and not gate and not backtest:
        return None

    run_id = str(combined.get("run_id") or backtest.get("run_id") or run_dir.name)
    candidates = combined.get("candidate_factor_ids")
    if candidates is None:
        rows = gate.get("rows") or []
        candidates = [r.get("factor_id") for r in rows if r.get("factor_id")]

    passed = combined.get("passed_factor_ids")
    if passed is None:
        passed = [r["factor_id"] for r in (gate.get("rows") or []) if r.get("ho_pass")]

    effective = combined.get("effective")
    if effective is None:
        effective = bool(backtest.get("effective"))

    return {
        "run_id": run_id,
        "generated_at": combined.get("generated_at"),
        "candidate_factor_ids": list(candidates or []),
        "passed_factor_ids": list(passed or []),
        "gate": gate,
        "backtest": backtest,
        "effective": bool(effective),
        "_run_dir": str(run_dir),
    }


def summarize_run(combined: dict[str, Any]) -> dict[str, Any]:
    bt = combined.get("backtest") or {}
    delta = bt.get("delta") or {}
    yearly = bt.get("yearly") or {}
    year_sharpes = [_num(v.get("delta_sharpe")) for v in yearly.values()]
    year_sharpes = [x for x in year_sharpes if x is not None]

    gate_rows = (combined.get("gate") or {}).get("rows") or []
    gate_evaluated = len(gate_rows) if gate_rows else len(combined.get("candidate_factor_ids") or [])

    return {
        "run_id": combined.get("run_id"),
        "generated_at": combined.get("generated_at"),
        "run_dir": combined.get("_run_dir"),
        "candidates": len(combined.get("candidate_factor_ids") or []),
        "gate_evaluated": gate_evaluated,
        "gate_passed": len(combined.get("passed_factor_ids") or []),
        "smartx_ran": bool(bt),
        "effective": bool(combined.get("effective")),
        "delta_return_pct": _round_num(delta.get("return_pct"), 2),
        "delta_sharpe": _round_num(delta.get("sharpe"), 3),
        "positive_years": sum(1 for s in year_sharpes if s > 0),
        "year_count": len(year_sharpes),
        "worst_year_delta_sharpe": _round_num(min(year_sharpes), 3) if year_sharpes else None,
        "elapsed_seconds": _round_num(bt.get("elapsed_seconds"), 1),
        "passed_factor_ids": list(combined.get("passed_factor_ids") or []),
        "yearly": {
            year: {
                "delta_return_pct": _round_num(row.get("delta_return_pct"), 2),
                "delta_sharpe": _round_num(row.get("delta_sharpe"), 3),
            }
            for year, row in sorted(yearly.items())
        },
    }


def aggregate_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {
            "run_count": 0,
            "with_candidates": 0,
            "with_gate_pass": 0,
            "with_smartx": 0,
            "effective_count": 0,
            "gate_pass_rate": None,
            "smartx_effective_rate": None,
            "avg_gate_passed_when_ran": None,
            "avg_delta_sharpe_when_smartx": None,
        }

    with_candidates = sum(1 for r in rows if r["candidates"] > 0)
    with_gate_pass = sum(1 for r in rows if r["gate_passed"] > 0)
    with_smartx = sum(1 for r in rows if r["smartx_ran"])
    effective_count = sum(1 for r in rows if r["effective"])
    smartx_sharpes = [r["delta_sharpe"] for r in rows if r["smartx_ran"] and r["delta_sharpe"] is not None]
    gate_passed_counts = [r["gate_passed"] for r in rows if r["gate_passed"] > 0]

    return {
        "run_count": n,
        "with_candidates": with_candidates,
        "with_gate_pass": with_gate_pass,
        "with_smartx": with_smartx,
        "effective_count": effective_count,
        "gate_pass_rate": round(with_gate_pass / n, 4) if n else None,
        "smartx_effective_rate": round(effective_count / with_smartx, 4) if with_smartx else None,
        "avg_gate_passed_when_ran": round(sum(gate_passed_counts) / len(gate_passed_counts), 2)
        if gate_passed_counts
        else None,
        "avg_delta_sharpe_when_smartx": round(sum(smartx_sharpes) / len(smartx_sharpes), 4)
        if smartx_sharpes
        else None,
    }


def build_hints(rows: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    if not rows:
        return ["尚无 mining_runs 记录；先跑 run_discovery_cycle.py。"]

    hints: list[str] = []
    recent = rows[-5:]
    recent_gate_zero = sum(1 for r in recent if r["gate_passed"] == 0)
    recent_smartx_fail = sum(
        1 for r in recent if r["smartx_ran"] and not r["effective"]
    )
    recent_smartx_ran = sum(1 for r in recent if r["smartx_ran"])

    if summary["effective_count"]:
        winners = [r["run_id"] for r in rows if r["effective"]]
        hints.append(f"已有 {summary['effective_count']} 轮 SmartX 通过：{', '.join(winners)}。")

    if recent_gate_zero >= 3:
        hints.append(
            "最近 5 轮里多数 gate 为 0：优先检查 mining（prompt/seed/lanes）或 holdout 门槛，而不是继续盲跑 SmartX。"
        )
    elif recent_smartx_ran >= 3 and recent_smartx_fail == recent_smartx_ran:
        hints.append(
            "最近若干轮 gate 有产出但 SmartX 均未通过：考虑换机制主题（避免与 Alpha158 重叠），或对近失轮次做 2025 归因。"
        )

    near_miss = [
        r
        for r in rows
        if r["smartx_ran"]
        and not r["effective"]
        and r["delta_sharpe"] is not None
        and r["delta_sharpe"] >= -0.05
        and (r["positive_years"] or 0) >= 2
    ]
    if near_miss:
        ids = ", ".join(r["run_id"] for r in near_miss[-3:])
        hints.append(f"近失轮次（ΔSharpe 接近 0 且多数年份为正）：{ids}，可优先人工复盘。")

    if not hints:
        hints.append("流水线正常；继续按固定节奏跑 cycle，并记录每轮 gate/SmartX 变化。")
    return hints


def _infer_factor_families(factor_ids: list[str]) -> list[str]:
    families: list[str] = []
    patterns = (
        ("Amihud/流动性", ("amihud",)),
        ("隔夜-日内", ("on_minus_intraday", "overnight", "intraday")),
        ("quiet/低波", ("quiet", "lowvol")),
        ("波动/idvol", ("idvol", "realized_vol", "vol")),
        ("动量/反转", ("mom", "reversal", "ret")),
        ("量价/金额", ("amount", "turnover", "vwap")),
        ("基本面", ("funda", "roe", "ep", "bp")),
    )
    lowered = [f.lower() for f in factor_ids]
    for label, keys in patterns:
        if any(any(k in fid for k in keys) for fid in lowered):
            families.append(label)
    return families or ["未分类（看 factor_id 自行判断机制）"]


def _run_verdict(row: dict[str, Any]) -> str:
    if row.get("effective"):
        return "SmartX 通过"
    if not row.get("smartx_ran"):
        return "仅 gate / SmartX 未跑完"
    d_sh = row.get("delta_sharpe")
    worst = row.get("worst_year_delta_sharpe")
    pos_years = row.get("positive_years") or 0
    if d_sh is not None and d_sh >= -0.05 and pos_years >= 2:
        return "近失（全期接近有效，分年稳定性不足）"
    if worst is not None and worst < -0.10:
        return "SmartX 未通过（最差年 ΔSharpe 低于 -0.10）"
    return "SmartX 未通过"


def _format_yearly(row: dict[str, Any]) -> str:
    yearly = row.get("yearly") or {}
    if not yearly:
        return "分年：无 SmartX 分年数据"
    parts = []
    for year, yrow in sorted(yearly.items()):
        dr = yrow.get("delta_return_pct")
        ds = yrow.get("delta_sharpe")
        dr_s = f"{dr:+.2f}pp" if dr is not None else "NA"
        ds_s = f"{ds:+.3f}" if ds is not None else "NA"
        parts.append(f"{year} ΔRet {dr_s} / ΔSharpe {ds_s}")
    return "分年：" + "；".join(parts)


def _format_run_section(row: dict[str, Any]) -> list[str]:
    run_id = row.get("run_id", "?")
    passed = row.get("passed_factor_ids") or []
    families = _infer_factor_families(passed)
    lines = [
        f"--- 轮次 {run_id}（gate {row.get('gate_passed', 0)}，{_run_verdict(row)}）---",
        f"- gate 通过因子：{', '.join(passed) if passed else '（无）'}",
        f"- 机制画像（由 factor_id 推断）：{', '.join(families)}",
    ]
    if row.get("smartx_ran"):
        dr = row.get("delta_return_pct")
        ds = row.get("delta_sharpe")
        lines.append(
            f"- 全期：ΔRet {dr:+.2f}pp，ΔSharpe {ds:+.3f}"
            if dr is not None and ds is not None
            else "- 全期：SmartX 有跑但缺 delta 指标"
        )
        lines.append(f"- {_format_yearly(row)}")
        worst = row.get("worst_year_delta_sharpe")
        if worst is not None and worst < -0.10:
            lines.append("- 教训：最差年 Sharpe 拖累明显，新因子须提高跨 regime 稳定性（尤其 2025）")
        elif _run_verdict(row).startswith("近失"):
            lines.append("- 教训：有组合 alpha，但 2025 等年份稳定性差 0.01 量级；优先低换手、与 Alpha158 低相关")
        elif (row.get("delta_sharpe") or 0) < 0:
            lines.append("- 教训：组合增量为负，避免重复同类机制微调")
    else:
        lines.append("- 说明：本轮未产出完整 SmartX 对照（可能 cycle 中断或仅完成 gate）")
    return lines


def _load_manual_constraints(path: Path | None = None) -> str:
    path = path or DISCOVERY_CONSTRAINTS_FILE
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return (
        "（未找到 configs/mining_user_discovery_constraints.txt；"
        "请创建该文件以维护人工挖掘约束。）"
    )


def build_discovery_user_text(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    hints: list[str],
    *,
    generated_at: str | None = None,
    constraints_path: Path | None = None,
) -> str:
    ts = generated_at or datetime.now().astimezone().isoformat(timespec="seconds")
    smartx_rows = [r for r in rows if r.get("smartx_ran")]
    history_rows = smartx_rows[-5:] if smartx_rows else rows[-5:]

    auto_lines = [
        "【离线总结 · SmartX 验收反馈（只读参考，勿机械复刻已有 factor_id）】",
        "",
        f"自动生成于：{ts}",
        "背景：discovery cycle = gate(2023) + Alpha158 T+5 SmartX（CSI300 PIT / S30-daily / 择时 / 真实费率）。",
        "终审规则：全期 ΔSharpe≥0.05 且 ΔRet>0；三年中至少两年 ΔSharpe>0；最差年 ΔSharpe≥-0.10。",
        "",
        f"汇总（共 {summary.get('run_count', 0)} 轮）："
        f" gate≥1 {summary.get('with_gate_pass', 0)} 轮，"
        f" SmartX {summary.get('with_smartx', 0)} 轮，"
        f" effective {summary.get('effective_count', 0)} 轮。",
    ]
    if summary.get("avg_delta_sharpe_when_smartx") is not None:
        auto_lines.append(
            f"SmartX 平均 ΔSharpe：{summary['avg_delta_sharpe_when_smartx']:+.3f}"
        )
    auto_lines.append("")
    auto_lines.append("【历史轮次（最近有 SmartX 的最多 5 轮）】")
    if history_rows:
        for row in history_rows:
            auto_lines.extend(_format_run_section(row))
            auto_lines.append("")
    else:
        auto_lines.append("（尚无完整轮次记录）")
        auto_lines.append("")

    auto_lines.append("【自动建议】")
    for hint in hints:
        auto_lines.append(f"- {hint}")

    manual = _load_manual_constraints(constraints_path)
    return (
        f"{AUTO_BEGIN}\n"
        + "\n".join(auto_lines).rstrip()
        + f"\n{AUTO_END}\n\n"
        + f"{MANUAL_BEGIN}\n"
        + manual.rstrip()
        + "\n"
    )


def write_discovery_user_file(
    path: Path,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    hints: list[str],
    *,
    constraints_path: Path | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = build_discovery_user_text(
        rows, summary, hints, constraints_path=constraints_path
    )
    path.write_text(text, encoding="utf-8")


def _fmt_pct(value: float | None, width: int = 7) -> str:
    if value is None:
        return "NA".rjust(width)
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}".rjust(width)


def _fmt_num(value: float | None, width: int = 7, ndigits: int = 3) -> str:
    if value is None:
        return "NA".rjust(width)
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{ndigits}f}".rjust(width)


def _fmt_bool(value: bool, width: int = 5) -> str:
    return ("Y" if value else "N").center(width)


def print_table(rows: list[dict[str, Any]]) -> None:
    header = (
        f"{'run_id':18s} {'cand':>4s} {'gate':>4s} {'sx':>2s} {'eff':>3s} "
        f"{'ΔRet%':>7s} {'ΔShp':>7s} {'y+':>3s} {'worstΔShp':>9s} {'sec':>7s}"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{str(r['run_id']):18s} "
            f"{r['candidates']:4d} "
            f"{r['gate_passed']:4d} "
            f"{_fmt_bool(r['smartx_ran'], 2)} "
            f"{_fmt_bool(r['effective'], 3)} "
            f"{_fmt_pct(r['delta_return_pct'])} "
            f"{_fmt_num(r['delta_sharpe'])} "
            f"{(str(r['positive_years']) if r['year_count'] else '-'):>3s} "
            f"{_fmt_num(r['worst_year_delta_sharpe'], 9)} "
            f"{_fmt_num(r['elapsed_seconds'], 7, 0)}"
        )


def print_summary_block(summary: dict[str, Any], hints: list[str]) -> None:
    print()
    print("汇总")
    print(f"  轮次: {summary['run_count']}")
    print(f"  有候选: {summary['with_candidates']} | gate≥1: {summary['with_gate_pass']} | SmartX: {summary['with_smartx']}")
    print(f"  effective: {summary['effective_count']}")
    if summary["gate_pass_rate"] is not None:
        print(f"  gate 通过率: {summary['gate_pass_rate'] * 100:.1f}%")
    if summary["smartx_effective_rate"] is not None:
        print(f"  SmartX 通过率（在有回测的轮次中）: {summary['smartx_effective_rate'] * 100:.1f}%")
    if summary["avg_gate_passed_when_ran"] is not None:
        print(f"  gate 通过时平均因子数: {summary['avg_gate_passed_when_ran']:.1f}")
    if summary["avg_delta_sharpe_when_smartx"] is not None:
        print(f"  SmartX 平均 ΔSharpe: {summary['avg_delta_sharpe_when_smartx']:+.3f}")
    print()
    print("建议")
    for line in hints:
        print(f"  - {line}")


def collect_runs(runs_dir: Path) -> list[dict[str, Any]]:
    if not runs_dir.is_dir():
        return []

    loaded: list[tuple[tuple, dict[str, Any]]] = []
    for child in runs_dir.iterdir():
        if not child.is_dir():
            continue
        payload = load_run(child)
        if payload is None:
            continue
        loaded.append((_sort_key(child, payload), payload))

    loaded.sort(key=lambda item: item[0])
    return [summarize_run(payload) for _, payload in loaded]


def filter_rows(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    out = rows
    if args.effective_only:
        out = [r for r in out if r["effective"]]
    if args.gate_pass_only:
        out = [r for r in out if r["gate_passed"] > 0]
    if args.last and args.last > 0:
        out = out[-args.last :]
    return out


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "run_id",
        "generated_at",
        "candidates",
        "gate_evaluated",
        "gate_passed",
        "smartx_ran",
        "effective",
        "delta_return_pct",
        "delta_sharpe",
        "positive_years",
        "year_count",
        "worst_year_delta_sharpe",
        "elapsed_seconds",
        "passed_factor_ids",
        "run_dir",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            item = dict(row)
            item["passed_factor_ids"] = ",".join(item.get("passed_factor_ids") or [])
            writer.writerow({k: item.get(k) for k in fields})


def main() -> int:
    args = _parse_args()
    runs_dir = args.runs_dir.expanduser().resolve()

    all_rows = collect_runs(runs_dir)
    rows = filter_rows(all_rows, args)
    summary = aggregate_summary(all_rows)
    hints = build_hints(all_rows, summary)

    if not rows:
        print(f"未找到可汇总的轮次: {runs_dir}")
        if not runs_dir.is_dir():
            print("提示：目录不存在；先跑 run_discovery_cycle.py 生成 artifacts/mining_runs/<run_id>/")
        return 1

    print(f"mining_runs: {runs_dir}  (显示 {len(rows)}/{len(all_rows)} 轮)")
    print_table(rows)
    print_summary_block(summary, hints)

    payload = {
        "runs_dir": str(runs_dir),
        "generated_at": datetime.now().astimezone().isoformat(),
        "rows": rows,
        "summary": summary,
        "hints": hints,
    }
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON: {args.json_out}")
    if args.csv_out:
        write_csv(args.csv_out, rows)
        print(f"CSV: {args.csv_out}")
    if args.update_discovery_user:
        out = args.discovery_user_file.expanduser().resolve()
        write_discovery_user_file(out, all_rows, summary, hints)
        print(f"\n已更新挖掘离线总结: {out}")
        print("  人工约束编辑: configs/mining_user_discovery_constraints.txt")
    elif all_rows:
        print(
            "\n提示：本次未更新 configs/mining_user_discovery.txt；"
            "加 --update-discovery-user 可同步到下一轮挖掘 --user-file"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
