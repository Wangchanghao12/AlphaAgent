"""报告格式化测试。"""

from seekalpha.factor.report import format_factor_report_text


def test_format_factor_report_text():
    text = format_factor_report_text(
        {
            "eval_start": "2024-06-01",
            "eval_end": "2026-05-31",
            "label_col": "label_1d_close_to_close",
            "n_days": 388,
            "ic": -0.003,
            "icir": -0.0437,
            "rank_ic": -0.0081,
            "coverage": 0.9915,
            "cs_pearson_autocorr": 0.931,
            "mls_fmb": {"mean_rho": -0.0135, "mls": 0.012, "n_days_rho": 388},
            "decile_mean_label": [
                {"decile": 1, "mean_label": -0.001},
                {"decile": 10, "mean_label": 0.002},
            ],
        }
    )
    assert "因子评估报告" in text
    assert "IC" in text
    assert "MLS / FMB" in text
    assert "D 1" in text
    assert "D10" in text
