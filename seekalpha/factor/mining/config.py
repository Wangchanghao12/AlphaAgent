"""因子挖掘配置：评估上下文 + LLM/循环参数。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from seekalpha.factor.mining.context import StockEvalContext


@dataclass
class MiningConfig:
    """一次挖掘运行的全部配置。"""

    eval: StockEvalContext
    model: str = "gpt-4o-mini"
    temperature: float | None = None
    max_tokens: int = 8192
    max_turns: int = 16
    max_tool_calls_per_round: int = 8
    max_tool_workers: int = 4
    max_parallel_eval: int | None = None
    """同时进行的 train/val 评估上限；None 时读环境变量 MAX_PARALLEL_EVAL。"""
    min_tool_call_rounds_before_allow_stop: int = 3
    factorlib_path: Path | None = None
    enable_submit: bool = True
    max_cs_corr: float = 0.8
    similar_top_k: int = 3
    ingest_overwrite: bool = False
    auto_realign_panel: bool = True
    registry_path: Path = Path("artifacts/factorzoo/stock_1d/mining_delivered_registry.json")
    expr_dir: Path = Path("artifacts/factorzoo/stock_1d/expressions")
