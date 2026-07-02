# SeekAlpha

多因子策略研究框架（Tushare 数据 + DSL 因子 + FactorZoo + 可选 LLM 挖掘）。

**完整操作手册**：[docs/operations_manual.md](docs/operations_manual.md)

## 新人上手（最小路径）

```powershell
# 1. 依赖
uv sync

# 2. 环境变量
copy .env.example .env
# 编辑 .env：至少填 TUSHARE_TOKEN

# 3. 构建 Panel（本地生成，不入 Git）
uv run python scripts/build_panel.py --start 2024-01-01 --end 2024-12-31

# 可选：季频基本面（先 fetch，再 enrich；或 --with-fundamentals 一步完成）
uv run python scripts/fetch_fundamentals.py --start 2015-01-01 --end 2026-12-31
uv run python scripts/build_panel.py --enrich-only

# 4. 初始化因子库 + 从 Git 里的 .dsl 重建 memmap
uv run python scripts/init_factorlib.py
uv run python scripts/ingest_factors.py --expr-dir artifacts/factorzoo/stock_1d/expressions

# 5. 验证
uv run python scripts/factorlib_info.py
uv run python scripts/eval_factor.py --expr-file artifacts/factorzoo/stock_1d/expressions/idio_qspread_win_20.dsl --report
```

> Panel（~600 万行 parquet）和 factorzoo memmap **不在 Git 里**；协作者 clone 后需本地 build panel + `ingest --expr-dir` 重建数值库。

## 因子 Git 同步（团队）

| 操作 | 命令 |
|------|------|
| 入库后导出 DSL | `uv run python scripts/sync_factor_exprs.py` |
| 提交 | `git add artifacts/factorzoo/stock_1d/expressions/*.dsl` |
| 拉取后重建 memmap | `uv run python scripts/ingest_factors.py --expr-dir artifacts/factorzoo/stock_1d/expressions --overwrite` |

**`--label-col` 选用**：基本面因子 → `label_10d_close_to_close`；价量因子 → `label_1d_close_to_close`。

```powershell
# 基本面
uv run python scripts/eval_factor.py --expr-file your.dsl --report --label-col label_10d_close_to_close
# 价量
uv run python scripts/eval_factor.py --expr-file your.dsl --report --label-col label_1d_close_to_close
```

## 因子挖掘（可选）

```powershell
uv sync --extra mining
# .env 填 OPENAI_API_KEY、MODEL
# Panel 需含 funda_* 列（build_panel --enrich-only 或 --with-fundamentals）

# 基本面挖掘
uv run python scripts/factor_mining_agentscope.py --panel artifacts/panel/panel_1d.parquet --label-col label_10d_close_to_close

# 价量挖掘
uv run python scripts/factor_mining_agentscope.py --panel artifacts/panel/panel_1d.parquet --label-col label_1d_close_to_close
```

## 测试

```powershell
uv run pytest tests/ -q
```

## 目录

```
seekalpha/     # 核心包
scripts/       # CLI
artifacts/     # panel、fundamental、factorzoo（仅 expressions/*.dsl 入 Git）
docs/          # 操作手册、指标说明
```
