"""MLS-FMB prompt 门槛加载测试。"""

from __future__ import annotations

from alphaagent.factor.mining.mls_thresholds import mls_fmb_prompt_thresholds, mls_fmb_thresholds_markdown
from alphaagent.factor.mining.prompts import build_system_prompt


def test_mls_fmb_prompt_thresholds_loaded() -> None:
    th = mls_fmb_prompt_thresholds()
    assert th["train"]["mean_rho"] > 0
    assert th["val"]["nw_t_rho"] >= th["train"]["nw_t_rho"] * 0.8


def test_system_prompt_includes_mls_fmb_thresholds() -> None:
    prompt = build_system_prompt(include_operator_catalog=False)
    assert "mls_fmb" in prompt
    assert "mean_rho" in prompt
    assert "nw_t_rho" in prompt
    assert "25% 分位" in prompt or "25% 分位" in mls_fmb_thresholds_markdown()
