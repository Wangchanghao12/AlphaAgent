MAX_PARALLEL_EVAL=4 MAX_TOOL_WORKERS=4 MAX_TURNS=8 \
bash scripts/run_factor_mining_parallel.sh \
  --lanes momentum,volatility,volume,weekly,fundamental,microstructure >> log/run_factor_mining_parallel.log 2>&1 &
