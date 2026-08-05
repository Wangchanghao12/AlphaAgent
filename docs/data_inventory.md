# 数据下载与产物清单

> 本文记录本机 / 服务器上 **已拉取、已构建** 的数据资产（以 2026-08 前后一轮搭建为准）。  
> 命令均在仓库根目录执行；服务器路径示例：`/mnt/recom/develop/wangchanghao/rtp_fg/AlphaAgent`。

---

## 1. 总览

| 层级 | 产物 | 来源 | 状态（本轮） |
|------|------|------|----------------|
| 行情缓存 | `artifacts/market/daily_hq.parquet` | Tushare `daily` / `daily_basic` / `adj_factor` 等 | 已拉（约 2018～2026） |
| 基本面缓存 | `artifacts/fundamental/quarterly.parquet` | Tushare `fina_indicator`（`--no-vip`） | 已拉（约 2022Q1～2026H1） |
| 披露日历 | `artifacts/fundamental/disclosure_calendar.parquet` | 随基本面一并写入 | 已有 |
| 行业缓存 | `artifacts/industry/sw_l1_membership.parquet` | 申万一级；`index_member` 空时回退 `index_member_all` | 已有 |
| 日频 Panel | `artifacts/panel/panel_1d.parquet` | hq 离线构建 + funda/industry enrich | 已建（约 922 万行 × 55 列） |
| 因子库 | `artifacts/factorzoo/stock_1d/` | `init_factorlib` + 示例 ingest | 已初始化（非下载） |

**未拉 / 刻意跳过：**

| 项 | 说明 |
|----|------|
| 三大表 `income` / `balancesheet` / `cashflow` | `--with-statements`；`--no-vip` 下过慢，本轮未落地 |
| 2018～2021 基本面 | 为赶一天 token，区间缩到约 2022 起 |
| VIP 全市场 `fina_indicator_vip` | 当前 token 无 VIP，改用 `--universe zz1000 --no-vip` |

---

## 2. 行情（Market HQ）

| 项 | 内容 |
|----|------|
| 脚本 | `scripts/fetch_market.py` |
| 输出 | `artifacts/market/daily_hq.parquet`（可选分片 `daily_hq_parts/`） |
| Universe | 中证 1000（`zz1000`）历史成分并集 |
| 大致区间 | **2018-01-01 ～ 2026-07**（末期个别交易日可能有缺口） |
| 主要内容 | OHLCV、复权因子、市值、ST、`daily_basic`（换手 / PE/PB 等） |

校验：

```bash
python scripts/check_market_hq.py
# 或
python -c "
from alphaagent.data.market_fetch import load_market_hq
hq = load_market_hq()
print(hq.shape, hq.index.get_level_values(0).min(), hq.index.get_level_values(0).max())
"
```

增量补缺：`scripts/update_panel.py` / `scripts/compact_market_hq.py --gaps`。

---

## 3. 基本面（Fundamentals）

| 项 | 内容 |
|----|------|
| 脚本 | `scripts/fetch_fundamentals.py` |
| 输出 | `artifacts/fundamental/quarterly.parquet`、`disclosure_calendar.parquet` |
| 模式 | `--universe zz1000 --no-vip`（逐股） |
| 接口 | `fina_indicator`（**不含**三大表） |
| 报告期 | 约 **20220331 ～ 20260630**（曾确认至少 15 期已落盘；续跑可补齐末几期） |
| 成分规模 | zz1000 历史并集，约 **1800～2400** 只（随 `--start/--end` 变化） |

本轮典型命令：

```bash
PYTHONUNBUFFERED=1 python -u scripts/fetch_fundamentals.py \
  --start 2022-01-01 --end 2026-07-31 \
  --universe zz1000 --no-vip
```

查看已缓存报告期：

```bash
python -c "
import pandas as pd
q = pd.read_parquet('artifacts/fundamental/quarterly.parquet')
ends = sorted(pd.to_datetime(q.index.get_level_values('report_end')).unique())
print('periods', len(ends), 'rows', len(q))
print([d.strftime('%Y%m%d') for d in ends])
"
```

