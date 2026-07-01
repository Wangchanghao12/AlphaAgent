"""mining 包最小单测：算子清单、prompt、种子因子。"""

from __future__ import annotations

from pathlib import Path

from seekalpha.dsl.catalog import list_operator_names, operator_catalog_markdown
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
    assert "tool_calls" in prompt
    bare = build_system_prompt(include_operator_catalog=False)
    assert "未注入算子清单" in bare
    no_submit = build_system_prompt(enable_submit=False)
    assert "未启用" in no_submit and "submit_factor" in no_submit


def test_system_prompt_includes_session_label() -> None:
    prompt = build_system_prompt(label_col="label_10d_close_to_close", include_operator_catalog=False)
    assert "本次会话 label 列：`label_10d_close_to_close`" in prompt
    assert "10 日持有" in prompt
    assert "长持有 label 提示" in prompt
    assert "仅作**相对参考**" in prompt or "相对参考" in prompt
