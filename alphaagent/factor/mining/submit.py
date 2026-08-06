"""挖掘会话内因子交付入库。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from alphaagent.factor.types import IngestPolicy
from alphaagent.factor.ingest import ingest_factor, load_panel_for_zoo
from alphaagent.factor.types import IngestResult
from alphaagent.factor.eval import evaluate_factor_on_range
from alphaagent.factor.mining.service import StockEvalService
from alphaagent.factor.zoo import DEFAULT_FACTORLIB_ROOT, FactorZoo
from alphaagent.factor.zoo.realign import panel_paths_match, realign_factorlib_to_panel
from alphaagent.factor.mining.registry_io import upsert_mining_registry
from alphaagent.factor.mining.filelock import factor_report_lock


def slug_factor_id(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", str(name).strip().lower())
    return re.sub(r"_+", "_", s).strip("_") or "factor"


CS_PEARSON_AUTOCORR_MIN = 0.6
HOLDOUT_MIN_ABS_IC = 0.005
HOLDOUT_MIN_ABS_ICIR = 0.05
HOLDOUT_MIN_T = 2.0
"""holdout t 值门槛：t = |ICIR| × √n_days（近似 Fama-MacBeth t）。"""


def _is_finite_num(x: Any) -> bool:
    return x is not None and np.isfinite(float(x))


def check_delivery_metrics(metrics: dict[str, Any]) -> tuple[bool, list[str]]:
    """全区间入库指标是否达到保留级候选门槛。"""
    reasons: list[str] = []
    ic = metrics.get("ic")
    if ic is None or abs(float(ic)) < 0.005:
        reasons.append("ic")
    icir = metrics.get("icir")
    if icir is None or abs(float(icir)) <= 0.1:
        reasons.append("icir")
    rank_ic = metrics.get("rank_ic")
    if rank_ic is None or abs(float(rank_ic)) < 0.005:
        reasons.append("rank_ic")
    cov = metrics.get("coverage")
    if cov is None or float(cov) <= 0.9:
        reasons.append("coverage")
    cs_auto = metrics.get("cs_pearson_autocorr")
    if cs_auto is None or float(cs_auto) <= CS_PEARSON_AUTOCORR_MIN:
        reasons.append("cs_pearson_autocorr")
    return len(reasons) == 0, reasons


def check_holdout_metrics(
    summary: dict[str, Any],
    *,
    ref_ic: float | None = None,
    min_t: float = HOLDOUT_MIN_T,
) -> tuple[bool, list[str]]:
    """holdout 窗（如 2026）：IC 须达标、t 值显著、LS 与 IC 同向。

    ``ref_ic`` 传入 train∪val 窗 IC 时，额外要求 holdout IC 与其同号
    （防止仅靠 2026 方向翻转通过筛选的因子入库）。
    """
    reasons: list[str] = []
    ic = summary.get("ic")
    if ic is None or abs(float(ic)) < HOLDOUT_MIN_ABS_IC:
        reasons.append("holdout_ic")
    icir = summary.get("icir")
    if icir is None or abs(float(icir)) < HOLDOUT_MIN_ABS_ICIR:
        reasons.append("holdout_icir")
    n_days = summary.get("n_days")
    if _is_finite_num(icir) and _is_finite_num(n_days) and int(n_days) > 0:
        t_stat = abs(float(icir)) * (int(n_days) ** 0.5)
        if t_stat < min_t:
            reasons.append("holdout_t")
    if ref_ic is not None and _is_finite_num(ref_ic) and float(ref_ic) != 0.0 and _is_finite_num(ic) and float(ic) != 0.0:
        if (float(ic) > 0) != (float(ref_ic) > 0):
            reasons.append("holdout_sign_flip")
    mls = summary.get("mls_fmb") or {}
    mean_ls = mls.get("mean_ls")
    if ic is not None and mean_ls is not None:
        ic_f, ls_f = float(ic), float(mean_ls)
        if np.isfinite(ic_f) and np.isfinite(ls_f):
            if ic_f > 0 and ls_f <= 0:
                reasons.append("holdout_ls_vs_market")
            if ic_f < 0 and ls_f >= 0:
                reasons.append("holdout_ls_vs_market")
    return len(reasons) == 0, reasons


def yearly_holdout_windows(start: str, end: str) -> list[tuple[str, str, str]]:
    """把 holdout 区间按自然年拆分，返回 [(年份标签, 窗起, 窗止), ...]（按时间升序）。"""
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    out: list[tuple[str, str, str]] = []
    for year in range(s.year, e.year + 1):
        w_start = max(s, pd.Timestamp(year, 1, 1))
        w_end = min(e, pd.Timestamp(year, 12, 31))
        out.append((str(year), w_start.strftime("%Y-%m-%d"), w_end.strftime("%Y-%m-%d")))
    return out


def _holdout_year_payload(raw: dict[str, Any]) -> dict[str, Any]:
    summary = raw.get("summary") or {}
    mls = summary.get("mls_fmb") or {}
    return {
        "date_range": raw.get("date_range"),
        "ic": summary.get("ic"),
        "icir": summary.get("icir"),
        "rank_ic": summary.get("rank_ic"),
        "n_days": summary.get("n_days"),
        "mls_mean_ls": mls.get("mean_ls"),
        "mls_nw_t_ls": mls.get("nw_t_ls"),
    }


def check_holdout_yearly(session, *, multi_line_expr: str, factor_id: str) -> dict[str, Any]:
    """holdout 分年复检：最近一年全门槛（gate），更早年份仅 IC 符号翻转时拦截（参考）。

    返回 ``{"passed": bool, "fail_reasons": [...], "gate_year": ..., "per_year": [...]}``。
    """
    ctx = session.ctx
    windows = yearly_holdout_windows(ctx.holdout_start, ctx.holdout_end)
    per_year: list[dict[str, Any]] = []
    fail_reasons: list[str] = []
    gate_ic: float | None = None

    for year, w_start, w_end in windows:
        raw = evaluate_factor_on_range(
            session,
            start=w_start,
            end=w_end,
            multi_line_expr=multi_line_expr,
            factor_name=factor_id,
            split_label=f"holdout_{year}",
        )
        if not raw.get("ok"):
            return {
                "ok": False,
                "passed": False,
                "fail_reasons": [f"holdout_{year}_eval_failed"],
                "gate_year": windows[-1][0],
                "per_year": per_year,
                "error": raw.get("error", "holdout_eval_failed"),
                "error_type": raw.get("error_type", "HoldoutEvalError"),
            }
        summary = raw.get("summary") or {}
        entry = {"year": year, "gate": year == windows[-1][0], **_holdout_year_payload(raw)}
        ok, reasons = check_holdout_metrics(summary)
        entry["passed"] = ok
        entry["fail_reasons"] = reasons
        if entry["gate"]:
            ic = summary.get("ic")
            gate_ic = float(ic) if ic is not None and np.isfinite(float(ic)) else None
            if not ok:
                fail_reasons.extend(f"{year}:{r}" for r in reasons)
        per_year.append(entry)

    # 参考年（升序在 gate 年之前）的符号检查需要 gate_ic，放到 gate 年评估完后统一校验；
    # 不达全门槛不拦截，仅 IC 与门槛年符号翻转视为不泛化
    if gate_ic is not None:
        for entry in per_year:
            if entry["gate"]:
                continue
            ic = entry.get("ic")
            if ic is None:
                continue
            ic_f = float(ic)
            if np.isfinite(ic_f) and ic_f != 0.0 and gate_ic * ic_f < 0:
                entry["fail_reasons"] = [*entry.get("fail_reasons", []), "holdout_sign_flip_vs_gate_year"]
                entry["passed"] = False
                fail_reasons.append(f"{entry['year']}:holdout_sign_flip_vs_gate_year")

    return {
        "ok": True,
        "passed": len(fail_reasons) == 0,
        "fail_reasons": fail_reasons,
        "gate_year": windows[-1][0],
        "per_year": per_year,
    }


class FactorSubmitService:
    """将保留级候选提交至 factorzoo（train-start ~ val-end 求值、指标、截面去重）。"""

    def __init__(
        self,
        service: StockEvalService,
        *,
        factorlib_path: Path,
        registry_path: Path,
        expr_dir: Path,
        repo_root: Path,
        max_cs_corr: float = 0.8,
        similar_top_k: int = 3,
        overwrite: bool = False,
        auto_realign_panel: bool = True,
    ) -> None:
        self.service = service
        self.factorlib_path = Path(factorlib_path).expanduser().resolve()
        self.registry_path = Path(registry_path).expanduser().resolve()
        self.expr_dir = Path(expr_dir).expanduser().resolve()
        self.repo_root = Path(repo_root).resolve()
        self.max_cs_corr = max_cs_corr
        self.similar_top_k = similar_top_k
        self.overwrite = overwrite
        self.auto_realign_panel = auto_realign_panel

    def submit(
        self,
        session_id: str,
        *,
        multi_line_expr: str,
        factor_name: str,
        comment: str,
    ) -> dict[str, Any]:
        expr = multi_line_expr.strip()
        if not expr:
            return {
                "ok": False,
                "stored": False,
                "error": "multi_line_expr_required_non_empty_string",
                "error_type": "ToolArgumentsError",
            }
        if not str(comment).strip():
            return {
                "ok": False,
                "stored": False,
                "error": "comment_required_non_empty_string",
                "error_type": "ToolArgumentsError",
            }

        factor_id = slug_factor_id(factor_name)
        name = str(factor_name).strip() or factor_id

        try:
            session = self.service.sessions.get(session_id)
        except KeyError:
            return {
                "ok": False,
                "stored": False,
                "error": f"session_not_found: {session_id}",
                "error_type": "SessionError",
            }

        ctx = session.ctx
        holdout_payload: dict[str, Any] | None = None
        if ctx.holdout_start and ctx.holdout_end:
            holdout_check = check_holdout_yearly(session, multi_line_expr=expr, factor_id=factor_id)
            if not holdout_check.get("ok", False):
                return {
                    "ok": False,
                    "stored": False,
                    "error": holdout_check.get("error", "holdout_eval_failed"),
                    "error_type": holdout_check.get("error_type", "HoldoutEvalError"),
                    "holdout_check": {"passed": False, **holdout_check},
                }
            holdout_payload = {
                "date_range": {"start": ctx.holdout_start, "end": ctx.holdout_end},
                "passed": holdout_check["passed"],
                "fail_reasons": holdout_check["fail_reasons"],
                "gate_year": holdout_check["gate_year"],
                "per_year": holdout_check["per_year"],
            }
            if not holdout_check["passed"]:
                return {
                    "ok": False,
                    "stored": False,
                    "error": f"holdout_check_failed:{','.join(holdout_check['fail_reasons'])}",
                    "error_type": "HoldoutCheckFailed",
                    "holdout_check": holdout_payload,
                }

        with factor_report_lock(self.factorlib_path):
            try:
                zoo = FactorZoo.open(self.factorlib_path)
            except FileNotFoundError as e:
                return {
                    "ok": False,
                    "stored": False,
                    "error": f"factorlib_not_initialized: {self.factorlib_path}",
                    "error_type": "FactorLibError",
                    "detail": str(e),
                }

            try:
                panel = load_panel_for_zoo(zoo, panel_path=ctx.panel_path)
            except ValueError as e:
                if not self.auto_realign_panel:
                    return {
                        "ok": False,
                        "stored": False,
                        "error": str(e),
                        "error_type": "PanelMismatchError",
                    }
                zoo_panel = Path(zoo.manifest.panel_path)
                if not panel_paths_match(ctx.panel_path, zoo_panel):
                    return {
                        "ok": False,
                        "stored": False,
                        "error": (
                            f"{e}; panel 路径不一致: session={ctx.panel_path} zoo={zoo_panel}，"
                            "请用 --panel 与因子库相同文件，或重新 init_factorlib"
                        ),
                        "error_type": "PanelMismatchError",
                    }
                try:
                    from alphaagent.data.panel import load_panel as _load_panel

                    full_panel = _load_panel(ctx.panel_path).sort_index()
                    realign_info = realign_factorlib_to_panel(
                        self.factorlib_path,
                        panel=full_panel,
                        panel_path=ctx.panel_path,
                    )
                    zoo = FactorZoo.open(self.factorlib_path)
                    panel = full_panel
                except Exception as exc:  # noqa: BLE001
                    return {
                        "ok": False,
                        "stored": False,
                        "error": f"panel_realign_failed: {exc}",
                        "error_type": "PanelRealignError",
                    }
            else:
                realign_info = None

            if realign_info is None and len(panel) != zoo.manifest.n_rows:
                return {
                    "ok": False,
                    "stored": False,
                    "error": (
                        f"panel 行数 {len(panel)} != 库 n_rows {zoo.manifest.n_rows}；"
                        "请用相同 panel 初始化库，或仅用于调试切片"
                    ),
                    "error_type": "PanelMismatchError",
                }

            result = ingest_factor(
                zoo,
                factor_id=factor_id,
                name=name,
                expr=expr,
                panel=panel,
                policy=IngestPolicy.from_context(ctx, max_cs_corr=self.max_cs_corr, similar_top_k=self.similar_top_k),
                overwrite=self.overwrite,
            )

            # 方向一致性复核：gate 年 holdout IC 与 train∪val 全窗 IC 反号 → 视为方向翻转，回滚
            if result.stored and holdout_payload is not None:
                gate_year = holdout_payload.get("gate_year")
                ho_ic = None
                for entry in holdout_payload.get("per_year") or []:
                    if entry.get("year") == gate_year:
                        ho_ic = entry.get("ic")
                        break
                train_ic = result.metrics.get("ic")
                if (
                    _is_finite_num(train_ic)
                    and _is_finite_num(ho_ic)
                    and float(train_ic) != 0.0
                    and float(ho_ic) != 0.0
                    and (float(ho_ic) > 0) != (float(train_ic) > 0)
                ):
                    zoo.delete_factor(factor_id)
                    result = IngestResult(
                        factor_id=result.factor_id,
                        col_idx=None,
                        stored=False,
                        skipped_reason="holdout_sign_flip_vs_trainval",
                        metrics=result.metrics,
                        similarity=result.similarity,
                        extra=result.extra,
                    )

            delivery_ok, delivery_reasons = check_delivery_metrics(result.metrics)
            rolled_back = False
            if result.stored and not delivery_ok:
                zoo.delete_factor(factor_id)
                rolled_back = True
                result = IngestResult(
                    factor_id=result.factor_id,
                    col_idx=None,
                    stored=False,
                    skipped_reason=f"delivery_check_failed:{','.join(delivery_reasons)}",
                    metrics=result.metrics,
                    similarity=result.similarity,
                    extra=result.extra,
                )

            payload: dict[str, Any] = {
                "ok": result.stored,
                "stored": result.stored,
                "factor_id": factor_id,
                "factor_name": name,
                "comment": comment.strip(),
                "eval_range": {"start": ctx.train_start, "end": ctx.val_end},
                "metrics": result.metrics,
                "delivery_check": {"passed": delivery_ok, "fail_reasons": delivery_reasons},
                "similarity": result.similarity,
                "holdout_check": holdout_payload,
                "skipped_reason": result.skipped_reason,
                "rolled_back": rolled_back,
            }
            if realign_info and realign_info.get("realigned"):
                payload["panel_realigned"] = realign_info

            if result.stored:
                policy = IngestPolicy.from_context(ctx, max_cs_corr=self.max_cs_corr, similar_top_k=self.similar_top_k)
                reg_path, dsl_path = upsert_mining_registry(
                    self.registry_path,
                    factor_id=factor_id,
                    name=name,
                    comment=comment.strip(),
                    expr=expr,
                    expr_dir=self.expr_dir,
                    repo_root=self.repo_root,
                    policy=policy,
                    metrics=result.metrics,
                    similarity=result.similarity,
                    ingest_status="stored",
                    source="submit",
                )
                payload["registry_path"] = reg_path
                payload["dsl_path"] = dsl_path
                payload["factorlib_path"] = str(self.factorlib_path)
            elif result.skipped_reason:
                payload["ok"] = False
                if result.skipped_reason.startswith("cs_corr"):
                    payload["error_type"] = "DuplicateFactorError"
                elif result.skipped_reason == "already_exists":
                    payload["error_type"] = "AlreadyExistsError"
                elif result.skipped_reason.startswith("delivery_check_failed"):
                    payload["error_type"] = "DeliveryCheckError"
                elif result.skipped_reason == "holdout_sign_flip_vs_trainval":
                    payload["error_type"] = "HoldoutSignFlipError"
                    payload["rolled_back"] = True
                else:
                    payload["error_type"] = "IngestSkipped"
                payload["error"] = result.skipped_reason
            else:
                payload["ok"] = False
                payload["error_type"] = "IngestError"
                payload["error"] = "ingest_failed"

            return payload


def default_factorlib_path(repo_root: Path) -> Path:
    _ = repo_root  # 兼容旧签名；AlphaAgent 使用固定 artifacts 路径
    return DEFAULT_FACTORLIB_ROOT
