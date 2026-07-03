"""mining 包最小单测：算子清单、prompt、种子因子。"""

from __future__ import annotations

from pathlib import Path

from seekalpha.dsl.catalog import list_operator_names, operator_catalog_markdown
from seekalpha.factor.mining.console import _metrics_parts
from seekalpha.factor.mining.prompts import build_system_prompt
from seekalpha.factor.mining.seed_factors import build_user_message_with_seed_factors


def test_build_user_message_with_seed_factors(tmp_path: Path) -> None:
    dsl = tmp_path / "my_factor.dsl"
    dsl.write_text("raw = TS_MEAN($adj_close, 20)\nSUBTRACT($adj_close, raw)", encoding="utf-8")
    msg = build_user_message_with_seed_factors(
        "继续优化 IC",
        [dsl],
        repo_root=tmp_path,
    )
    assert "初始种子因子" in msg
    assert "my_factor" in msg
    assert "TS_MEAN($adj_close, 20)" in msg
    assert "继续优化 IC" in msg
    assert "eval_on_train_set" in msg


def test_operator_catalog_non_empty() -> None:
    names = list_operator_names()
    assert names and all(n.isupper() or "_" in n for n in names)
    md = operator_catalog_markdown()
    assert "`TS_MEAN" in md


def test_system_prompt_sections() -> None:
    prompt = build_system_prompt()
    assert "因子构建接口" in prompt
    assert "eval_on_train_set" in prompt
    assert "submit_factor" in prompt
    assert "会话完成条件" in prompt
    assert "stored=true" in prompt
    assert "cs_pearson_autocorr" in prompt
    assert "mls_fmb" in prompt
    assert "mean_rho" in prompt
    assert "TS_MEAN" in prompt
    assert "@1w" in prompt
    assert "$funda_roe" in prompt
    assert "funda_days_since_disclose" in prompt
    assert "tool_calls" in prompt
    bare = build_system_prompt(include_operator_catalog=False)
    assert "未注入算子清单" in bare
    no_submit = build_system_prompt(enable_submit=False)
    assert "未启用" in no_submit and "submit_factor" in no_submit


def test_metrics_parts_includes_mls_fmb() -> None:
    parts = _metrics_parts(
        {
            "ic": 0.0273,
            "icir": 0.5112,
            "rank_ic": 0.0285,
            "factor_coverage": 0.9071,
            "cs_pearson_autocorr": 0.9581,
            "n_days": 670,
            "n_instruments": 2405,
            "factor_skewness": -0.002,
            "factor_kurtosis": 0.4632,
            "decile_mean_label": [
                {"decile": 1, "mean_label": -0.0067},
                {"decile": 10, "mean_label": 0.0029},
            ],
            "mls_fmb": {
                "mean_rho": -0.0173,
                "nw_t_rho": -0.3873,
                "nw_t_ls": 1.116,
                "mls": -0.0265,
            },
        },
        {"n_months": 33, "mean_monthly_ic": 0.0275, "share_months_ic_positive": 0.758},
        None,
    )
    text = "  ".join(parts)
    assert "ρ=-0.0173" in text
    assert "NWρ=-0.3873" in text
    assert "NWls=1.116" in text
    assert "MLS=-0.0265" in text


def test_system_prompt_includes_session_label() -> None:
    prompt = build_system_prompt(label_col="label_10d_close_to_close", include_operator_catalog=False)
    assert "本次会话 label 列：`label_10d_close_to_close`" in prompt
    assert "10 日持有" in prompt
    assert "长持有 label 提示" in prompt
    assert "label 选用建议" in prompt
    assert "label_1d_close_to_close" in prompt
    assert "仅作**相对参考**" in prompt or "相对参考" in prompt


def test_mining_stream_observer_emits_agent_blocks() -> None:
    from seekalpha.factor.mining.cli_stream import MiningStreamObserver

    events: list[tuple[str, dict]] = []

    def _capture(event: str, payload: dict) -> None:
        events.append((event, payload))

    obs = MiningStreamObserver(emit=_capture, turn=2)
    obs.on_thinking_start()
    obs.on_thinking_delta("分析 IC ")
    obs.on_thinking_delta("趋势")
    obs.on_thinking_end()
    obs.on_text_delta("继续迭代")
    obs.on_text_end()
    obs.on_tool_call_start("tc1", "eval_on_train_set")
    obs.on_tool_call_delta("tc1", '{"factor_name": "x"}')
    obs.on_tool_call_ready("tc1")
    obs.on_tool_result_delta("tc1", '{"ok": true}')
    obs.on_tool_result_end("tc1")

    assert events[0] == ("agent_thinking", {"turn": 2, "content": "分析 IC 趋势"})
    assert events[1] == ("assistant_message", {"turn": 2, "content": "继续迭代"})
    assert events[2][0] == "assistant_tool_call"
    assert events[2][1]["name"] == "eval_on_train_set"
    assert events[3][0] == "tool_results"
    assert events[3][1]["results"][0]["result"]["ok"] is True
