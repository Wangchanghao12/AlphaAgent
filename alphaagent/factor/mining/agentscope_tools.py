"""将 FactorEvalTools 包装为 AgentScope FunctionTool。"""

from __future__ import annotations

import os
import time
from concurrent.futures import TimeoutError as FutureTimeoutError
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

from agentscope.message import TextBlock
from agentscope.tool import FunctionTool, Toolkit, ToolChunk

from alphaagent.factor.mining.tools import FactorEvalTools

_EXECUTOR: ThreadPoolExecutor | None = None

# 单次工具评估超时（秒）：病态 DSL（超长窗口/昂贵算子）可能烧 CPU 数小时，
# 超时后向模型返回错误；僵死线程会被 _force_shutdown_executor 在退出时清理。
EVAL_TIMEOUT_SECONDS = float(os.getenv("MINING_EVAL_TIMEOUT", "900"))
# 连续超时几次后熔断：超时并不会取消线程，继续探针只会把队列堵死。
EVAL_TIMEOUT_TRIP_AFTER = int(os.getenv("MINING_EVAL_TIMEOUT_TRIP", "3"))

_TIMEOUT_MARK = "超过"
_CIRCUIT_MARK = "评估队列已熔断"


class EvalTimeoutCircuit:
    """进程内连续超时熔断（一个 lane 一个进程）。"""

    def __init__(self, trip_after: int = EVAL_TIMEOUT_TRIP_AFTER) -> None:
        self.trip_after = max(1, trip_after)
        self.consecutive = 0
        self.open = False

    def reset(self) -> None:
        self.consecutive = 0
        self.open = False

    def record_timeout(self) -> None:
        self.consecutive += 1
        if self.consecutive >= self.trip_after:
            self.open = True

    def record_ok(self) -> None:
        self.consecutive = 0
        self.open = False


_CIRCUIT = EvalTimeoutCircuit()


def reset_eval_timeout_circuit(*, trip_after: int | None = None) -> EvalTimeoutCircuit:
    global _CIRCUIT
    _CIRCUIT = EvalTimeoutCircuit(trip_after if trip_after is not None else EVAL_TIMEOUT_TRIP_AFTER)
    return _CIRCUIT


def eval_circuit_is_open() -> bool:
    return _CIRCUIT.open


def is_eval_timeout_error(result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict):
        return False
    err = str(result.get("error") or "")
    return _TIMEOUT_MARK in err or _CIRCUIT_MARK in err


def _timeout_error(name: str, *, timeout: float, queued: bool = False) -> dict[str, Any]:
    if queued or _CIRCUIT.open:
        return {
            "ok": False,
            "error_type": "EvalTimeoutCircuitOpen",
            "error": (
                f"{_CIRCUIT_MARK}：连续 {_CIRCUIT.consecutive} 次 {name} 超时。"
                "超时任务仍占着评估线程，继续探针只会再等 900s。"
                "禁止再用 RANK($adj_close)/$adj_close 探测；停止本会话 eval，已入库因子即本轮交付。"
            ),
        }
    return {
        "ok": False,
        "error_type": "EvalTimeout",
        "error": (
            f"工具 {name} {_TIMEOUT_MARK} {timeout:.0f}s 被放弃。"
            "不要用更简单的探针反复试；若连续超时，停止 eval。"
        ),
    }


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
    max_workers: int = 1,
    timeout: float = EVAL_TIMEOUT_SECONDS,
) -> tuple[dict[str, Any], float]:
    """在共享执行器上跑 dispatch，超时返回错误结果（僵死线程由退出清理处理）。

    max_workers 透传给共享执行器（首次创建时生效），保证一个 lane 内
    多个并发 eval 不会被串行化。
    """
    if _CIRCUIT.open:
        return _timeout_error(name, timeout=timeout, queued=True), 0.0
    executor = _executor(max_workers)
    future = executor.submit(_dispatch_sync, tools, name, arguments)
    t0 = time.perf_counter()
    try:
        result, elapsed = future.result(timeout=timeout)
        if isinstance(result, dict) and result.get("ok"):
            _CIRCUIT.record_ok()
        return result, elapsed
    except FutureTimeoutError:
        elapsed = round(time.perf_counter() - t0, 2)
        _CIRCUIT.record_timeout()
        return _timeout_error(name, timeout=timeout), elapsed
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
            partial(_dispatch_with_timeout, max_workers=max_workers),
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
            partial(_dispatch_with_timeout, max_workers=max_workers),
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
            partial(_dispatch_with_timeout, max_workers=max_workers),
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
                partial(_dispatch_with_timeout, max_workers=max_workers),
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
