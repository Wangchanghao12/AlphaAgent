# AlphaAgent

A multi-factor equity research framework for China A-shares: build a daily panel from Tushare (or pre-packaged parquet caches), express factors in DSL (domain-specific language), evaluate them in **FactorZoo**, and optionally mine new factors with LLMs.

> **AlphaAgent** 是一套面向 A 股的多因子研究框架：从 Tushare（或开源数据包）构建日频 panel，用 DSL 表达因子，在 FactorZoo 中评估，并可选 LLM 辅助挖掘。

## What it does

| Layer | Description |
|-------|-------------|
| **Data** | Two-stage pipeline — fetch raw caches (market / fundamentals / industry) online, then build or update the panel **offline** |
| **Factors** | DSL expressions → memmap factor library; IC / turnover / quantile reports via `eval_factor.py` |
| **Mining** | Optional AgentScope agents propose and iterate on factor expressions (`factor_mining_agentscope.py`) |

Universe in the reference dataset: **CSI 1000 (ZZ1000)** constituent union, 2015-01 ~ 2026-06, ~2,757 stocks, ~6.2M panel rows.

Panel and large binaries are **not in Git**. Clone the repo, then either pull data with a Tushare token or restore the [open data package](docs/data_release.md) and rebuild offline.

## Quick start

```powershell
uv sync
copy .env.example .env   # set TUSHARE_TOKEN (only needed for Option B below)

# Get the data — see "Data preparation": download the open package, OR:
uv run python scripts/fetch_market.py --start 2015-01-01 --end 2026-06-30 --universe zz1000
uv run python scripts/fetch_fundamentals.py --start 2015-01-01 --end 2026-12-31

# Build the panel offline, then rebuild the factor library and evaluate a factor
uv run python scripts/build_panel.py --with-fundamentals --with-industry
uv run python scripts/init_factorlib.py
uv run python scripts/ingest_factors.py --expr-dir artifacts/factorzoo/stock_1d/expressions
uv run python scripts/eval_factor.py --expr-file artifacts/factorzoo/stock_1d/expressions/idio_qspread_win_20.dsl --report
```

Incremental updates: `uv run python scripts/update_panel.py --universe zz1000 --with-fundamentals --with-industry`

## Data preparation

The panel and raw caches are **not tracked in Git**. Choose one of the two options below.

### Option A — download the open data package (no Tushare token)

Pre-built raw parquet caches (CSI 1000 union, 2015-01 ~ 2026-06):

- **Baidu Netdisk**: <https://pan.baidu.com/s/1GsCl6McyoHyws5bl571HqQ?pwd=5qp5> (code: `5qp5`)
- File: `alphaagent-data-20260703.zip`

```powershell
# 1. Extract the zip into the repo root, so that these folders are populated:
#    artifacts/market, artifacts/fundamental, artifacts/industry, artifacts/index
# 2. Rebuild the panel offline (reads local caches only, no network):
uv run python scripts/build_panel.py --with-fundamentals --with-industry
# 3. Rebuild the factor library from Git-tracked DSL:
uv run python scripts/init_factorlib.py
uv run python scripts/ingest_factors.py --expr-dir artifacts/factorzoo/stock_1d/expressions
```

The package ships a `MANIFEST.json` (sha256) for integrity checks. See
[docs/data_release.md](docs/data_release.md) for the full layout.

### Option B — fetch from Tushare yourself (needs token)

Set `TUSHARE_TOKEN` in `.env`, then run the fetch + build commands shown in
[Quick start](#quick-start).

## Documentation

| Doc | Topic |
|-----|-------|
| [docs/operations_manual.md](docs/operations_manual.md) | Full workflow (中文) |
| [docs/data_release.md](docs/data_release.md) | Open data package layout & restore |
| [docs/panel_fundamental_fields.md](docs/panel_fundamental_fields.md) | Panel fundamental columns |
| [docs/factor_metrics.md](docs/factor_metrics.md) | Factor evaluation metrics |

## Factor sync (team)

| Action | Command |
|--------|---------|
| Export DSL after ingest | `uv run python scripts/sync_factor_exprs.py` |
| Commit | `git add artifacts/factorzoo/stock_1d/expressions/*.dsl` |
| Rebuild memmap after pull | `uv run python scripts/ingest_factors.py --expr-dir artifacts/factorzoo/stock_1d/expressions --overwrite` |

**Label column**: fundamentals → `label_10d_close_to_close`; price/volume → `label_1d_close_to_close`.

## Factor mining (optional)

```powershell
uv sync --extra mining
# .env: OPENAI_API_KEY, MODEL

uv run python scripts/factor_mining_agentscope.py --panel artifacts/panel/panel_1d.parquet --label-col label_10d_close_to_close
```

## Tests

```powershell
uv run pytest tests/ -q
```

## Layout

```
seekalpha/     # core package (data, factor, mining, …)
scripts/       # CLI entry points
artifacts/     # local data & factorzoo (only expressions/*.dsl tracked in Git)
docs/          # manuals
```

## License & data

Code in this repository is open source. Market and fundamental data are derived from [Tushare Pro](https://tushare.pro); redistribution of the data package must comply with Tushare's terms. Research use only.

---
