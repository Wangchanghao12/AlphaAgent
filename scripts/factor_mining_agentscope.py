#!/usr/bin/env python3
"""LLM 股票因子挖掘 CLI（AgentScope 版，终端流式输出）。

与 scripts/factor_mining.py 使用相同的 system prompt 与 eval/submit 工具语义；
模型思考、回复与工具结果通过 AgentScope reply_stream 实时打印。

示例：
  uv sync --extra mining
  uv run python scripts/factor_mining_agentscope.py \\
    --panel artifacts/panel/panel_1d.parquet
  uv run python scripts/factor_mining_agentscope.py \\
    --panel artifacts/panel/panel_1d.parquet \\
    --seed-factor examples/factors/ma20_dev.dsl \\
    --user-message "在种子因子基础上继续优化"

环境变量（仓库根 .env）：OPENAI_API_KEY、OPENAI_API_BASE、MODEL。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment,misc]

from alphaagent.core.paths import FACTORZOO_DIR, PANEL_PATH  # noqa: E402
from alphaagent.factor.mining import MiningConfig  # noqa: E402
from alphaagent.factor.mining.agentscope_run import run_factor_mining_agentscope  # noqa: E402
from alphaagent.factor.mining.context import StockEvalContext  # noqa: E402
from alphaagent.factor.mining.seed_factors import build_user_message_with_seed_factors  # noqa: E402
from alphaagent.factor.types import DEFAULT_LABEL_COL  # noqa: E402


def _load_env() -> None:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LLM 股票因子挖掘（AgentScope 流式 CLI）")
    p.add_argument("--panel", default=str(PANEL_PATH))
    p.add_argument("--train-start", default="2018-01-01")
    p.add_argument("--train-end", default="2020-12-31")
    p.add_argument("--val-start", default="2021-01-01")
    p.add_argument("--val-end", default="2023-12-31")
    p.add_argument("--label-col", default=DEFAULT_LABEL_COL)
    p.add_argument(
        "--no-fundamentals",
        action="store_true",
        help="不载入基本面列(funda_*)，省内存；prompt 也会隐藏基本面字段（适合只挖价量因子）",
    )
    p.add_argument("--temperature", type=float, default=None)
    p.add_argument("--max-tokens", type=int, default=8192)
    p.add_argument(
        "--max-turns",
        type=int,
        default=5,
        help=(
            "外层重进 agent 的次数上限（每次 = 一整轮 ReAct，模型自愿停手才回外层）；"
            "同时间接决定 ReAct 内循环上限 max(max_turns*max_tool_calls_per_round, max_turns, 20)。"
            "注意：它无法打断进行中的单次 reply_stream，实际运行长度主要由内循环上限与模型何时停手决定"
        ),
    )
    p.add_argument("--max-tool-calls-per-round", type=int, default=8)
    p.add_argument("--max-tool-workers", type=int, default=4)
    p.add_argument(
        "--max-parallel-eval",
        type=int,
        default=None,
        help="同时进行的 train/val 评估上限；不传则读环境变量 MAX_PARALLEL_EVAL（默认 1）。建议与 --max-tool-workers 匹配",
    )
    p.add_argument("--min-tool-call-rounds", type=int, default=3)
    p.add_argument("--log-dir", default="logs/factor_mining")
    p.add_argument(
        "--user-message",
        default="请在训练集上提出并迭代多个多行因子表达式，再于验证集上检验泛化；目标为提高 abs(IC)/RANKIC 与 ICIR，并兼顾月度稳健性。",
    )
    p.add_argument("--user-file", type=Path, help="从文件读取 user 消息（覆盖 --user-message）")
    p.add_argument(
        "--seed-factor",
        dest="seed_factors",
        action="append",
        nargs="+",
        default=[],
        metavar="PATH",
        help="初始种子因子 .dsl 路径，可重复指定；单次可跟多个路径，如 --seed-factor a.dsl b.dsl",
    )
    p.add_argument("--no-operator-catalog", action="store_true", help="不在 system prompt 中注入算子清单")
    p.add_argument("--quiet", action="store_true", help="不在终端流式打印（仍写 JSONL 日志）")
    p.add_argument("--factorlib", type=Path, default=None, help=f"factorzoo 根目录（默认 {FACTORZOO_DIR}）")
    p.add_argument("--no-submit", action="store_true", help="禁用 submit_factor 交付工具")
    p.add_argument("--max-cs-corr", type=float, default=0.8, help="submit 截面去重 |corr| 上限")
    p.add_argument("--similar-top-k", type=int, default=3, help="查重失败时返回的最相似因子数")
    p.add_argument("--ingest-overwrite", action="store_true", help="submit 时覆盖已存在 factor_id")
    return p.parse_args()


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def main() -> int:
    _load_env()
    args = _parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("错误：未设置 OPENAI_API_KEY，请在 .env 中配置", file=sys.stderr)
        return 2

    model = os.environ.get("MODEL")
    if not model:
        print("错误：未设置 MODEL，请在 .env 中配置", file=sys.stderr)
        return 2

    try:
        import agentscope  # noqa: F401
    except ImportError:
        print("错误：请安装 agentscope（uv sync --extra mining）", file=sys.stderr)
        return 2

    user_message = args.user_file.read_text(encoding="utf-8") if args.user_file else args.user_message
    seed_paths = [Path(p) for batch in args.seed_factors for p in batch]
    if seed_paths:
        try:
            user_message = build_user_message_with_seed_factors(
                user_message, seed_paths, repo_root=ROOT
            )
        except FileNotFoundError as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return 2
    base_url = os.environ.get("OPENAI_API_BASE")

    config = MiningConfig(
        eval=StockEvalContext(
            panel_path=_resolve(args.panel),
            train_start=args.train_start,
            train_end=args.train_end,
            val_start=args.val_start,
            val_end=args.val_end,
            label_col=args.label_col,
            include_fundamentals=not args.no_fundamentals,
        ),
        model=model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        max_turns=args.max_turns,
        max_tool_calls_per_round=args.max_tool_calls_per_round,
        max_tool_workers=args.max_tool_workers,
        max_parallel_eval=args.max_parallel_eval,
        min_tool_call_rounds_before_allow_stop=args.min_tool_call_rounds,
        factorlib_path=_resolve(str(args.factorlib)) if args.factorlib else None,
        enable_submit=not args.no_submit,
        max_cs_corr=args.max_cs_corr,
        similar_top_k=args.similar_top_k,
        ingest_overwrite=args.ingest_overwrite,
    )

    out = asyncio.run(
        run_factor_mining_agentscope(
            config,
            user_message,
            api_key=api_key,
            base_url=base_url,
            log_dir=args.log_dir,
            include_operator_catalog=not args.no_operator_catalog,
            verbose=not args.quiet,
        )
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