续跑：已缓存报告期会跳过；缺期可用 `--periods YYYYMMDD ...` 补拉。

Panel 内基本面列（enrich 后约 19 个，前缀 `funda_`），例如：

`funda_roe`、`funda_roa`、`funda_eps`、`funda_bps`、`funda_debt_to_assets`、`funda_netprofit_yoy`、`funda_or_yoy`、`funda_grossprofit_margin`、`funda_current_ratio`、`funda_fs_ebit`、`funda_fs_rd_exp`、`funda_days_since_disclose`、`funda_days_since_quarter_start` 等。

详见 [panel_fundamental_fields.md](./panel_fundamental_fields.md)。

---

## 4. 行业（Industry）

| 项 | 内容 |
|----|------|
| 触发 | `build_panel.py --with-industry`（可选 `--refresh-industry` 强制重拉） |
| 缓存 | `artifacts/industry/sw_l1_membership.parquet` |
| 内容 | 申万一级行业成员；Panel 列 **`industry_sw_l1`** |
| 拉取备注 | `index_member` 无数据时回退 `index_member_all`（约 32 个一级行业） |

有缓存时不要加 `--refresh-industry`，否则会重新打 Tushare。

---

## 5. Panel（离线构建）

| 项 | 内容 |
|----|------|
| 脚本 | `scripts/build_panel.py` |
| 输出 | `artifacts/panel/panel_1d.parquet` |
| 本轮规模 | 约 **9,223,691 行 × 55 列**（enrich 后） |
| 量价列 | `adj_*`、`ret`、`volume`、`float_cap` 等 |
| Label | `label_1d_open_to_open`、`label_*d_close_to_close` 等 |
| Enrich | `--enrich-only --with-fundamentals --with-industry` |

确认列：

```bash
python -c "
import pandas as pd
p = pd.read_parquet('artifacts/panel/panel_1d.parquet')
print('shape', p.shape)
print('funda', sum(c.startswith('funda_') for c in p.columns))
print('industry', 'industry_sw_l1' in p.columns)
print('labels', [c for c in p.columns if str(c).startswith('label_')])
"
```

---

## 6. 因子库（非下载，本地构建）

| 项 | 内容 |
|----|------|
| 路径 | `artifacts/factorzoo/stock_1d/` |
| 初始化 | `scripts/init_factorlib.py` |
| 示例入库 | `ma20_dev`、`ma_dev`、`mom_vol`；另有 `amihud_log_30d_winsor` 等 |
| 查看 | `python scripts/factorlib_info.py` |

挖掘产出另写 `expressions/*.dsl` 与 `mining_delivered_registry.json`（仅 `submit` 成功才落库）。

---

## 7. 数据流（本轮实际路径）

```text
Tushare
  ├─ fetch_market.py          → artifacts/market/daily_hq.parquet
  ├─ fetch_fundamentals.py    → artifacts/fundamental/{quarterly,disclosure_calendar}.parquet
  └─ build_panel --with-industry → artifacts/industry/sw_l1_membership.parquet
         │
         ▼
build_panel.py（离线）
         │
         ▼
artifacts/panel/panel_1d.parquet
  （量价 + label + funda_* + industry_sw_l1）
         │
         ▼
init_factorlib / ingest / factor_mining
```

---

## 8. 若需补全

| 目标 | 建议命令 |
|------|----------|
| 补基本面末几期 | `fetch_fundamentals.py --periods ... --universe zz1000 --no-vip` |
| 拉 2018～2021 基本面 | 同脚本加长 `--start`；注意请求量与 token 时长 |
| 三大表 | `--with-statements`（VIP 或极长 `--no-vip`） |
| 行情缺口 | `compact_market_hq.py --gaps` → `update_panel.py` / `fetch_market.py --update` |
| 只补行业列 | `build_panel.py --enrich-only --with-industry`（勿随意 `--refresh-industry`） |

操作手册总流程见 [operations_manual.md](./operations_manual.md)。
