"""因子评估 metrics 测试。"""

from seekalpha.factor import evaluate_factor


def test_evaluate_factor_on_mini_panel(mini_panel):
    metrics = evaluate_factor("$ret", mini_panel)
    assert "ic" in metrics
    assert "coverage" in metrics
    assert metrics["n_days"] >= 0
