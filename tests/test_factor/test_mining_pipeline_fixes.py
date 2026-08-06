"""挖掘链路修复回归：columns 透传、holdout 分年复检、registry 摘要。"""

from __future__ import annotations

import json
from pathlib import Path

from alphaagent.factor.mining.registry_io import mining_registry_digest
from alphaagent.factor.mining.schemas import SessionCreateRequest
from alphaagent.factor.mining.service import StockEvalService
from alphaagent.factor.mining import submit as submit_mod
from alphaagent.factor.mining.submit import check_holdout_yearly, yearly_holdout_windows
from alphaagent.factor.types import DEFAULT_LABEL_COL


# --- yearly_holdout_windows ---


def test_yearly_holdout_windows_multi_year():
    windows = yearly_holdout_windows("2025-01-01", "2026-07-31")
    assert windows == [
        ("2025", "2025-01-01", "2025-12-31"),
        ("2026", "2026-01-01", "2026-07-31"),
    ]


def test_yearly_holdout_windows_single_year_partial():
    windows = yearly_holdout_windows("2026-02-01", "2026-07-31")
    assert windows == [("2026", "2026-02-01", "2026-07-31")]


# --- mining_registry_digest ---


def test_mining_registry_digest(tmp_path: Path):
    reg = {
        "b_factor": {"name": "b_factor", "comment": "多行\n  注释  " + "x" * 100},
        "a_factor": {"name": "a_factor"},
    }
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
    digest = mining_registry_digest(p, comment_chars=40)
    lines = digest.splitlines()
    assert lines[0].startswith("【factorzoo 已入库因子")
    # 排序稳定：a 在前
    assert lines[1] == "- a_factor"
    assert lines[2].startswith("- b_factor: ")
    assert lines[2].endswith("…")
    assert "\n" not in lines[2]


def test_mining_registry_digest_missing_file(tmp_path: Path):
    assert mining_registry_digest(tmp_path / "nope.json") == ""


# --- create_session columns 透传（lane 内存优化真正生效） ---


def test_create_session_columns_pruning(tmp_path: Path, mini_panel):
    panel_path = tmp_path / "panel.parquet"
    mini_panel.to_parquet(panel_path)
    svc = StockEvalService(max_parallel_eval=1)
    resp = svc.create_session(
        SessionCreateRequest(
            panel_path=str(panel_path),
            train_start="2024-01-01",
            train_end="2024-01-04",
            val_start="2024-01-05",
            val_end="2024-01-10",
            columns=("adj_close", "ret"),
            include_fundamentals=False,
        )
    )
    session = svc.sessions.get(resp.session_id)
    assert session.ctx.columns == ("adj_close", "ret")
    assert set(session.panel.columns) <= {"adj_close", "ret", DEFAULT_LABEL_COL}
    assert DEFAULT_LABEL_COL in session.panel.columns


# --- check_holdout_yearly：gate 年全门槛、参考年只拦符号翻转 ---


class _FakeCtx:
    def __init__(self, holdout_start: str, holdout_end: str) -> None:
        self.holdout_start = holdout_start
        self.holdout_end = holdout_end


class _FakeSession:
    def __init__(self, holdout_start: str, holdout_end: str) -> None:
        self.ctx = _FakeCtx(holdout_start, holdout_end)


def _ok_raw(ic: float, icir: float = 0.2, mean_ls: float | None = None) -> dict:
    if mean_ls is None:
        mean_ls = 0.001 if ic > 0 else -0.001
    return {
        "ok": True,
        "date_range": {"start": "s", "end": "e"},
        "summary": {"ic": ic, "icir": icir, "rank_ic": ic, "n_days": 100, "mls_fmb": {"mean_ls": mean_ls}},
    }


def test_check_holdout_yearly_gate_pass_reference_same_sign(monkeypatch):
    calls: list[tuple[str, str]] = []

    def _stub(session, *, start, end, **kwargs):
        calls.append((start, end))
        return _ok_raw(0.02)

    monkeypatch.setattr(submit_mod, "evaluate_factor_on_range", _stub)
    out = check_holdout_yearly(
        _FakeSession("2025-01-01", "2026-07-31"), multi_line_expr="$close", factor_id="f"
    )
    assert out["ok"] and out["passed"]
    assert out["gate_year"] == "2026"
    assert [c[0] for c in calls] == ["2025-01-01", "2026-01-01"]
    assert [e["year"] for e in out["per_year"]] == ["2025", "2026"]
    assert out["per_year"][1]["gate"] is True


def test_check_holdout_yearly_reference_sign_flip_blocks(monkeypatch):
    def _stub(session, *, start, end, **kwargs):
        # 2025 参考年 IC 符号与 2026 gate 年相反
        return _ok_raw(-0.02) if start.startswith("2025") else _ok_raw(0.02)

    monkeypatch.setattr(submit_mod, "evaluate_factor_on_range", _stub)
    out = check_holdout_yearly(
        _FakeSession("2025-01-01", "2026-07-31"), multi_line_expr="$close", factor_id="f"
    )
    assert out["ok"]
    assert not out["passed"]
    assert "2025:holdout_sign_flip_vs_gate_year" in out["fail_reasons"]
    ref = out["per_year"][0]
    assert ref["passed"] is False


def test_check_holdout_yearly_reference_weak_ic_does_not_block(monkeypatch):
    def _stub(session, *, start, end, **kwargs):
        # 2025 参考年 IC 弱（不达全门槛）但同号 → 只参考不拦截
        return _ok_raw(0.002) if start.startswith("2025") else _ok_raw(0.02)

    monkeypatch.setattr(submit_mod, "evaluate_factor_on_range", _stub)
    out = check_holdout_yearly(
        _FakeSession("2025-01-01", "2026-07-31"), multi_line_expr="$close", factor_id="f"
    )
    assert out["passed"]
    assert out["per_year"][0]["passed"] is False  # 参考年未达全门槛（仅记录）
    assert out["fail_reasons"] == []


def test_check_holdout_yearly_gate_year_fail(monkeypatch):
    def _stub(session, *, start, end, **kwargs):
        return _ok_raw(0.02) if start.startswith("2025") else _ok_raw(0.001, icir=0.01)

    monkeypatch.setattr(submit_mod, "evaluate_factor_on_range", _stub)
    out = check_holdout_yearly(
        _FakeSession("2025-01-01", "2026-07-31"), multi_line_expr="$close", factor_id="f"
    )
    assert not out["passed"]
    assert any(r.startswith("2026:") for r in out["fail_reasons"])


def test_check_holdout_yearly_eval_error(monkeypatch):
    def _stub(session, *, start, end, **kwargs):
        return {"ok": False, "error": "boom", "error_type": "EmptyData"}

    monkeypatch.setattr(submit_mod, "evaluate_factor_on_range", _stub)
    out = check_holdout_yearly(
        _FakeSession("2026-01-01", "2026-07-31"), multi_line_expr="$close", factor_id="f"
    )
    assert not out["ok"]
    assert out["error_type"] == "EmptyData"
