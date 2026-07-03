# Data pipeline & open-data release

> Two-stage design: **fetch (online) → build panel (offline)**. Panel construction
> never touches Tushare. Market data is fetched into a raw hq cache, then the panel
> is built/updated offline from that cache. This mirrors the fundamentals flow.

## Architecture

```
Stage 1 — fetch (online)              Raw parquet caches            Stage 2 — build panel (offline)
scripts/fetch_market.py        ->  artifacts/market/daily_hq.parquet   ┐
                                   artifacts/index/<code>_members...    │
scripts/fetch_fundamentals.py  ->  artifacts/fundamental/quarterly...  │-> scripts/build_panel.py
                                   artifacts/fundamental/disclosure...  │   -> artifacts/panel/panel_1d.parquet
build_panel --with-industry    ->  artifacts/industry/sw_l1_membership ┘

Incremental: scripts/update_panel.py
  = update_market_cache (append hq) + update_panel_from_hq (tail-merge + re-derive)
```

- `seekalpha/data/market_fetch.py` — all Tushare fetching + hq cache IO + `fetch_and_save_market` (full) / `update_market_cache` (incremental).
- `seekalpha/data/index_members.py` — index constituents cached as monthly snapshots under `artifacts/index/`. Used only at fetch time to decide which stocks to pull; reused on same-range re-fetch (`--refresh-members` to force re-pull). The offline panel build does not depend on it.
- `seekalpha/data/panel.py` — offline only: `build_panel` (from hq cache) and `update_panel_from_hq` (incremental). No Tushare import at call time.

## Full build (with token)

```bash
# 1. fetch raw market hq into artifacts/market/daily_hq.parquet
uv run python scripts/fetch_market.py --start 2015-01-01 --end 2026-06-30 --universe zz1000
# 2. fetch quarterly fundamentals + disclosure calendar
uv run python scripts/fetch_fundamentals.py --start 2015-01-01 --end 2026-12-31 --with-statements
# 3. build the panel offline (also caches SW L1 industry on first run)
uv run python scripts/build_panel.py --with-fundamentals --with-industry
```

## Incremental update

```bash
uv run python scripts/update_panel.py --universe zz1000 --with-fundamentals --with-industry
```

Step 1 appends new trade dates to `daily_hq.parquet`; step 2 tail-merges the new
rows into the panel and re-derives `ret`/`label_*` from the trading day before the gap.

## Packaging for open-data distribution

```bash
uv run python scripts/pack_data_release.py --zip
```

Produces `dist/alphaagent-data-<date>/` (mirroring `artifacts/`) with the four raw
caches, plus `MANIFEST.json` (sha256) and a bilingual `README.md`. Upload the folder
or zip to your file host (Baidu Cloud, etc.). The factor library (`artifacts/factorzoo`)
is not packaged; rebuild it via `scripts/ingest_factors.py`.

## Restore (consumer side, offline)

1. Extract the package into the repo root so `artifacts/market|fundamental|industry` are populated.
2. `uv run python scripts/build_panel.py --with-fundamentals --with-industry`
3. Optionally verify file sha256 against `MANIFEST.json`.

---

# 数据管线与开源数据发布（中文）

> 两段式：**拉取（联网）→ 建 panel（离线）**。panel 构建全程不联网——行情先拉进
> hq 缓存，再从缓存离线构建/更新 panel，与基本面流程对称。

## 架构

- `seekalpha/data/market_fetch.py`：所有 Tushare 抓取 + hq 缓存读写 + `fetch_and_save_market`（全量）/ `update_market_cache`（增量）。
- `seekalpha/data/panel.py`：纯离线，`build_panel`（读 hq 缓存）与 `update_panel_from_hq`（增量）。

## 全量构建（需 token）

```bash
# 1. 拉行情 → artifacts/market/daily_hq.parquet
uv run python scripts/fetch_market.py --start 2015-01-01 --end 2026-06-30 --universe zz1000
# 2. 拉季频基本面 + 披露日历
uv run python scripts/fetch_fundamentals.py --start 2015-01-01 --end 2026-12-31 --with-statements
# 3. 离线建 panel（首次会顺带缓存申万一级行业）
uv run python scripts/build_panel.py --with-fundamentals --with-industry
```

## 增量更新

```bash
uv run python scripts/update_panel.py --universe zz1000 --with-fundamentals --with-industry
```

步骤 1 把新交易日追加进 `daily_hq.parquet`；步骤 2 把新增行 merge 进 panel，并从缺口
前一交易日起重算 `ret`/`label_*`。

## 打包发布

```bash
uv run python scripts/pack_data_release.py --zip
```

生成 `dist/alphaagent-data-<日期>/`（对齐 `artifacts/` 布局），含四个原始缓存 +
`MANIFEST.json`（sha256）+ 双语 README。把目录或 zip 上传到网盘（百度云等）即可。
因子库（`artifacts/factorzoo`）不打包，用 `scripts/ingest_factors.py` 重建。

## 重构（使用方，离线）

1. 解压到仓库根，使 `artifacts/market|fundamental|industry` 就位。
2. `uv run python scripts/build_panel.py --with-fundamentals --with-industry`
3. （可选）用 `MANIFEST.json` 的 sha256 校验。
