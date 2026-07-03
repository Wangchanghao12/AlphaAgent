# AlphaAgent 开发记录

> 截至 2026-07-02。统一 monorepo `alphaagent`：Tushare 数据源 + AlphaAgent DSL + FactorZoo，目标覆盖因子研究 → 模型 → 回测 → 实盘。

---

## 已完成

### 基础框架（Phase 1）

- `alphaagent` 包骨架：`core` / `data` / `dsl`
- DSL 从 AlphaAgent-Stock 迁移，表达式求值可用
- Panel 全量构建 + 增量更新（parquet，`--update` 自动补 gap、回填 ret/label）
- Tushare 客户端（`.env` token、重试/超时）
- 分层单测：`test_core` / `test_data` / `test_dsl`

### 数据层

- ZZ1000 成分股：`index_weight` 按月并集（~2696 只，非仅当前 1000 只）
- ST：`stock_st` 日度 `is_st`；`float_cap`：按 `trade_date` 拉 `daily_basic`
- 复权：`adj_* = OHLC × adjfactor`，新增 `adj_vwap`；建议 `--batch-size 20` 避免 6000 行截断
- 当前 Panel：~618 万行 × 20 列，2015-01 ~ 2026-06，与 `pro_bar(hfq)` 在 2 位小数内一致

### 季频基本面（PIT）

- `fetch_fundamentals.py`：`fina_indicator` / `fina_indicator_vip` 拉全市场季频 → `artifacts/fundamental/`
- `fundamental.py`：披露日 T+1 生效 PIT 展开（port AlphaAgent）、披露距离特征
- `build_panel.py`：`--with-fundamentals` / `--enrich-only` 并入 panel
- 当前字段：`funda_roe`、`funda_netprofit_yoy`、`funda_fs_ebit` 等 17 指标 + 2 披露日历列
- 挖掘 prompt 已文档化 `$funda_*` 用法；单测 `test_fundamental_pit` / `test_fundamental_fetch`

### 因子研究（Phase 2）

- 评估/入库从 AlphaAgent 迁移：`eval`、`metrics`、`report`、FactorZoo、`ingest`
- CLI：`eval_factor.py`（IC 报告）、`ingest_factors.py`（`--expr-file` / registry）、`init_factorlib.py`、`realign_factorlib.py`
- 默认 label：`label_1d_open_to_open`
- 因子库：memmap 存储 + 截面查重；panel 变更后 `realign` 重算已有因子
- T+N 窗口增量更新（T=240 天 + 新窗口，overlap 一致性已测）
- 文档：`docs/factor_metrics.md`
- 单测：`test_factor`（含 rolling probe）

### 可选

- LLM 因子挖掘：`scripts/factor_mining.py`
- Panel 复权修补：`scripts/repair_panel_adjfactor.py`（rebuild 后通常不需要）

---

## 规划（待办）

### Phase 3 — 模型 + 回测

- [ ] `alphaagent/model/`：dataset、walk-forward 训练（Linear / LightGBM）
- [ ] `alphaagent/portfolio/`：alpha → 目标持仓
- [ ] `alphaagent/backtest/`：朴素逐日回测引擎（与 live 共用 portfolio 逻辑）
- [ ] `scripts/train_model.py`、`scripts/backtest.py`
- [ ] YAML 驱动策略配置（`configs/strategies/`）
- [ ] StrategyBundle 版本化（`artifacts/bundles/`）
- [ ] `test_model` / `test_portfolio` / `test_backtest`

### Phase 4 — 实盘

- [ ] `alphaagent/live/`：inference、reconciler（目标 vs 持仓 → 订单）
- [ ] `alphaagent/exec/qmt/`：精简 QMT adapter
- [ ] `alphaagent/risk/`、`alphaagent/monitor/`
- [ ] `scripts/run_live.py`
- [ ] `test_live` / `test_exec` / `test_integration` 全链路

### Phase 5 — 优化（可选）

- [ ] 三大表全量 `funda_fs_*` 科目（income/balancesheet/cashflow）
- [ ] `daily_basic` 扩展 PE/PB 等日频估值列
- [ ] 回测性能：预计算 alpha 表、向量化 PnL
- [ ] 时点成分股 mask（回测/实盘过滤当日 zz1000）
- [ ] Panel 原子写入、断点续传 build
- [ ] adjfactor merge 彻底清零（单股补拉 + ffill/bfill）

---

## 已知遗留（低优先级）

- ~3% 行 `adjfactor=1.0`（新股初期正常 + 少量 merge 遗漏）
- `vwap` 单位：amount 千元 / volume 手（与 close 差 10 倍，可用 `$adj_vwap`）
- 无「当日成分股」过滤，信号层需自行处理
