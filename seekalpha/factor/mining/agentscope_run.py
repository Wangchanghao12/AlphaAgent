"""AgentScope 版因子挖掘编排：复用 prompt/工具上下文，终端流式输出。"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentscope.agent import Agent, ContextConfig, ReActConfig
from agentscope.credential import OpenAICredential
from agentscope.message import UserMsg
from agentscope.model import OpenAIChatModel
from agentscope.permission import PermissionContext, PermissionMode
from agentscope.state import AgentState
from agentscope.workspace import LocalWorkspace

from seekalpha.factor.mining.schemas import SessionCreateRequest
from seekalpha.factor.mining.service import StockEvalService
from seekalpha.factor.mining.agentscope_tools import build_factor_eval_toolkit, context_to_openai_messages
from seekalpha.factor.mining.cli_stream import MiningStreamObserver, stream_to_cli
from seekalpha.factor.mining.config import MiningConfig
from seekalpha.factor.mining.console import ConsolePrinter
from seekalpha.factor.mining.loop import _NUDGE, _submit_record
from seekalpha.factor.mining.operators import list_operator_names
from seekalpha.factor.mining.prompts import build_system_prompt
from seekalpha.factor.mining.submit import FactorSubmitService, default_factorlib_path
from seekalpha.factor.mining.tools import FactorEvalTools

_NUDGE_MSG = _NUDGE


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_model(
    config: MiningConfig,
    *,
    api_key: str,
    base_url: str | None,
    extra_body: dict[str, Any] | None,
) -> OpenAIChatModel:
    params: dict[str, Any] = {
        "max_tokens": config.max_tokens,
        "parallel_tool_calls": True,
    }
    if config.temperature is not None:
        params["temperature"] = config.temperature
    return OpenAIChatModel(
        credential=OpenAICredential(api_key=api_key, base_url=base_url),
        model=config.model,
        parameters=OpenAIChatModel.Parameters(**params),
        stream=True,
        extra_body=extra_body,
    )


async def create_mining_agent(
    *,
    config: MiningConfig,
    system_prompt: str,
    factor_tools: FactorEvalTools,
    workspace: LocalWorkspace,
    api_key: str,
    base_url: str | None,
    extra_body: dict[str, Any] | None,
) -> Agent:
    toolkit = build_factor_eval_toolkit(factor_tools, max_workers=config.max_tool_workers)
    react_iters = max(config.max_turns * config.max_tool_calls_per_round, config.max_turns, 20)
    return Agent(
        name="FactorMiner",
        system_prompt=system_prompt,
        model=_build_model(config, api_key=api_key, base_url=base_url, extra_body=extra_body),
        toolkit=toolkit,
        offloader=workspace,
        react_config=ReActConfig(max_iters=react_iters),
        state=AgentState(
            permission_context=PermissionContext(mode=PermissionMode.BYPASS),
        ),
        context_config=ContextConfig(
            trigger_ratio=0.75,
            reserve_ratio=0.15,
            tool_result_limit=5000,
        ),
    )


async def run_factor_mining_agentscope(
    config: MiningConfig,
    user_message: str,
    *,
    api_key: str,
    base_url: str | None = None,
    log_dir: str | Path = "logs/factor_mining",
    include_operator_catalog: bool = True,
    extra_instructions: str = "",
    extra_body: dict[str, Any] | None = None,
    service: StockEvalService | None = None,
    verbose: bool = True,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """AgentScope 版挖掘入口：与 run_factor_mining 配置一致，CLI 流式输出。"""
    service = service or StockEvalService()
    root = repo_root or _repo_root()
    ctx = config.eval
    session_resp = service.create_session(
        SessionCreateRequest(
            panel_path=str(ctx.panel_path),
            train_start=ctx.train_start,
            train_end=ctx.train_end,
            val_start=ctx.val_start,
            val_end=ctx.val_end,
            label_col=ctx.label_col,
        )
    )

    submit_service: FactorSubmitService | None = None
    if config.enable_submit:
        lib_path = config.factorlib_path or default_factorlib_path(root)
        submit_service = FactorSubmitService(
            service,
            factorlib_path=lib_path,
            registry_path=root / config.registry_path,
            expr_dir=root / config.expr_dir,
            repo_root=root,
            max_cs_corr=config.max_cs_corr,
            similar_top_k=config.similar_top_k,
            overwrite=config.ingest_overwrite,
        )

    factor_tools = FactorEvalTools(service, session_resp.session_id, submit_service=submit_service)
    system_prompt = build_system_prompt(
        include_operator_catalog=include_operator_catalog,
        enable_submit=config.enable_submit,
        extra_instructions=extra_instructions,
        label_col=ctx.label_col,
    )

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_jsonl = log_dir / f"run_{stamp}.jsonl"
    workspace_dir = log_dir / f"agentscope_workspace_{stamp}"
    workspace = LocalWorkspace(workdir=str(workspace_dir))
    await workspace.initialize()

    printer = ConsolePrinter(stream=sys.stderr) if verbose else None
    if printer is not None:
        printer.session_start(config.model, len(list_operator_names()))

    def _emit(event: str, payload: dict[str, Any]) -> None:
        with log_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": _now(), "event": event, **payload}, ensure_ascii=False, default=str) + "\n")

    _emit("session_start", {"model": config.model, "max_turns": config.max_turns, "framework": "agentscope"})

    agent = await create_mining_agent(
        config=config,
        system_prompt=system_prompt,
        factor_tools=factor_tools,
        workspace=workspace,
        api_key=api_key,
        base_url=base_url,
        extra_body=extra_body,
    )

    tool_call_rounds = 0
    outer_turn = 0
    tool_call_rows: list[dict[str, Any]] = []
    submit_records: list[dict[str, Any]] = []
    end_reason = "no_tool_calls"
    pending = user_message

    while outer_turn < config.max_turns:
        if printer is not None:
            printer.turn(outer_turn)

        observer = MiningStreamObserver(printer=printer, emit=None, turn=outer_turn)

        def _on_tool_emit(event: str, payload: dict[str, Any]) -> None:
            _emit(event, payload)
            for row in payload.get("results") or []:
                res = row.get("result") if isinstance(row.get("result"), dict) else {}
                tool_call_rows.append(
                    {
                        "turn": outer_turn,
                        "name": row.get("name"),
                        "elapsed_seconds": row.get("elapsed_seconds"),
                        "ok": res.get("ok"),
                    }
                )
                if row.get("name") == "submit_factor":
                    submit_records.append(
                        _submit_record(
                            turn=outer_turn,
                            arguments_raw=row.get("arguments_raw"),
                            result=res,
                        )
                    )

        observer.emit = _on_tool_emit

        user_msg = UserMsg(name="user", content=pending)
        had_tools = await stream_to_cli(
            agent,
            user_msg,
            show_thinking=True,
            auto_confirm=True,
            observer=observer,
            quiet=not verbose,
        )

        if had_tools:
            tool_call_rounds += 1

        if not had_tools:
            if tool_call_rounds < config.min_tool_call_rounds_before_allow_stop:
                _emit("nudge", {"turn": outer_turn, "tool_call_rounds": tool_call_rounds})
                pending = _NUDGE_MSG
                outer_turn += 1
                continue
            end_reason = "no_tool_calls"
            break

        outer_turn += 1
        if outer_turn >= config.max_turns:
            end_reason = "max_turns_reached"
            break
        pending = "请基于当前工具结果继续迭代；需要时并行 eval_on_train_set，达标后 submit_factor。"
    else:
        end_reason = "max_turns_reached"

    if printer is not None:
        ok = sum(1 for r in tool_call_rows if r.get("ok"))
        printer.session_end(end_reason, ok, len(tool_call_rows))

    messages = context_to_openai_messages(agent.state.context)
    snapshot = log_jsonl.with_suffix(".messages.json")
    snapshot.write_text(json.dumps(messages, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    times = [r["elapsed_seconds"] for r in tool_call_rows if r.get("elapsed_seconds") is not None]
    submitted_factors = [r for r in submit_records if r.get("stored")]
    submit_failures = [r for r in submit_records if not r.get("stored")]
    summary = {
        "log_jsonl": str(log_jsonl),
        "framework": "agentscope",
        "agent_session_id": agent.state.session_id,
        "tool_calls": {
            "count": len(tool_call_rows),
            "ok": sum(1 for r in tool_call_rows if r.get("ok")),
            "elapsed_seconds_total": round(sum(times), 4) if times else 0.0,
        },
        "submitted_factors": submitted_factors,
        "submit_failures": submit_failures,
        "messages_snapshot": str(snapshot),
    }
    log_jsonl.with_suffix(".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    _emit("run_summary", summary)
    _emit("session_end", {"turn": outer_turn, "reason": end_reason})

    return {
        "session_id": session_resp.session_id,
        "agent_session_id": agent.state.session_id,
        "n_messages": len(messages),
        "log_jsonl": str(log_jsonl),
        "messages_snapshot": str(snapshot),
        "summary": str(log_jsonl.with_suffix(".summary.json")),
        "framework": "agentscope",
    }
