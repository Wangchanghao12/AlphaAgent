#!/usr/bin/env bash
# 并行因子挖掘：按 lane（信息维度）拆成多个独立进程并发挖掘。
#
# 设计要点（解决"多进程并行"的三大隐患）：
#  1) 内存：每个 lane 只加载自己需要的列（--mine-lane 自动带 --cols），
#     不再每进程加载整份 panel。
#  2) 重复挖掘：每个进程只有一个主维度（lane），prompt 里明确"首要信号必须来自本维度，
#     允许用控制列做中性化/增强"。既避免多进程重复探索，又不牺牲混合因子。
#  3) 提交冲突：所有进程共享同一 factorzoo 因子库，submit 时按 |corr| 去重；
#     提交路径已加跨进程文件锁（fcntl.flock），并发写不互踩/不损坏。
#
# 用法（仓库根目录）：
#   export OPENAI_API_KEY=sk-xxxx
#   bash scripts/run_factor_mining_parallel.sh --lanes momentum,volatility,volume,weekly
#   bash scripts/run_factor_mining_parallel.sh --lanes momentum,fundamental --no-submit --max-turns 3
#
# 前置：同 run_factor_mining.sh（panel 已存在、mining 依赖已装、factorlib 已 init）。

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# 可选：复用本机已有 export（勿把 key 写进仓库）
if [[ -f "${AA_EXPORT_SH:-}" ]]; then
  # shellcheck disable=SC1090
  source "$AA_EXPORT_SH"
elif [[ -f "$HOME/export.sh" ]]; then
  # shellcheck disable=SC1090
  source "$HOME/export.sh"
fi

export OPENAI_API_BASE="${OPENAI_API_BASE:-${AX_LLM_BASE_URL:-https://litellm.spaccez.com/v1}}"
export MODEL="${MODEL:-${AX_LLM_MODEL:-deepseek-v4-flash}}"
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  if [[ -n "${AX_LLM_API_KEY:-}" ]]; then
    export OPENAI_API_KEY="$AX_LLM_API_KEY"
  elif [[ -n "${LITELLM_API_KEY:-}" ]]; then
    export OPENAI_API_KEY="$LITELLM_API_KEY"
  fi
fi
: "${OPENAI_API_KEY:?请先 export OPENAI_API_KEY（或 AX_LLM_API_KEY / LITELLM_API_KEY）}"

PANEL="${PANEL:-artifacts/panel/panel_1d.parquet}"
LABEL_COL="${LABEL_COL:-label_10d_close_to_close}"
LANES="${LANES:-momentum,volatility,volume,weekly}"
MAX_PARALLEL_EVAL="${MAX_PARALLEL_EVAL:-4}"   # 每进程并行 eval 数（多个进程共用 8 核，别都设满）
MAX_TOOL_WORKERS="${MAX_TOOL_WORKERS:-4}"
MAX_TURNS="${MAX_TURNS:-5}"
NO_SUBMIT="${NO_SUBMIT:-0}"
LOG_ROOT="${LOG_ROOT:-logs/factor_mining}"

if [[ ! -f "$PANEL" ]]; then
  echo "错误：找不到 Panel: $PANEL" >&2
  exit 1
fi

printf 'LiteLLM base : %s\n' "$OPENAI_API_BASE"
printf 'MODEL        : %s\n' "$MODEL"
printf 'PANEL        : %s\n' "$PANEL"
printf 'LABEL_COL    : %s\n' "$LABEL_COL"
printf 'LANES        : %s\n' "$LANES"
printf 'per-proc eval/workers: %s/%s\n' "$MAX_PARALLEL_EVAL" "$MAX_TOOL_WORKERS"

if command -v uv >/dev/null 2>&1; then
  PY=(uv run python)
else
  PY=(python)
  echo "提示: 未找到 uv，使用 $(command -v python)（请确认已 conda activate 且装好 mining 依赖）" >&2
fi

SCRIPT=scripts/factor_mining_agentscope.py
mkdir -p "$LOG_ROOT"

# 基础参数（所有进程共享）
declare -a BASE
BASE=(--panel "$PANEL" --label-col "$LABEL_COL" --max-turns "$MAX_TURNS")
if [[ "$NO_SUBMIT" == "1" ]]; then
  BASE+=(--no-submit)
fi

IFS=',' read -ra LANE_LIST <<< "$LANES"
PIDS=()
declare -A PID_LANE
for lane in "${LANE_LIST[@]}"; do
  lane="$(echo "$lane" | xargs)"   # 去空格
  [[ -z "$lane" ]] && continue
  logdir="$LOG_ROOT/$lane"
  mkdir -p "$logdir"
  echo "[launch] $lane  ->  log=$logdir  (pid-file=$$)"
  "${PY[@]}" "$SCRIPT" \
    "${BASE[@]}" \
    --mine-lane "$lane" \
    --max-parallel-eval "$MAX_PARALLEL_EVAL" \
    --max-tool-workers "$MAX_TOOL_WORKERS" \
    --log-dir "$logdir" \
    >"$logdir/cli.log" 2>&1 &
  PID=$!
  PIDS+=("$PID")
  PID_LANE[$PID]="$lane"
  echo "  started pid=$PID"
done

echo
echo "已启动 ${#PIDS[@]} 个挖掘进程。Ctrl-C 结束本轮；日志见 $LOG_ROOT/<lane>/cli.log"
echo "----------------------------------------"

FAIL=0
for PID in "${PIDS[@]}"; do
  if wait "$PID"; then
    echo "[ok] $PID  ${PID_LANE[$PID]}  完成"
  else
    echo "[FAIL] $PID  ${PID_LANE[$PID]}  退出码=$?"
    FAIL=1
  fi
done

echo "----------------------------------------"
if [[ "$FAIL" == "0" ]]; then
  echo "全部 lane 完成。"
else
  echo "存在失败 lane，请查看对应 $LOG_ROOT/<lane>/cli.log"
  exit 1
fi