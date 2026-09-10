"""summarize_mining_runs.py 回归。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = ROOT / "scripts" / "summarize_mining_runs.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("summarize_mining_runs", MOD_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


smr = _load_module()
aggregate_summary = smr.aggregate_summary
build_hints = smr.build_hints
collect_runs = smr.collect_runs
load_run = smr.load_run
summarize_run = smr.summarize_run
build_discovery_user_text = smr.build_discovery_user_text
write_discovery_user_file = smr.write_discovery_user_file


def _write_run(
    base: Path,
    run_id: str,
    *,
    candidates: list[str],
    passed: list[str],
    effective: bool,
    delta_return: float,
    delta_sharpe: float,
    yearly: dict | None = None,
) -> Path:
    run_dir = base / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    yearly = yearly or {
        "2024": {"delta_return_pct": 1.0, "delta_sharpe": 0.05},
        "2025": {"delta_return_pct": -1.0, "delta_sharpe": -0.2},
    }
    payload = {
        "run_id": run_id,
        "generated_at": "2026-09-04T10:00:00+00:00",
        "candidate_factor_ids": candidates,
        "passed_factor_ids": passed,
        "gate": {"rows": [{"factor_id": c, "ho_pass": c in passed} for c in candidates]},
        "backtest": {
            "effective": effective,
            "delta": {"return_pct": delta_return, "sharpe": delta_sharpe},
            "yearly": {
                y: {
                    "delta_return_pct": v["delta_return_pct"],
                    "delta_sharpe": v["delta_sharpe"],
                }
                for y, v in yearly.items()
            },
            "elapsed_seconds": 120.0,
        },
        "effective": effective,
    }
    (run_dir / "result.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return run_dir


def test_load_run_from_split_files(tmp_path: Path):
    run_dir = tmp_path / "20260904_175957"
    run_dir.mkdir()
    (run_dir / "gate_eval.json").write_text(
        json.dumps(
            {
                "rows": [
                    {"factor_id": "a", "ho_pass": True},
                    {"factor_id": "b", "ho_pass": False},
                ]
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "smartx_compare.json").write_text(
        json.dumps(
            {
                "run_id": "20260904_175957",
                "effective": False,
                "delta": {"return_pct": -4.5, "sharpe": -0.27},
                "yearly": {"2024": {"delta_sharpe": 0.07}},
            }
        ),
        encoding="utf-8",
    )
    combined = load_run(run_dir)
    assert combined is not None
    assert combined["passed_factor_ids"] == ["a"]
    assert combined["backtest"]["delta"]["sharpe"] == -0.27


def test_collect_and_summarize(tmp_path: Path):
    _write_run(
        tmp_path,
        "20260901_120000",
        candidates=["f1"],
        passed=[],
        effective=False,
        delta_return=0.0,
        delta_sharpe=0.0,
    )
    _write_run(
        tmp_path,
        "20260904_175957",
        candidates=["a", "b"],
        passed=["a"],
        effective=False,
        delta_return=-4.53,
        delta_sharpe=-0.27,
    )
    rows = collect_runs(tmp_path)
    assert [r["run_id"] for r in rows] == ["20260901_120000", "20260904_175957"]
    last = rows[-1]
    assert last["gate_passed"] == 1
    assert last["smartx_ran"] is True
    assert last["worst_year_delta_sharpe"] == -0.2


def test_aggregate_and_hints(tmp_path: Path):
    rows = [
        summarize_run(
            {
                "run_id": "r1",
                "candidate_factor_ids": ["a"],
                "passed_factor_ids": [],
                "backtest": {},
                "effective": False,
            }
        ),
        summarize_run(
            {
                "run_id": "r2",
                "candidate_factor_ids": ["a", "b"],
                "passed_factor_ids": ["a"],
                "backtest": {
                    "delta": {"return_pct": -1.0, "sharpe": -0.02},
                    "yearly": {
                        "2024": {"delta_sharpe": 0.06},
                        "2025": {"delta_sharpe": 0.01},
                    },
                },
                "effective": False,
            }
        ),
    ]
    summary = aggregate_summary(rows)
    assert summary["run_count"] == 2
    assert summary["with_gate_pass"] == 1
    assert summary["smartx_effective_rate"] == 0.0
    hints = build_hints(rows, summary)
    assert hints


def test_build_discovery_user_text(tmp_path: Path):
    rows = [
        {
            "run_id": "20260908_201528",
            "candidates": 3,
            "gate_passed": 3,
            "passed_factor_ids": ["quiet_lowvol_a", "amihud20_x"],
            "smartx_ran": True,
            "effective": False,
            "delta_return_pct": 11.31,
            "delta_sharpe": 0.264,
            "positive_years": 2,
            "worst_year_delta_sharpe": -0.105,
            "yearly": {
                "2024": {"delta_return_pct": 10.54, "delta_sharpe": 0.618},
                "2025": {"delta_return_pct": -1.17, "delta_sharpe": -0.105},
            },
        }
    ]
    summary = aggregate_summary(rows)
    hints = build_hints(rows, summary)
    text = build_discovery_user_text(rows, summary, hints, generated_at="2026-09-10T12:00:00+08:00")
    assert "20260908_201528" in text
    assert "近失" in text
    assert smr.MANUAL_BEGIN in text

    constraints = tmp_path / "constraints.txt"
    constraints.write_text("人工约束测试", encoding="utf-8")
    out = tmp_path / "mining_user_discovery.txt"
    write_discovery_user_file(out, rows, summary, hints, constraints_path=constraints)
    assert "人工约束测试" in out.read_text(encoding="utf-8")
