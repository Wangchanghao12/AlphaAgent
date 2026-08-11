#!/usr/bin/env python3
"""因子状态台账：生成 / 更新 configs/factors/factor_status.json。

台账记录每个因子的三类状态：
  eval_*   评估结果（train/val/holdout IC、是否过 2026 门槛、评估日期）
  useful   人工判断是否有用（useful / marginal / useless / null 待评估）
  vnpy_*   是否已导出到 vnpy、是否已在 vnpy 架构中回测过

重复运行是安全的：已有条目的人工字段（useful、vnpy_*、notes）不会被覆盖，
只刷新指标与新增因子；registry 中已删除的因子保留但标记 in_registry=false。

用法:
  # 从 registry 生成/刷新（人工标注保留）
  uv run python scripts/sync_factor_status.py

  # 从 eval_mining_batch.py --json-out 的结果回填 2026 评估列
  uv run python scripts/sync_factor_status.py --from-eval batch_eval_result.json

  # 标记已导出/已回测（逗号分隔多个 id，支持 --all）
  uv run python scripts/sync_factor_status.py --mark-vnpy-exported id1,id2
  uv run python scripts/sync_factor_status.py --mark-vnpy-backtested --all

  # 人工评价（配合 --comment 写备注）
  uv run python scripts/sync_factor_status.py --set-useful useless \
      --ids wk_sq_geom26_stoch39_mkt --comment "holdout 翻号，弃用"
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alphaagent.core.paths import CONFIGS_DIR, MINING_REGISTRY_PATH  # noqa: E402


def load_mining_registry(path: Path) -> dict:
    """轻量读取 registry（不引入 factor 包的重依赖链）。"""
    path = Path(path)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

DEFAULT_STATUS_PATH = CONFIGS_DIR / "factors" / "factor_status.json"
USEFUL_VALUES = ("useful", "marginal", "useless")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _round(v: object, ndigits: int = 4) -> object:
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return round(f, ndigits)


def _new_entry(factor_id: str, entry: dict) -> dict:
    """registry 条目 → 台账新条目（人工字段初始为空）。"""
    metrics = entry.get("ingest_metrics") if isinstance(entry.get("ingest_metrics"), dict) else {}
    return {
        "name": entry.get("name") or factor_id,
        "comment": str(entry.get("comment") or ""),
        "source": entry.get("source") or "?",
        "ingested_at": entry.get("ingested_at"),
        "in_registry": True,
        "eval": {
            "train_ic": _round(metrics.get("ic")),
            "train_icir": _round(metrics.get("icir")),
            "holdout_2026_pass": None,
            "holdout_2026_ic": None,
            "holdout_2026_icir": None,
            "eval_at": None,
        },
        "useful": None,
        "vnpy": {
            "exported": False,
            "backtested": False,
            "exported_at": None,
        },
        "notes": "",
    }


def _sync_from_registry(status: dict, registry: dict) -> tuple[int, int]:
    added = 0
    dropped = 0
    factors: dict = status["factors"]
    for factor_id, entry in registry.items():
        if factor_id not in factors:
            factors[factor_id] = _new_entry(factor_id, entry)
            added += 1
        else:
            # 只刷新客观字段，保留人工标注
            rec = factors[factor_id]
            rec["in_registry"] = True
            rec["name"] = entry.get("name") or rec.get("name") or factor_id
            rec["comment"] = str(entry.get("comment") or rec.get("comment") or "")
            rec["source"] = entry.get("source") or rec.get("source") or "?"
            rec["ingested_at"] = entry.get("ingested_at") or rec.get("ingested_at")
            metrics = entry.get("ingest_metrics") if isinstance(entry.get("ingest_metrics"), dict) else {}
            if metrics:
                rec.setdefault("eval", {})
                rec["eval"]["train_ic"] = _round(metrics.get("ic"))
                rec["eval"]["train_icir"] = _round(metrics.get("icir"))
    for factor_id, rec in factors.items():
        if factor_id not in registry and rec.get("in_registry", True):
            rec["in_registry"] = False
            dropped += 1
    return added, dropped


def _apply_eval_result(status: dict, row: dict) -> bool:
    factor_id = row.get("factor_id")
    rec = status["factors"].get(factor_id)
    if rec is None:
        return False
    ev = rec.setdefault("eval", {})
    ev["train_ic"] = _round(row.get("train_ic"))
    ev["train_icir"] = _round(row.get("train_icir"))
    ev["val_ic"] = _round(row.get("val_ic"))
    ev["val_icir"] = _round(row.get("val_icir"))
    ev["holdout_2026_ic"] = _round(row.get("ho_ic"))
    ev["holdout_2026_icir"] = _round(row.get("ho_icir"))
    ev["holdout_2026_pass"] = bool(row.get("ho_pass"))
    if row.get("ho_reason") and row.get("ho_reason") != "ok":
        ev["holdout_2026_fail_reason"] = row["ho_reason"]
    else:
        ev.pop("holdout_2026_fail_reason", None)
    ev["eval_at"] = _now()
    return True


def _select_ids(status: dict, ids_arg: str | None) -> list[str]:
    if ids_arg == "--all":
        return sorted(status["factors"])
    if not ids_arg:
        raise SystemExit("错误：需要 --ids 列表（或 --all）")
    ids = [s.strip() for s in ids_arg.split(",") if s.strip()]
    missing = [i for i in ids if i not in status["factors"]]
    if missing:
        raise SystemExit(f"错误：台账中不存在这些 factor_id: {missing}")
    return ids


def _print_table(status: dict) -> None:
    header = (
        f"{'factor_id':36s} {'useful':9s} {'ho26':6s} {'ho_IC':8s} "
        f"{'exported':9s} {'backtest':9s} {'note'}"
    )
    print(header)
    print("-" * len(header))
    for factor_id in sorted(status["factors"]):
        rec = status["factors"][factor_id]
        ev = rec.get("eval") or {}
        vnp = rec.get("vnpy") or {}
        ho_pass = ev.get("holdout_2026_pass")
        ho_str = "-" if ho_pass is None else ("PASS" if ho_pass else "FAIL")
        mark = "" if rec.get("in_registry", True) else "  [已出 registry]"
        print(
            f"{factor_id[:36]:36s} {str(rec.get('useful') or '-'):9s} {ho_str:6s} "
            f"{str(ev.get('holdout_2026_ic') if ev.get('holdout_2026_ic') is not None else '-'):8s} "
            f"{str(vnp.get('exported')):9s} {str(vnp.get('backtested')):9s} "
            f"{str(rec.get('notes') or '')[:40]}{mark}"
        )


def main() -> int:
    p = argparse.ArgumentParser(description="维护因子状态台账 factor_status.json")
    p.add_argument("--status-file", type=Path, default=DEFAULT_STATUS_PATH)
    p.add_argument("--registry", type=Path, default=MINING_REGISTRY_PATH)
    p.add_argument("--from-eval", type=Path, default=None,
                   help="eval_mining_batch.py --json-out 的结果 JSON，回填评估列")
    p.add_argument("--mark-vnpy-exported", dest="exported_ids", default=None,
                   help="标记已导出到 vnpy：逗号分隔 id，或 --all")
    p.add_argument("--mark-vnpy-backtested", dest="backtested_ids", default=None,
                   help="标记已在 vnpy 回测：逗号分隔 id，或 --all")
    p.add_argument("--set-useful", choices=USEFUL_VALUES, default=None)
    p.add_argument("--ids", default=None, help="配合 --set-useful / --comment 的因子 id 列表")
    p.add_argument("--comment", default=None, help="追加到所选因子的 notes")
    p.add_argument("--table", action="store_true", help="操作后打印台账总览")
    args = p.parse_args()

    status_path = args.status_file
    if status_path.is_file():
        status = json.loads(status_path.read_text(encoding="utf-8"))
    else:
        status = {"meta": {"description": "因子状态台账（人工标注 + 自动刷新指标）"}, "factors": {}}
    status.setdefault("factors", {})

    # 1) 与 registry 对齐（新增因子 / 客观指标刷新）
    registry = load_mining_registry(args.registry)
    added, dropped = _sync_from_registry(status, registry)

    # 2) 批量评估结果回填
    n_eval = 0
    if args.from_eval is not None:
        rows = json.loads(args.from_eval.read_text(encoding="utf-8"))
        rows = rows.get("rows") if isinstance(rows, dict) else rows
        for row in rows or []:
            if isinstance(row, dict) and _apply_eval_result(status, row):
                n_eval += 1

    # 3) vnpy 状态标记
    for ids_arg, field, ts_field, label in (
        (args.exported_ids, "exported", "exported_at", "已导出 vnpy"),
        (args.backtested_ids, "backtested", None, "已 vnpy 回测"),
    ):
        if ids_arg is None:
            continue
        for fid in _select_ids(status, ids_arg):
            vnp = status["factors"][fid].setdefault("vnpy", {})
            vnp[field] = True
            if ts_field and not vnp.get(ts_field):
                vnp[ts_field] = _now()
            print(f"标记 {fid}: {label}")

    # 4) 人工评价 / 备注
    if args.set_useful or args.comment:
        ids = _select_ids(status, args.ids)
        for fid in ids:
            rec = status["factors"][fid]
            if args.set_useful:
                rec["useful"] = args.set_useful
            if args.comment:
                rec["notes"] = (rec.get("notes") or "").strip()
                rec["notes"] = f"{rec['notes']} [{_now()[:10]}] {args.comment}".strip()

    status["meta"]["updated_at"] = _now()
    status["meta"]["n_factors"] = len(status["factors"])

    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"台账: {status_path}  共 {len(status['factors'])} 个因子"
          f"（新增 {added}，registry 已删除 {dropped}"
          + (f"，回填评估 {n_eval}" if args.from_eval else "") + "）")
    if args.table:
        _print_table(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
