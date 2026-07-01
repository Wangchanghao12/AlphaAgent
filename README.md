# SeekAlpha



多因子策略研究 + 实盘框架



## 快速开始



```bash

# 安装依赖（需 uv）

uv sync



# 配置 Tushare Token（项目根目录 .env）

# TUSHARE_TOKEN=your_token



# 构建 ZZ1000 Panel（默认 universe=zz1000，成分并集 + 批量拉取）

uv run python scripts/build_panel.py --start 2024-01-01 --end 2024-12-31



# 全市场按日拉取（较慢）

uv run python scripts/build_panel.py --start 2024-01-01 --end 2024-01-31 --universe none



# 增量更新

uv run python scripts/build_panel.py --update

```



## 目录结构



```

seekalpha/

  core/       # 类型、配置、路径

  data/       # Tushare + Panel parquet

  dsl/        # 因子 DSL（来自 AlphaAgent-Stock）

  factor/     # 评估、入库、factorzoo

scripts/      # CLI 入口

configs/      # YAML / registry 配置

artifacts/    # 运行时产物（panel、factorzoo、bundle）

tests/        # 分层单测

```



## Panel 存储



- 历史全量：`artifacts/panel/panel_1d.parquet`

- 实盘增量：`scripts/build_panel.py --update`（检测 panel 内全部缺失日，按股票池批量回填，与全量 build 相同拉数方式）

- Schema 与 AlphaAgent-Stock 一致，研究/实盘共用



## 因子库（factorzoo）



```bash

# 1. 构建 panel（若尚未有）

uv run python scripts/build_panel.py --start 2024-01-01 --end 2024-12-31



# 2. 初始化因子库（绑定 panel 行索引）

uv run python scripts/init_factorlib.py



# 3. 单因子 IC 报告（全量 panel 求值，--start-time 仅切 metrics）
uv run python scripts/eval_factor.py --expr-file examples/factors/ma_dev.dsl --report

# 4. 批量入库
uv run python scripts/ingest_factors.py --registry configs/factors/registry.example.json

# 5. 查看 catalog
uv run python scripts/factorlib_info.py
```

指标说明见 [docs/factor_metrics.md](docs/factor_metrics.md)。



## 因子挖掘（可选）



```bash

uv sync --extra mining

# 配置 OPENAI_API_KEY / OPENAI_API_BASE / MODEL（.env）

uv run python scripts/factor_mining.py --panel artifacts/panel/panel_1d.parquet

```



## 测试



```bash

uv run pytest tests/ -q

```


