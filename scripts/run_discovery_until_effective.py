#!/usr/bin/env python3
"""循环跑 discovery cycle，直到 SmartX effective=true 或达到安全上限。

成功 / 触顶 / 致命错误时可选飞书机器人通知（webhook 放 .env，勿提交）。

用法:
  # .env: FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...
  python scripts/run_discovery_until_effective.py \\
    --vnpy-root /path/to/alpha_research \\
    --alpha-python /path/to/python \\
    --vnpy-python /path/to/python

  nohup python scripts/run_discovery_until_effective.py ... >> log/discovery_until.log 2>&1 &
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CYCLE_SCRIPT = ROOT / "scripts/run_discovery_cycle.py"
RUNS_DIR = ROOT / "artifacts/mining_runs"
STATE_FILE = RUNS_DIR / "discovery_until_state.json"


def _parse_args() -> argparse.Namespace:
    candidates = [
        Path("/mnt/recom/develop/wangchanghao/rtp_fg/em_ak/em_ak/examples/alpha_research"),
        ROOT.parent / "em_ak/em_ak/examples/alpha_research",
    ]
    default_vnpy = next(
        (p for p in candidates if (p / "smallcap_live/config.py").is_file()),
        candidates[0],
    )
    p = argparse.ArgumentParser(description="循环 discovery cycle 直至 SmartX 通过")
    p.add_argument("--vnpy-root", type=Path, default=Path(os.environ.get("VNPY_ALPHA_RESEARCH", default_vnpy)))
    p.add_argument("--alpha-python", default=os.environ.get("ALPHAAGENT_PYTHON", sys.executable))
    p.add_argument("--vnpy-python", default=os.environ.get("VNPY_PYTHON", sys.executable))
    p.add_argument("--lanes", default="momentum,volatility,volume,weekly,crosssectional")
    p.add_argument("--max-turns", type=int, default=8)
    p.add_argument("--max-runs", type=int, default=30, help="最多跑几轮 cycle（安全上限，默认 30）")
    p.add_argument(
        "--max-hours",
        type=float,
        default=168.0,
        help="总时长上限（小时，0=不限；默认 168=7 天）",
    )
    p.add_argument("--sleep-secs", type=float, default=120.0, help="两轮之间休眠秒数（默认 120）")
    p.add_argument(
        "--feishu-webhook",
        default=os.environ.get("FEISHU_WEBHOOK_URL", ""),
        help="飞书群机器人 webhook；也可设环境变量 FEISHU_WEBHOOK_URL",
    )
    p.add_argument("--notify-each-run", action="store_true", help="每轮结束都发飞书（默认仅成功/触顶/失败）")
    p.add_argument("--stop-on-error", action="store_true", help="单轮 cycle 非零退出时立即停止")
    p.add_argument("--dry-run", action="store_true", help="只打印计划，不真正循环")
    return p.parse_args()


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None  # type: ignore[assignment]
    if load_dotenv is not None:
        load_dotenv(env_path, override=False)
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(state: dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def send_feishu_text(webhook: str, text: str, *, timeout: float = 15.0) -> None:
    if not webhook.strip():
        print("[feishu] 未配置 webhook，跳过通知", flush=True)
        return
    payload = json.dumps({"msg_type": "text", "content": {"text": text}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook.strip(),
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"飞书 HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"飞书请求失败: {exc}") from exc
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = {"raw": body}
    if isinstance(parsed, dict) and parsed.get("code") not in (None, 0):
        raise RuntimeError(f"飞书返回错误: {parsed}")


def _format_run_brief(result: dict[str, Any]) -> str:
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


def _build_cycle_cmd(args: argparse.Namespace, run_id: str) -> list[str]:
    return [
        args.alpha_python,
        str(CYCLE_SCRIPT),
        "--vnpy-root",
        str(args.vnpy_root),
        "--alpha-python",
        args.alpha_python,
        "--vnpy-python",
        args.vnpy_python,
        "--lanes",
        args.lanes,
        "--max-turns",
        str(args.max_turns),
        "--run-id",
        run_id,
    ]


def _run_cycle(cmd: list[str], log_path: Path) -> int:
    print(f"\n$ {shlex.join(cmd)}", flush=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as fh:
        process = subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            fh.write(line)
        return process.wait()


def main() -> int:
    _load_dotenv()
    args = _parse_args()
    if not args.feishu_webhook:
        args.feishu_webhook = os.environ.get("FEISHU_WEBHOOK_URL", "")

    if args.dry_run:
        print("计划：循环 run_discovery_cycle.py 直至 effective=true")
        print(f"  max_runs={args.max_runs}  max_hours={args.max_hours or '不限'}")
        print(f"  feishu={'已配置' if args.feishu_webhook else '未配置'}")
        print(f"  示例命令: {shlex.join(_build_cycle_cmd(args, 'YYYYMMDD_HHMMSS'))}")
        return 0

    started = time.time()
    state: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "max_runs": args.max_runs,
        "max_hours": args.max_hours,
        "runs": [],
    }
    _save_state(state)

    for attempt in range(1, args.max_runs + 1):
        elapsed_h = (time.time() - started) / 3600.0
        if args.max_hours > 0 and elapsed_h >= args.max_hours:
            msg = (
                f"[AlphaAgent] discovery 触顶停止\n"
                f"原因: 已达时长上限 {args.max_hours:.1f}h\n"
                f"已完成 {attempt - 1} 轮，尚无 effective 轮次\n"
                f"请查看 artifacts/mining_runs/ 与 summarize_mining_runs.py"
            )
            print(msg, flush=True)
            try:
                send_feishu_text(args.feishu_webhook, msg)
            except RuntimeError as exc:
                print(f"[feishu] {exc}", file=sys.stderr)
            return 2

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        print(f"\n========== cycle {attempt}/{args.max_runs}  run_id={run_id} ==========", flush=True)
        cmd = _build_cycle_cmd(args, run_id)
        log_path = RUNS_DIR / run_id / "cycle.log"
        rc = _run_cycle(cmd, log_path)

        result_path = RUNS_DIR / run_id / "result.json"
        result = _load_json(result_path)
        if not result:
            result = {"run_id": run_id, "effective": False, "error": "missing result.json"}

        brief = _format_run_brief(result)
        print(brief, flush=True)

        entry = {
            "attempt": attempt,
            "run_id": run_id,
            "exit_code": rc,
            "effective": bool(result.get("effective")),
            "passed": len(result.get("passed_factor_ids") or []),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        state["runs"].append(entry)
        _save_state(state)

        if rc != 0:
            err_msg = (
                f"[AlphaAgent] discovery 第 {attempt} 轮异常退出 (code={rc})\n"
                f"{brief}\n"
                f"log: {log_path}"
            )
            print(err_msg, flush=True)
            try:
                send_feishu_text(args.feishu_webhook, err_msg)
            except RuntimeError as exc:
                print(f"[feishu] {exc}", file=sys.stderr)
            if args.stop_on_error:
                return rc

        elif args.notify_each_run and args.feishu_webhook:
            try:
                send_feishu_text(
                    args.feishu_webhook,
                    f"[AlphaAgent] discovery 第 {attempt} 轮完成\n{brief}",
                )
            except RuntimeError as exc:
                print(f"[feishu] {exc}", file=sys.stderr)

        if result.get("effective"):
            win_msg = (
                f"[AlphaAgent] SmartX 通过\n"
                f"第 {attempt} 轮 effective=true\n"
                f"{brief}\n"
                f"产物: artifacts/mining_runs/{run_id}/"
            )
            print(win_msg, flush=True)
            try:
                send_feishu_text(args.feishu_webhook, win_msg)
            except RuntimeError as exc:
                print(f"[feishu] {exc}", file=sys.stderr)
            state["outcome"] = "effective"
            state["win_run_id"] = run_id
            _save_state(state)
            return 0

        if attempt < args.max_runs and args.sleep_secs > 0:
            print(f"休眠 {args.sleep_secs:.0f}s 后开始下一轮…", flush=True)
            time.sleep(args.sleep_secs)

    msg = (
        f"[AlphaAgent] discovery 触顶停止\n"
        f"原因: 已达轮次上限 {args.max_runs}，尚无 effective 轮次\n"
        f"建议: python scripts/summarize_mining_runs.py --last 10\n"
        f"并更新 configs/mining_user_discovery.txt 后再跑"
    )
    print(msg, flush=True)
    try:
        send_feishu_text(args.feishu_webhook, msg)
    except RuntimeError as exc:
        print(f"[feishu] {exc}", file=sys.stderr)
    state["outcome"] = "max_runs"
    _save_state(state)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
