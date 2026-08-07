"""将 FactorEvalTools 包装为 AgentScope FunctionTool。"""

from __future__ import annotations

import os
import time
from concurrent.futures import TimeoutError as FutureTimeoutError
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from agentscope.message import TextBlock
from agentscope.tool import FunctionTool, Toolkit, ToolChunk

from alphaagent.factor.mining.tools import FactorEvalTools

_EXECUTOR: ThreadPoolExecutor | None = None

# 单次工具评估超时（秒）：病态 DSL（超长窗口/昂贵算子）可能烧 CPU 数小时，
# 超时后向模型返回错误；僵死线程会被 _force_shutdown_executor 在退出时清理。
EVAL_TIMEOUT_SECONDS = float(os.getenv("MINING_EVAL_TIMEOUT", "900"))


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


def _dispatch_with_timeout(
    tools: FactorEvalTools,
    name: str,
    arguments: dict[str, Any],
    *,
    timeout: float = EVAL_TIMEOUT_SECONDS,
) -> tuple[dict[str, Any], float]:
    """在共享执行器上跑 dispatch，超时返回错误结果（僵死线程由退出清理处理）。"""
    executor = _executor(1)
    future = executor.submit(_dispatch_sync, tools, name, arguments)
    t0 = time.perf_counter()
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError:
        elapsed = round(time.perf_counter() - t0, 2)
        return (
            {
                "ok": False,
                "error": (
                    f"工具 {name} 超过 {timeout:.0f}s 被放弃（表达式可能过于昂贵："
                    f"请缩短窗口/降低复杂度后重试）"
                ),
            },
            elapsed,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = round(time.perf_counter() - t0, 4)
        return {"ok": False, "error": f"工具执行异常: {exc!r}"}, elapsed


def _force_shutdown_executor() -> None:
    """退出前清理：放弃僵死评估线程，避免解释器 join 导致进程永不退出。"""
    global _EXECUTOR
    executor = _EXECUTOR
    if executor is None:
        return
    for thread in list(getattr(executor, "_threads", set())):
        lock = getattr(thread, "_tstate_lock", None)
        if lock is not None:
            thread._tstate_lock = None  # 解除退出时的 join 等待
    executor.shutdown(wait=False, cancel_futures=True)
    _EXECUTOR = None


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
            None,
            _dispatch_with_timeout,
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
            None,
            _dispatch_with_timeout,
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
            None,
            _dispatch_with_timeout,
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
                None,
                _dispatch_with_timeout,
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
