#!/usr/bin/env bash
# 因子挖掘启动脚本：经 LiteLLM（OpenAI 兼容）接入模型。
# 参考 yd_recom_agentx/agentx_strategy/run_strategy_agent.sh 的网关配置方式。
#
# 用法（仓库根目录）：
#   export OPENAI_API_KEY=sk-xxxx          # 或 AX_LLM_API_KEY / LITELLM_API_KEY
#   bash scripts/run_factor_mining.sh
#   bash scripts/run_factor_mining.sh --no-submit --max-turns 2
#
# 前置：
#   1. 依赖：uv sync --extra mining，或 conda 环境已装 mining 依赖（openai/agentscope 等）
#   2. artifacts/panel/panel_1d.parquet 已存在（开源包离线 build，或 Tushare 拉数）
#   3. 若要 submit_factor：先 init_factorlib + ingest_factors --expr-dir ...
# 启动器：优先 uv run；无 uv 时用当前 PATH 的 python（conda 可先 conda activate）
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

# LiteLLM 网关（与 agentx 同机房默认一致；可被环境变量覆盖）
export OPENAI_API_BASE="${OPENAI_API_BASE:-${AX_LLM_BASE_URL:-https://litellm.spaccez.com/v1}}"
export MODEL="${MODEL:-${AX_LLM_MODEL:-deepseek-v4-flash}}"

# key 优先级：OPENAI_API_KEY → AX_LLM_API_KEY → LITELLM_API_KEY
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  if [[ -n "${AX_LLM_API_KEY:-}" ]]; then
    export OPENAI_API_KEY="$AX_LLM_API_KEY"
  elif [[ -n "${LITELLM_API_KEY:-}" ]]; then
    export OPENAI_API_KEY="$LITELLM_API_KEY"
  fi
fi
: "${OPENAI_API_KEY:?请先 export OPENAI_API_KEY（或 AX_LLM_API_KEY / LITELLM_API_KEY）}"

# 可选并行评估
export MAX_PARALLEL_EVAL="${MAX_PARALLEL_EVAL:-8}"

PANEL="${PANEL:-artifacts/panel/panel_1d.parquet}"
LABEL_COL="${LABEL_COL:-label_10d_close_to_close}"
BACKEND="${AA_MINING_BACKEND:-agentscope}"   # agentscope | openai

if [[ ! -f "$PANEL" ]]; then
  cat >&2 <<EOF
错误：找不到 Panel：$PANEL

挖因子不直接调 Tushare，但必须先有 panel。二选一：
  A) 下载开源包（无需 token）→ 解压到仓库根 → build_panel
     见 README「Data preparation / Option A」
  B) 配置 TUSHARE_TOKEN 后 fetch_market / fetch_fundamentals → build_panel
     见 README「Option B」
EOF
  exit 1
fi

echo "LiteLLM base : $OPENAI_API_BASE"
echo "MODEL        : $MODEL"
echo "PANEL        : $PANEL"
echo "LABEL_COL    : $LABEL_COL"
echo "BACKEND      : $BACKEND"

if [[ "$BACKEND" == "openai" ]]; then
  SCRIPT=scripts/factor_mining.py
else
  SCRIPT=scripts/factor_mining_agentscope.py
fi

if command -v uv >/dev/null 2>&1; then
  PY=(uv run python)
else
  PY=(python)
  echo "提示: 未找到 uv，使用 $(command -v python)（请确认已 conda activate 且装好 mining 依赖）" >&2
fi

exec "${PY[@]}" "$SCRIPT" \
  --panel "$PANEL" \
  --label-col "$LABEL_COL" \
  "$@"
