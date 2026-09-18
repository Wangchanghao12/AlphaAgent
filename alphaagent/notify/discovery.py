"""discovery / SmartX 结果飞书通知。"""

from __future__ import annotations

import sys
from typing import Any

from alphaagent.notify.feishu import send_feishu_text


def format_smartx_brief(result: dict[str, Any]) -> str:
    run_id = result.get("run_id", "?")
    passed = result.get("passed_factor_ids") or []
    effective = bool(result.get("effective"))
    bt = result.get("backtest") or {}
    delta = bt.get("delta") or {}
    lines = [
        f"run_id: {run_id}",
        f"gate通过: {len(passed)}  effective: {'是' if effective else '否'}",
    ]
    if passed:
        lines.append(f"因子: {', '.join(passed[:6])}{'…' if len(passed) > 6 else ''}")
    if delta:
        lines.append(
            f"ΔRet {float(delta.get('return_pct', 0)):+.2f}pp  "
            f"ΔSharpe {float(delta.get('sharpe', 0)):+.3f}"
        )
    yearly = bt.get("yearly") or {}
    if yearly:
        parts = []
        for year in sorted(yearly):
            row = yearly[year]
            parts.append(f"{year} ΔShp {float(row.get('delta_sharpe', 0)):+.3f}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def emit_feishu(webhook: str, text: str) -> str:
    """发送并打印状态；失败写 stderr 但不抛错。"""
    try:
        status = send_feishu_text(webhook, text)
    except RuntimeError as exc:
        print(f"[feishu] 发送失败: {exc}", file=sys.stderr, flush=True)
        return f"failed:{exc}"
    if status == "skipped:no_webhook":
        print("[feishu] 未配置 FEISHU_WEBHOOK_URL，跳过通知", flush=True)
        return status
    print("[feishu] 已发送", flush=True)
    return status


def notify_smartx_effective(
    result: dict[str, Any],
    *,
    webhook: str,
    headline: str,
) -> str:
    run_id = result.get("run_id", "?")
    brief = format_smartx_brief(result)
    text = f"{headline}\n{brief}\n产物: artifacts/mining_runs/{run_id}/"
    return emit_feishu(webhook, text)
