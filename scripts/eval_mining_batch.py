#!/usr/bin/env python3
"""批量评估本轮 submit 因子在 train / val / holdout 三个窗上的表现。

用法:
  uv run python scripts/eval_mining_batch.py --registry artifacts/factorzoo/stock_1d/mining_delivered_registry.json

  # 只看本轮 submit 的因子（默认过滤 source=submit）
  uv run python scripts/eval_mining_batch.py --source-filter submit

  # 全部因子（包括 seed 导入）
  uv run python scripts/eval_mining_batch.py --source-filter all
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alphaagent.core.paths import PANEL_PATH  # noqa: E402
from alphaagent.data.panel import load_panel  # noqa: E402
from alphaagent.factor.eval import evaluate_factor_windows  # noqa: E402
from alphaagent.factor.mining.registry_io import load_mining_registry  # noqa: E402
from alphaagent.factor.mining.submit import check_holdout_metrics  # noqa: E402


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="批量评估挖掘因子的 train/val/holdout 表现")
    p.add_argument("--registry", type=Path, default=ROOT / "artifacts/factorzoo/stock_1d/mining_delivered_registry.json")
    p.add_argument("--panel", type=Path, default=PANEL_PATH)
    # 挖掘管线（run_factor_mining_parallel.sh / submit holdout 复检）统一用
    # label_10d_close_to_close，批筛查必须同标签，否则 IC 不可比、方向可能假翻号
    p.add_argument("--label-col", default="label_10d_close_to_close")
    p.add_argument("--train-start", default="2019-01-01")
    p.add_argument("--train-end", default="2023-12-31")
    p.add_argument("--val-start", default="2024-01-01")
    p.add_argument("--val-end", default="2025-12-31")
    p.add_argument("--holdout-start", default="2026-01-01")
    p.add_argument("--holdout-end", default="2026-07-31")
    p.add_argument(
        "--source-filter",
        default="submit",
        help="'submit'(默认)—只看挖掘 submit 的因子；'all'—全部注册的因子；逗号列表—指定来源",
    )
    p.add_argument(
        "--factor-ids",
        default=None,
        help="只评估这些 factor_id（逗号分隔）；用于隔离本轮新挖掘产物",
    )
    p.add_argument(
        "--since",
        default=None,
        help="只评估 ingested_at >= 该日期(YYYY-MM-DD)的因子，如 --since 2026-08-04 只看昨天本轮",
    )
    p.add_argument(
        "--until",
        default=None,
        help="只评估 ingested_at <= 该日期(YYYY-MM-DD)的因子",
    )
    p.add_argument("--min-holdout-ic", type=float, default=0.005, help="holdout 最小 |IC|（默认 0.005）")
    p.add_argument("--min-holdout-icir", type=float, default=0.05, help="holdout 最小 |ICIR|（默认 0.05）")
    p.add_argument(
        "--min-holdout-t",
        type=float,
        default=2.0,
        help="holdout 最小 t 值 = |ICIR|×√n_days（默认 2.0；传 0 关闭）",
    )
    p.add_argument(
        "--no-sign-consistency",
        action="store_true",
        help="默认要求 holdout IC 与 val IC 同号；加此开关关闭方向一致性检查",
    )
    p.add_argument("--panel-cache", type=Path, default=None, help="预加载 panel 的 pickle（加速多次评测）")
    p.add_argument("--json-out", type=Path, default=None,
                   help="把结果写成 JSON（供 sync_factor_status.py --from-eval 回填台账）")
    p.add_argument(
        "--workers",
        type=int,
        default=None,
        help="并行进程数（默认=min(cpu核心, 8)；传 1 则串行。CPU 密集任务建议=核心数）",
    )
    return p.parse_args()


def _resolve(root: Path, expr_file: str) -> Path:
    p = Path(expr_file)
    return p if p.is_absolute() else root / p


def _pass_thresholds(
    summary: dict,
    min_ic: float,
    min_icir: float,
    *,
    min_t: float = 2.0,
    ref_ic: float | None = None,
) -> tuple[bool, str]:
    """检查 holdout 门槛（同 check_holdout_metrics 但可调参）。

    新增：t 值显著性（|ICIR|×√n_days ≥ min_t）与方向一致性（holdout IC 与
    ref_ic（默认 val IC）同号，防止仅靠 holdout 方向翻转通过筛选）。
    """
    ic = summary.get("ic")
    icir = summary.get("icir")
    reasons: list[str] = []
    if ic is None or abs(float(ic)) < min_ic:
        reasons.append(f"|ic|={abs(ic) if ic else 'NA'}")
    if icir is None or abs(float(icir)) <= min_icir:
        reasons.append(f"|icir|={abs(icir) if icir else 'NA'}")
    n_days = summary.get("n_days")
    if min_t > 0 and icir is not None and n_days:
        t_stat = abs(float(icir)) * (int(n_days) ** 0.5)
        if t_stat < min_t:
            reasons.append(f"t={t_stat:.2f}<{min_t}")
    if ref_ic is not None and ic is not None:
        ref_f, ic_f = float(ref_ic), float(ic)
        if ref_f != 0.0 and ic_f != 0.0 and (ref_f > 0) != (ic_f > 0):
            reasons.append("sign_flip")
    mls = summary.get("mls_fmb") or {}
    mean_ls = mls.get("mean_ls")
    if ic is not None and mean_ls is not None:
        ic_f, ls_f = float(ic), float(mean_ls)
        if ic_f > 0 and ls_f <= 0:
            reasons.append("ls_sign")
        if ic_f < 0 and ls_f >= 0:
            reasons.append("ls_sign")
    return len(reasons) == 0, ",".join(reasons) if reasons else "ok"


def _short(s: str | None, width: int = 10) -> str:
    if s is None:
        return "NA".rjust(width)
    return f"{float(s):.{max(4, width-4)}f}".rjust(width)


def _pct(v: float | None, width: int = 7) -> str:
    if v is None:
        return "NA".rjust(width)
    return f"{float(v)*100:.1f}%".rjust(width)


# ---------------------------------------------------------------------------
# 多进程 worker：每个子进程通过模块全局量继承 panel 和参数（fork，COW 共享）
# ---------------------------------------------------------------------------
_PANEL = None  # pd.DataFrame，worker 共享（fork 后由子进程 COW 继承）
_WARGS: argparse.Namespace | None = None


def _evaluate_one(item: tuple[str, dict]) -> tuple[str, str | dict]:
    """单个因子的求值任务，在子进程里执行。返回 ("row", row_dict) 或 ("error", msg)。"""
    factor_id, entry = item
    args = _WARGS
    panel = _PANEL
    expr_file = entry.get("expression_file", "")
    if not expr_file:
        return ("error", f"{factor_id}: expression_file 为空")
    dsl_path = _resolve(ROOT, expr_file)
    if not dsl_path.is_file():
        return ("error", f"{factor_id}: 找不到表达式文件 {dsl_path}")
    expr = dsl_path.read_text(encoding="utf-8").strip()
    if not expr:
        return ("error", f"{factor_id}: 空表达式")
    try:
        win_metrics = evaluate_factor_windows(
            expr, panel,
            {
                "holdout": (args.holdout_start, args.holdout_end),
                "val": (args.val_start, args.val_end),
                "train": (args.train_start, args.train_end),
            },
            label_col=args.label_col,
        )
    except Exception as exc:  # noqa: BLE001
        return ("error", f"{factor_id}: 求值失败 ({type(exc).__name__}: {exc})")
    ho = win_metrics["holdout"]
    val = win_metrics["val"]
    train = win_metrics["train"]
    ho_ok, ho_reason = _pass_thresholds(
        ho, args.min_holdout_ic, args.min_holdout_icir,
        min_t=args.min_holdout_t,
        ref_ic=None if args.no_sign_consistency else val.get("ic"),
    )
    ho_icir, ho_n_days = ho.get("icir"), ho.get("n_days")
    ho_t = (
        abs(float(ho_icir)) * (int(ho_n_days) ** 0.5)
        if ho_icir is not None and ho_n_days
        else None
    )
    row = {
        "factor_id": factor_id,
        "name": entry.get("name", factor_id),
        "source": entry.get("source", "?"),
        "train_ic": train.get("ic"),
        "train_icir": train.get("icir"),
        "train_coverage": train.get("coverage"),
        "val_ic": val.get("ic"),
        "val_icir": val.get("icir"),
        "val_coverage": val.get("coverage"),
        "ho_ic": ho.get("ic"),
        "ho_icir": ho.get("icir"),
        "ho_t": ho_t,
        "ho_coverage": ho.get("coverage"),
        "ho_pass": ho_ok,
        "ho_reason": ho_reason,
    }
    return ("row", row)


def main() -> int:
    args = _parse_args()

    registry = load_mining_registry(args.registry)
    if not registry:
        print("错误：registry 为空或找不到", file=sys.stderr)
        return 1
    print(f"registry: {args.registry}  ({len(registry)} 个记录)")

    # 过滤 source
    if args.source_filter == "all":
        selected = list(registry.items())
    elif args.source_filter == "submit":
        selected = [(k, v) for k, v in registry.items() if v.get("source") == "submit"]
    else:
        sources = set(s.strip() for s in args.source_filter.split(","))
        selected = [(k, v) for k, v in registry.items() if v.get("source") in sources]

    if args.factor_ids:
        requested = {s.strip() for s in args.factor_ids.split(",") if s.strip()}
        missing = sorted(requested - set(registry))
        if missing:
            print(f"错误：registry 不存在因子: {missing}", file=sys.stderr)
            if set(missing) <= {"id1", "id2", "id3"}:
                print(
                    "提示：id1/id2 只是文档占位符，请换成 registry 里的真实 factor_id。",
                    file=sys.stderr,
                )
            print("可用 factor_id：", file=sys.stderr)
            for fid in sorted(registry):
                src = (registry[fid] or {}).get("source", "?")
                ts = str((registry[fid] or {}).get("ingested_at") or "")[:19]
                print(f"  {fid}  source={src}  ingested_at={ts or '?'}", file=sys.stderr)
            return 2
        selected = [(k, v) for k, v in selected if k in requested]

    # 过滤 ingested_at 日期范围
    if args.since or args.until:
        def _in_range(v: dict) -> bool:
            ts = str(v.get("ingested_at") or "")[:10]
            if args.since and ts < args.since:
                return False
            if args.until and ts > args.until:
                return False
            return True
        before = len(selected)
        selected = [(k, v) for k, v in selected if _in_range(v)]
        print(f"日期过滤(--since {args.since or '-'} --until {args.until or '-'}): {before} → {len(selected)}")

    print(f"筛选 source={args.source_filter!r} → {len(selected)} 个因子\n")

    if not selected:
        print("没有符合筛选条件的因子。")
        return 0

    print("加载 panel...", end=" ", flush=True)
    t0 = time.perf_counter()
    if args.panel_cache and Path(args.panel_cache).is_file():
        import pickle
        panel = pickle.loads(Path(args.panel_cache).read_bytes())
        print(f"pickle cache ({time.perf_counter()-t0:.1f}s) shape={panel.shape}")
    else:
        panel = load_panel(args.panel)
        print(f"parquet ({time.perf_counter()-t0:.1f}s) shape={panel.shape}")

    # 只排一次序，worker（fork 共享）直接复用，省去每个因子的重复 sort_index
    ts = time.perf_counter()
    panel = panel.sort_index()
    print(f"sort_index ({time.perf_counter()-ts:.1f}s)")

    rows: list[dict] = []
    errors: list[str] = []

    workers = args.workers
    if workers is None:
        workers = min(os.cpu_count() or 1, 8)
    use_parallel = workers >= 2 and len(selected) >= 2

    if use_parallel:
        # 限制每个 worker 的 BLAS/numba 线程数为 1：避免 16 进程 × 每进程多线程互相抢核，
        # 让"进程级并行"成为唯一并行源，总 CPU 才线性随核数涨。
        for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                   "NUMBA_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
            os.environ[_k] = "1"
        # fork 下子进程继承模块全局 _PANEL/_WARGS（COW 共享内存，零序列化开销）
        global _PANEL, _WARGS
        _PANEL = panel
        _WARGS = args
        res_by_id: dict[str, tuple[str, str | dict]] = {}
        t_par = time.perf_counter()
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_evaluate_one, it): it[0] for it in selected}
            for fut in as_completed(futs):
                res_by_id[futs[fut]] = fut.result()
        for factor_id, _entry in selected:
            status, payload = res_by_id[factor_id]
            if status == "row":
                rows.append(payload)
            else:
                errors.append(payload)
        print(f"并行求值 {len(selected)} 个因子 x{workers} 进程 ({time.perf_counter()-t_par:.1f}s)")
    else:
        for factor_id, entry in selected:
            status, payload = _evaluate_one((factor_id, entry))
            if status == "row":
                rows.append(payload)
            else:
                errors.append(payload)

    # --- 打印表格 ---
    sep = "-" * 138
    header = (
        f"{'factor_id':22s} {'source':8s} "
        f"{'train_IC':10s} {'ICIR':8s} {'cov':7s}  "
        f"{'val_IC':10s} {'ICIR':8s} {'cov':7s}  "
        f"{'ho_IC':10s} {'ICIR':8s} {'t':6s} {'cov':7s}  {'ho_pass?':10s}"
    )
    print(sep)
    print(header)
    print(sep)
    for r in rows:
        fname = r["factor_id"][:20]
        line = (
            f"{fname:22s} {r['source']:8s} "
            f"{_short(r['train_ic'])} {_short(r['train_icir'],8)} {_pct(r['train_coverage'])}  "
            f"{_short(r['val_ic'])} {_short(r['val_icir'],8)} {_pct(r['val_coverage'])}  "
            f"{_short(r['ho_ic'])} {_short(r['ho_icir'],8)} {_short(r['ho_t'],6)} {_pct(r['ho_coverage'])}  "
            f"{'PASS' if r['ho_pass'] else 'FAIL':10s}"
        )
        print(line)
    print(sep)

    # --- 汇总 ---
    n_pass = sum(1 for r in rows if r["ho_pass"])
    print(f"\n共 {len(rows)} 个因子，holdout 通过 {n_pass} 个")
    sign_note = "否" if args.no_sign_consistency else "是(与 val IC 同号)"
    print(f"门槛: |IC|≥{args.min_holdout_ic} |ICIR|>{args.min_holdout_icir} "
          f"t≥{args.min_holdout_t} 方向一致={sign_note}")
    if errors:
        print(f"\n跳过 {len(errors)} 个（因表达式文件缺失/空）：")
        for e in errors:
            print(f"  {e}")

    if args.json_out is not None:
        payload = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "windows": {
                "train": (args.train_start, args.train_end),
                "val": (args.val_start, args.val_end),
                "holdout": (args.holdout_start, args.holdout_end),
            },
            "rows": rows,
            "errors": errors,
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结果已写入: {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
