"""将 FactorEvalTools 包装为 AgentScope FunctionTool。"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from agentscope.message import TextBlock
from agentscope.tool import FunctionTool, Toolkit, ToolChunk

from alphaagent.factor.mining.tools import FactorEvalTools

_EXECUTOR: ThreadPoolExecutor | None = None


def _executor(max_workers: int) -> ThreadPoolExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = ThreadPoolExecutor(max_workers=max(1, max_workers))
    return _EXECUTOR


def _dispatch_sync(tools: FactorEvalTools, name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], float]:
    t0 = time.perf_counter()
    result = tools.dispatch(name, arguments)
    elapsed = round(time.perf_counter() - t0, 4)
    return result if isinstance(result, dict) else {"ok": False, "error": str(result)}, elapsed


def build_factor_eval_toolkit(tools: FactorEvalTools, *, max_workers: int = 4) -> Toolkit:
    """构建与 OpenAI 版一致的 eval / submit 工具集。"""

    async def eval_on_train_set(
        multi_line_expr: str,
        factor_name: str = "expr",
        include_detail_tables: bool = False,
        label_quantile_n: int = 10,
    ) -> ToolChunk:
        """训练集评估多行因子表达式，返回 summary、monthly_corr_robustness、label_quantile_buckets。"""
        loop = __import__("asyncio").get_running_loop()
        result, _elapsed = await loop.run_in_executor(
            _executor(max_workers),
            _dispatch_sync,
            tools,
            "eval_on_train_set",
            {
                "multi_line_expr": multi_line_expr,
                "factor_name": factor_name,
                "include_detail_tables": include_detail_tables,
                "label_quantile_n": label_quantile_n,
            },
        )
        return ToolChunk(content=[TextBlock(text=tools.result_to_content(result))])

    async def eval_on_val_set(
        multi_line_expr: str,
        factor_name: str = "expr",
        include_detail_tables: bool = False,
        label_quantile_n: int = 10,
        expected_sign: int | None = None,
    ) -> ToolChunk:
        """验证集评估；须传 expected_sign（train IC 符号 1/-1），结果含 sign_check。"""
        loop = __import__("asyncio").get_running_loop()
        args: dict[str, Any] = {
            "multi_line_expr": multi_line_expr,
            "factor_name": factor_name,
            "include_detail_tables": include_detail_tables,
            "label_quantile_n": label_quantile_n,
        }
        if expected_sign is not None:
            args["expected_sign"] = expected_sign
        result, _elapsed = await loop.run_in_executor(
            _executor(max_workers),
            _dispatch_sync,
            tools,
            "eval_on_val_set",
            args,
        )
        return ToolChunk(content=[TextBlock(text=tools.result_to_content(result))])

    async def eval_on_holdout_set(
        multi_line_expr: str,
        factor_name: str = "expr",
        include_detail_tables: bool = False,
        label_quantile_n: int = 10,
        expected_sign: int | None = None,
    ) -> ToolChunk:
        """holdout OOS（如 2026）评估；submit 前须 holdout 达标。"""
        loop = __import__("asyncio").get_running_loop()
        args: dict[str, Any] = {
            "multi_line_expr": multi_line_expr,
            "factor_name": factor_name,
            "include_detail_tables": include_detail_tables,
            "label_quantile_n": label_quantile_n,
        }
        if expected_sign is not None:
            args["expected_sign"] = expected_sign
        result, _elapsed = await loop.run_in_executor(
            _executor(max_workers),
            _dispatch_sync,
            tools,
            "eval_on_holdout_set",
            args,
        )
        return ToolChunk(content=[TextBlock(text=tools.result_to_content(result))])

    func_tools: list[FunctionTool] = [
        FunctionTool(eval_on_train_set, name="eval_on_train_set", is_read_only=True),
        FunctionTool(eval_on_val_set, name="eval_on_val_set", is_read_only=True),
        FunctionTool(eval_on_holdout_set, name="eval_on_holdout_set", is_read_only=True),
    ]

    if tools.submit_service is not None:

        async def submit_factor(
            multi_line_expr: str,
            factor_name: str,
            comment: str,
        ) -> ToolChunk:
            """【正式交付】将保留级候选入库 factorzoo；train/val 达标后必须调用。"""
            loop = __import__("asyncio").get_running_loop()
            result, _elapsed = await loop.run_in_executor(
                _executor(max_workers),
                _dispatch_sync,
                tools,
                "submit_factor",
                {
                    "multi_line_expr": multi_line_expr,
                    "factor_name": factor_name,
                    "comment": comment,
                },
            )
            return ToolChunk(content=[TextBlock(text=tools.result_to_content(result))])

        func_tools.append(FunctionTool(submit_factor, name="submit_factor"))

    return Toolkit(tools=func_tools)


def context_to_openai_messages(agent_context: Any) -> list[dict[str, Any]]:
    """将 AgentScope context 快照为 OpenAI 风格 messages（便于与旧日志格式对齐）。"""
    out: list[dict[str, Any]] = []
    for msg in agent_context:
        role = getattr(msg, "role", None) or getattr(msg, "name", "unknown")
        content = getattr(msg, "content", None)
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
                elif isinstance(block, dict) and block.get("text"):
                    text_parts.append(str(block["text"]))
            content = "\n".join(text_parts)
        out.append({"role": str(role), "content": content})
    return out
