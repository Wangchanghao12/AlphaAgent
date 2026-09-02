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
# 可选环境变量：MAX_TURNS（默认 8）、RETRY_ATTEMPTS（单 lane 失败重试次数，默认 3）。
# 日志：logs/factor_mining/<lane>/cli_<时间戳>.log（每次启动一份，不覆盖历史）。
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
TRAIN_START="${TRAIN_START:-2019-01-01}"
TRAIN_END="${TRAIN_END:-2021-12-31}"
VAL_START="${VAL_START:-2022-01-01}"
VAL_END="${VAL_END:-2024-12-31}"
HOLDOUT_START="${HOLDOUT_START:-2025-01-01}"
HOLDOUT_END="${HOLDOUT_END:-2026-07-31}"
LANES="${LANES:-momentum,volatility,volume,weekly}"
MAX_PARALLEL_EVAL="${MAX_PARALLEL_EVAL:-4}"   # 每进程并行 eval 数（多个进程共用 8 核，别都设满）
MAX_TOOL_WORKERS="${MAX_TOOL_WORKERS:-4}"
MAX_TURNS="${MAX_TURNS:-8}"
RETRY_ATTEMPTS="${RETRY_ATTEMPTS:-3}"
NO_SUBMIT="${NO_SUBMIT:-0}"
LOG_ROOT="${LOG_ROOT:-logs/factor_mining}"

# 命令行 flag（覆盖环境变量默认值）
while [[ $# -gt 0 ]]; do
  case "$1" in
    --lanes)     LANES="${2:?--lanes 需要参数，如 momentum,volume}"; shift 2 ;;
    --max-turns) MAX_TURNS="${2:?--max-turns 需要参数}"; shift 2 ;;
    --panel)     PANEL="${2:?--panel 需要参数}"; shift 2 ;;
    --label-col) LABEL_COL="${2:?--label-col 需要参数}"; shift 2 ;;
    --train-start) TRAIN_START="${2:?--train-start 需要参数}"; shift 2 ;;
    --train-end) TRAIN_END="${2:?--train-end 需要参数}"; shift 2 ;;
    --val-start) VAL_START="${2:?--val-start 需要参数}"; shift 2 ;;
    --val-end) VAL_END="${2:?--val-end 需要参数}"; shift 2 ;;
    --holdout-start) HOLDOUT_START="${2:?--holdout-start 需要参数}"; shift 2 ;;
    --holdout-end) HOLDOUT_END="${2:?--holdout-end 需要参数}"; shift 2 ;;
    --no-submit) NO_SUBMIT=1; shift ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

if [[ ! -f "$PANEL" ]]; then
  echo "错误：找不到 Panel: $PANEL" >&2
  exit 1
fi

printf 'LiteLLM base : %s\n' "$OPENAI_API_BASE"
printf 'MODEL        : %s\n' "$MODEL"
printf 'PANEL        : %s\n' "$PANEL"
printf 'LABEL_COL    : %s\n' "$LABEL_COL"
printf 'WINDOWS      : train=%s~%s val=%s~%s holdout=%s~%s\n' \
  "$TRAIN_START" "$TRAIN_END" "$VAL_START" "$VAL_END" "$HOLDOUT_START" "$HOLDOUT_END"
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

# 单 lane 执行器：失败自动重试（LLM 网关抖动等），日志追写到同一份带时间戳文件
run_lane() {
  local lane="$1" logfile="$2"
  shift 2
  local attempt=1 rc=0
  while (( attempt <= RETRY_ATTEMPTS )); do
    echo "[attempt $attempt/$RETRY_ATTEMPTS] $(date '+%F %T')" >> "$logfile"
    rc=0
    "${PY[@]}" "$SCRIPT" "$@" >> "$logfile" 2>&1 || rc=$?
    if (( rc == 0 )); then
      return 0
    fi
    echo "[retry] lane=$lane attempt=$attempt exit=$rc" >> "$logfile"
    if (( attempt < RETRY_ATTEMPTS )); then
      sleep 10
    fi
    attempt=$((attempt + 1))
  done
  return "$rc"
}

# 基础参数（所有进程共享）
declare -a BASE
BASE=(
  --panel "$PANEL" --label-col "$LABEL_COL" --max-turns "$MAX_TURNS"
  --train-start "$TRAIN_START" --train-end "$TRAIN_END"
  --val-start "$VAL_START" --val-end "$VAL_END"
  --holdout-start "$HOLDOUT_START" --holdout-end "$HOLDOUT_END"
)
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
  logfile="$logdir/cli_$(date +%Y%m%d_%H%M%S).log"
  echo "[launch] $lane  ->  log=$logfile"
  run_lane "$lane" "$logfile" \
    "${BASE[@]}" \
    --mine-lane "$lane" \
    --max-parallel-eval "$MAX_PARALLEL_EVAL" \
    --max-tool-workers "$MAX_TOOL_WORKERS" \
    --log-dir "$logdir" &
  PID=$!
  PIDS+=("$PID")
  PID_LANE[$PID]="$lane"
  echo "  started pid=$PID"
done

echo
echo "已启动 ${#PIDS[@]} 个挖掘进程。Ctrl-C 结束本轮；日志见 $LOG_ROOT/<lane>/cli_<时间戳>.log"
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
  echo "存在失败 lane（已重试 $RETRY_ATTEMPTS 次），请查看对应 $LOG_ROOT/<lane>/cli_*.log"
  exit 1
fi