"""飞书通知与 discovery 循环脚本回归。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load_module("run_discovery_until_effective", ROOT / "scripts/run_discovery_until_effective.py")


def test_format_run_brief():
    text = mod._format_run_brief(
        {
            "run_id": "20260910_120000",
            "passed_factor_ids": ["a", "b"],
            "effective": False,
            "backtest": {
                "delta": {"return_pct": 11.31, "sharpe": 0.264},
                "yearly": {
                    "2024": {"delta_sharpe": 0.618},
                    "2025": {"delta_sharpe": -0.105},
                },
            },
        }
    )
    assert "20260910_120000" in text
    assert "+11.31" in text
    assert "-0.105" in text


def test_feishu_payload_shape():
    payload = json.dumps({"msg_type": "text", "content": {"text": "hi"}}, ensure_ascii=False)
    parsed = json.loads(payload)
    assert parsed["msg_type"] == "text"
    assert parsed["content"]["text"] == "hi"
