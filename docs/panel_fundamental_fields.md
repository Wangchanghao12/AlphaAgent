# Panel 基本面数据字段说明

> 面向学习与理解：讲清 AlphaAgent 的 panel 里都有哪些基本面（财务）字段、它们从哪来、怎么进面板、以及在 DSL 表达式里怎么用。
>
> 相关代码：`alphaagent/data/panel.py`、`alphaagent/data/fundamental.py`、`alphaagent/data/fundamental_fetch.py`、`alphaagent/core/types.py`、`alphaagent/factor/mining/prompts.py`。
> 操作命令见 `docs/operations_manual.md` §1.3–1.5。

---

## 1. Panel 是什么

- **格式**：单个 Parquet 文件，默认路径 `artifacts/panel/panel_1d.parquet`（常量 `PANEL_PATH`，见 `alphaagent/core/paths.py`）。
- **索引**：两层 `MultiIndex = (datetime, instrument)`
  - `datetime`：交易日（`DatetimeIndex`）
  - `instrument`：Tushare `ts_code`，如 `000001.SZ`
- **频率**：日频（1d）；DSL 里可用 `$field@1w` 引用周线（W-FRI，无前视 backward 广播）。
- **数值类型**：`float32`（`is_trade` / `not_st` 标记列除外）。
- **默认股票池**：`zz1000`（中证 1000 成分并集）。
- **数据源**：**全部来自 Tushare Pro API**（无 akshare / wind / 本地文件）。Token 读取自 `.env` 的 `TUSHARE_TOKEN`。

Panel 的列分三类：**行情/衍生/label 列**（始终存在）、**基本面财务列 `funda_*`**（仅 `--with-fundamentals` 时并入）、**披露日历特征列 `funda_days_*`**。本文档重点是后两类。

在 DSL 表达式中引用任意列的语法都是 **`$` + 列名**，例如 `$funda_roe`、`$adj_close`。

---

## 2. 基本面字段总览

基本面字段分组如下，均来自 Tushare、经**严格 PIT** 展开/映射为日频（见 §4）：

- **§2.1 财务指标**（17 个，前缀 `funda_`）+ **§2.2 披露日历特征**（2 个）——来自 `fina_indicator`，默认拉取。
- **§3 三大表科目**（约 70 个，前缀 `funda_fs_*`）——来自 `income`/`balancesheet`/`cashflow`，加 `--with-statements` 时并入。
- **§3.4 行业分类**（`industry_sw_l1`）——申万一级行业离散码，加 `--with-industry` 时并入，用于**行业中性化**。

### 2.1 财务指标（前缀 `funda_`）

来源：Tushare `fina_indicator`（VIP 用 `fina_indicator_vip` 拉全市场）。
映射定义：`alphaagent/data/fundamental_fetch.py` 中的 `FINA_INDICATOR_COLUMN_MAP`。

| Panel 列名 | Tushare 原字段 | 含义 | 单位/量纲 |
|---|---|---|---|
| `funda_roe` | `roe` | 净资产收益率 | %（百分比） |
| `funda_roa` | `roa` | 总资产报酬率 | % |
| `funda_debt_to_assets` | `debt_to_assets` | 资产负债率 | % |
| `funda_netprofit_yoy` | `netprofit_yoy` | 归母净利润同比增长率 | % |
| `funda_or_yoy` | `or_yoy` | 营业收入同比增长率 | % |
| `funda_tr_yoy` | `tr_yoy` | 营业总收入同比增长率 | % |
| `funda_bps` | `bps` | 每股净资产 | 元/股 |
| `funda_eps` | `eps` | 基本每股收益 | 元/股 |
| `funda_grossprofit_margin` | `grossprofit_margin` | 销售毛利率 | % |
| `funda_netprofit_margin` | `netprofit_margin` | 销售净利率 | % |
| `funda_ocfps` | `ocfps` | 每股经营活动现金流净额 | 元/股 |
| `funda_profit_dedt` | `profit_dedt` | 扣非净利润（扣除非经常性损益） | 元 |
| `funda_current_ratio` | `current_ratio` | 流动比率 | 倍（无量纲） |
| `funda_quick_ratio` | `quick_ratio` | 速动比率 | 倍（无量纲） |
| `funda_fs_working_capital` | `working_capital` | 营运资本 | 元 |
| `funda_fs_ebit` | `ebit` | 息税前利润 | 元 |
| `funda_fs_rd_exp` | `rd_exp` | 研发费用（部分股票为 NaN） | 元 |

> 命名说明：`working_capital` / `ebit` / `rd_exp` 虽用了 `funda_fs_` 前缀（财报科目命名规范），但它们**实际是从 `fina_indicator` 拉取的**，与 §3 三大表接口来源不同（§3 里不再重复这三项）。

### 2.2 披露日历特征（前缀 `funda_days_`）

由 `alphaagent/data/fundamental.py` 计算（纯日历/PIT 推导，非 Tushare 原字段）。定义于 `DISCLOSURE_DISTANCE_COLUMNS`。

| Panel 列名 | 含义 | 单位 |
|---|---|---|
| `funda_days_since_disclose` | 距**上一期**财报披露**生效日**的交易日数（生效日 = 0）；严格 PIT，披露前为 NaN | 交易日数 |
| `funda_days_since_quarter_start` | 距当前季报区间首日（1/1、4/1、7/1、10/1）的交易日数 | 交易日数 |

> 可用 `--no-disclosure-distance` 关闭这两列的写入。

---

## 3. 三大表科目（`funda_fs_*`，可选并入）

三大表（利润表 / 资产负债表 / 现金流量表）来自 Tushare `income` / `balancesheet` / `cashflow`（VIP 用 `*_vip` 按期拉全市场，需 5000 积分）。
拉取时加 `--with-statements` 即并入同一份 `quarterly.parquet`，随 `fina_indicator` 一起走**同一套严格 PIT 展开**为日频（映射见 `alphaagent/data/fundamental_fetch.py` 的 `INCOME_COLUMN_MAP` / `BALANCESHEET_COLUMN_MAP` / `CASHFLOW_COLUMN_MAP`）。

**口径约定（按 Tushare 原始值存储，不做单季差分）：**
- **资产负债表**：**时点值**，列名无后缀（如 `funda_fs_total_assets`）。
- **利润表 / 现金流量表**：Tushare 返回**年初至今累计值（YTD）**，列名统一带 **`_ytd`** 后缀（Q1=当季，中报/三季报/年报为累计）。
- 期末/期初现金余额为时点值，用 `funda_fs_cash_equiv_end` / `_beg`。
- 仅取 `report_type='1'`（合并报表）；同 `(ts_code, end_date)` 保留 `ann_date` 最新一条。
- 单位均为**元**（EPS 为元/股，`funda_fs_total_share` 为股）。

### 3.1 利润表（`income` → `_ytd` 累计）

| Panel 列名 | Tushare 字段 | 含义 |
|---|---|---|
| `funda_fs_total_revenue_ytd` | `total_revenue` | 营业总收入 |
| `funda_fs_oper_revenue_ytd` | `revenue` | 营业收入 |
| `funda_fs_total_cogs_ytd` | `total_cogs` | 营业总成本 |
| `funda_fs_oper_cost_ytd` | `oper_cost` | 营业成本 |
| `funda_fs_selling_expense_ytd` | `sell_exp` | 销售费用 |
| `funda_fs_admin_expense_ytd` | `admin_exp` | 管理费用 |
| `funda_fs_finance_expense_ytd` | `fin_exp` | 财务费用 |
| `funda_fs_interest_expense_ytd` | `int_exp` | 利息支出 |
| `funda_fs_tax_surcharge_ytd` | `biz_tax_surchg` | 营业税金及附加 |
| `funda_fs_operate_profit_ytd` | `operate_profit` | 营业利润 |
| `funda_fs_total_profit_ytd` | `total_profit` | 利润总额 |
| `funda_fs_income_tax_ytd` | `income_tax` | 所得税费用 |
| `funda_fs_net_profit_ytd` | `n_income` | 净利润（含少数股东损益） |
| `funda_fs_net_profit_parent_ytd` | `n_income_attr_p` | 归母净利润 |
| `funda_fs_minority_interest_ytd` | `minority_gain` | 少数股东损益 |
| `funda_fs_comprehensive_income_ytd` | `t_compr_income` | 综合收益总额 |
| `funda_fs_comprehensive_income_parent_ytd` | `compr_inc_attr_p` | 归母综合收益 |
| `funda_fs_eps_basic_ytd` | `basic_eps` | 基本每股收益 |
| `funda_fs_eps_diluted_ytd` | `diluted_eps` | 稀释每股收益 |

### 3.2 资产负债表（`balancesheet` → 时点值）

| Panel 列名 | Tushare 字段 | 含义 |
|---|---|---|
| `funda_fs_total_assets` | `total_assets` | 资产总计 |
| `funda_fs_current_assets` | `total_cur_assets` | 流动资产合计 |
| `funda_fs_noncurrent_assets` | `total_nca` | 非流动资产合计 |
| `funda_fs_total_liabilities` | `total_liab` | 负债合计 |
| `funda_fs_current_liabilities` | `total_cur_liab` | 流动负债合计 |
| `funda_fs_noncurrent_liabilities` | `total_ncl` | 非流动负债合计 |
| `funda_fs_total_equity` | `total_hldr_eqy_exc_min_int` | 股东权益（不含少数） |
| `funda_fs_total_equity_incl_mi` | `total_hldr_eqy_inc_min_int` | 股东权益（含少数） |
| `funda_fs_total_liab_equity` | `total_liab_hldr_eqy` | 负债及股东权益总计 |
| `funda_fs_minority_interest_equity` | `minority_int` | 少数股东权益 |
| `funda_fs_money_cap` | `money_cap` | 货币资金 |
| `funda_fs_notes_receivable` | `notes_receiv` | 应收票据 |
| `funda_fs_accounts_receivable` | `accounts_receiv` | 应收账款 |
| `funda_fs_inventories` | `inventories` | 存货 |
| `funda_fs_fixed_assets` | `fix_assets` | 固定资产 |
| `funda_fs_construction_in_progress` | `cip` | 在建工程 |
| `funda_fs_intangible_assets` | `intan_assets` | 无形资产 |
| `funda_fs_goodwill` | `goodwill` | 商誉 |
| `funda_fs_rd_capitalized` | `r_and_d` | 研发支出（资本化） |
| `funda_fs_short_term_borrow` | `st_borr` | 短期借款 |
| `funda_fs_long_term_borrow` | `lt_borr` | 长期借款 |
| `funda_fs_bond_payable` | `bond_payable` | 应付债券 |
| `funda_fs_notes_payable` | `notes_payable` | 应付票据 |
| `funda_fs_accounts_payable` | `acct_payable` | 应付账款 |
| `funda_fs_advance_receipts` | `adv_receipts` | 预收款项 |
| `funda_fs_taxes_payable` | `taxes_payable` | 应交税费 |
| `funda_fs_payroll_payable` | `payroll_payable` | 应付职工薪酬 |
| `funda_fs_other_payables` | `oth_payable` | 其他应付款 |
| `funda_fs_retained_earnings` | `undistr_porfit` | 未分配利润 |
| `funda_fs_surplus_reserve` | `surplus_rese` | 盈余公积 |
| `funda_fs_capital_reserve` | `cap_rese` | 资本公积 |
| `funda_fs_total_share` | `total_share` | 期末总股本（股） |
| `funda_fs_other_comprehensive_income` | `oth_comp_income` | 其他综合收益 |

### 3.3 现金流量表（`cashflow`）

`_ytd` 为年初至今累计；`funda_fs_cash_equiv_end/beg` 为时点余额。

| Panel 列名 | Tushare 字段 | 含义 |
|---|---|---|
| `funda_fs_cash_from_sales_ytd` | `c_fr_sale_sg` | 销售商品/劳务收到的现金 |
| `funda_fs_ocf_inflow_ytd` | `c_inf_fr_operate_a` | 经营活动现金流入小计 |
| `funda_fs_cash_paid_goods_ytd` | `c_paid_goods_s` | 购买商品/劳务支付的现金 |
| `funda_fs_cash_paid_employees_ytd` | `c_paid_to_for_empl` | 支付给职工的现金 |
| `funda_fs_cash_paid_taxes_ytd` | `c_paid_for_taxes` | 支付的各项税费 |
| `funda_fs_ocf_outflow_ytd` | `st_cash_out_act` | 经营活动现金流出小计 |
| `funda_fs_ocf_net_ytd` | `n_cashflow_act` | 经营活动现金流量净额 |
| `funda_fs_capex_ytd` | `c_pay_acq_const_fiolta` | 购建固定/无形/长期资产支付现金 |
| `funda_fs_cash_paid_invest_ytd` | `c_paid_invest` | 投资支付的现金 |
| `funda_fs_icf_net_ytd` | `n_cashflow_inv_act` | 投资活动现金流量净额 |
| `funda_fs_cash_from_borrow_ytd` | `c_recp_borrow` | 取得借款收到的现金 |
| `funda_fs_cash_repay_debt_ytd` | `c_prepay_amt_borr` | 偿还债务支付的现金 |
| `funda_fs_fcf_net_ytd` | `n_cash_flows_fnc_act` | 筹资活动现金流量净额 |
| `funda_fs_free_cashflow_ytd` | `free_cashflow` | 企业自由现金流量 |
| `funda_fs_cash_net_incr_ytd` | `n_incr_cash_cash_equ` | 现金及等价物净增加额 |
| `funda_fs_depreciation_ytd` | `depr_fa_coga_dpba` | 固定资产折旧/油气折耗/生物折旧 |
| `funda_fs_amortization_intangible_ytd` | `amort_intang_assets` | 无形资产摊销 |
| `funda_fs_ocf_indirect_ytd` | `im_net_cashflow_oper_act` | 经营活动现金流量净额（间接法） |
| `funda_fs_cash_equiv_beg` | `c_cash_equ_beg_period` | 期初现金及等价物余额（时点） |
| `funda_fs_cash_equiv_end` | `c_cash_equ_end_period` | 期末现金及等价物余额（时点） |

> 注：`funda_fs_working_capital`（营运资本）、`funda_fs_ebit`（息税前利润）、`funda_fs_rd_exp`（研发费用）由 `fina_indicator` 提供（见 §2.1），不来自三大表接口，避免重复。
> `alphaagent/data/fundamental.py` 里另有一套中文名 `FUNDAMENTAL_STATEMENT_COLUMN_MAP`（对齐 AlphaAgent 数据源）用于读取历史中文列名，与上述英文接入路径互不冲突。

**DSL 使用**：与其他 `funda_*` 列一致，用 `$funda_fs_total_assets` 引用。累计值可用同比/环比构造：`TS_PCTCHANGE($funda_fs_oper_revenue_ytd, 60)` ≈ 单季环比参考；跨年注意 YTD 在 Q1 归零的阶跃。

### 3.4 行业分类：`industry_sw_l1`（可选并入）

基本面要放到行业里看——行业中性化能剔除"某因子只是反映了行业 beta"的部分。加 `--with-industry` 即并入一列申万一级行业码。

| Panel 列名 | 含义 | 类型 | 说明 |
|---|---|---|---|
| `industry_sw_l1` | 申万一级行业（SW2021）**离散整数码** 1..N | float32 | 严格 PIT；未归类为 NaN |

- **数据源**：Tushare `index_classify(level='L1', src='SW2021')`（行业目录，31 个）+ `index_member`（个股成员，含 `in_date`/`out_date`）。映射与拉取见 `alphaagent/data/industry.py`。
- **整数编码**：按行业 `index_code` 排序分配 1..N，跨次运行稳定；`sw_l1_code_map()` 可取"码→行业名"。
- **严格 PIT**：用 `merge_asof(backward)` 按 `in_date` 把每个交易日映射到当日有效行业；晚于 `out_date` 的样本置 NaN。**无前视**。
- **缓存**：成员表落 `artifacts/industry/sw_l1_membership.parquet`；首次自动拉取，`--refresh-industry` 强制重拉。
- **只做分组、不做数值运算**：行业码是类别标签，做加减/排序无意义。

**DSL 用法（行业中性化）**：行业码本身就是离散组号，**直接**当 `CS_NEUTRALIZE` 的分组参数，**勿**再套 `CS_BUCKET`：

```text
# 行业内去均值（行业中性）
CS_NEUTRALIZE($factor, $industry_sw_l1)

# 行业 + 市值双重中性
CS_NEUTRALIZE(CS_NEUTRALIZE($factor, $industry_sw_l1), CS_BUCKET(LOG($float_cap), 10))
```

> 原理：DSL 变量从 `panel.columns` 自动派生，`$industry_sw_l1` 即绑定该列；`CS_NEUTRALIZE(x, group)` 按 `group` 的离散值分组做 `x − 组内均值`。因此整数行业码可直接用作分组，无需改动 DSL。

---

## 4. 从 Tushare 到日频 Panel 的链路

### 4.1 拉季频缓存（`scripts/fetch_fundamentals.py`）

1. `fetch_fina_indicator_period`：VIP 每期一次拉全 A 股 `fina_indicator`。
2. `raw_fina_to_quarterly`：整理为索引 `(report_end, instrument)` 的季频宽表 → 写 `artifacts/fundamental/quarterly.parquet`。
3. `raw_fina_to_disclosure_events`：从 `ann_date`（公告日）提取披露日 → 写 `artifacts/fundamental/disclosure_calendar.parquet`（行 = `report_end`，列 = `instrument`，值 = 披露日期）。
4. （可选，`--with-statements`）`fetch_statement_period` + `raw_statement_to_quarterly`：每期拉 `income`/`balancesheet`/`cashflow`，过滤 `report_type='1'`、同键取最新 `ann_date`，按 `(report_end, instrument)` **列向合并**进同一份 `quarterly.parquet`。

### 4.2 PIT 展开并入 panel（`enrich_panel_fundamentals` → `expand_quarterly_fundamentals_pit`）

**严格 PIT（Point-In-Time，避免前视偏差）语义**：

- 财报公告日 D **当天不可用**；从 **D 的下一个交易日**起，该期字段才生效。
- 两期财报之间用 **ffill** 保持"最近一期已披露值"（即日频上表现为**阶跃 + 持有**）。
- 首次披露之前为 **NaN**，这是正常现象，不是数据缺失错误。

因此在日频上，`funda_*` 列在整个季度内是一条水平线，只在下一份财报生效日跳变一次。

---

## 5. 在 DSL 里使用基本面字段

基本面因子是"慢因子"，用法与价量因子不同，几条要点：

- **窗口单位是交易日**：`TS_PCTCHANGE($funda_roe, 20)` 的 20 指 20 个交易日；约 **60 交易日 ≈ 一个季度**。
- **市值中性**：截面组合建议加 `CS_NEUTRALIZE(..., CS_BUCKET(LOG($float_cap), 10))`。
- **先去极值再排序**：比率类字段可先 `CS_WINSORIZE` 再 `RANK`。
- **label 选用**：基本面/慢因子用 `--label-col label_10d_close_to_close`（或 `label_20d_...`）；价量/短周期因子用 `label_1d_close_to_close`。
- **事件窗**：可借助披露距离列，如 `TS_PCTCHANGE($xxx, $funda_days_since_disclose)`。

### 已入库示例

`artifacts/factorzoo/stock_1d/expressions/roe_lowvol_center_smooth.dsl`（引用 `$funda_roe`）：

```1:7:artifacts/factorzoo/stock_1d/expressions/roe_lowvol_center_smooth.dsl
roe_r = RANK(CS_WINSORIZE($funda_roe, 0.01, 0.99))
vol = TS_STD($ret, 20)
vol_r = RANK(DIVIDE(1, ADD(vol, 0.001)))
roe_center = MULTIPLY(roe_r, SUBTRACT(1, roe_r))
vol_center = MULTIPLY(vol_r, SUBTRACT(1, vol_r))
score = ADD(roe_center, vol_center)
CS_NEUTRALIZE(CS_WINSORIZE(score, 0.01, 0.99), CS_BUCKET(LOG($float_cap), 10))
```

`artifacts/factorzoo/stock_1d/expressions/netprofit_yoy_lowvol_turnover_gaussian.dsl`（引用 `$funda_netprofit_yoy`）：

```1:4:artifacts/factorzoo/stock_1d/expressions/netprofit_yoy_lowvol_turnover_gaussian.dsl
np_z = CS_ZSCORE(CS_WINSORIZE($funda_netprofit_yoy, 0.01, 0.99))
vol_z = CS_ZSCORE(TS_STD($ret, 20))
amt = TS_MEAN($amount, 20)
turnover_z = CS_ZSCORE(DIVIDE(amt, $float_cap))
```

---

## 6. 附：行情 / 衍生 / label 列（非基本面，便于对照）

始终存在，`build_panel` 自动生成（`OUTPUT_COLUMNS`，见 `alphaagent/core/types.py`）。

| 字段 | 含义 | 说明 |
|---|---|---|
| `open` `high` `low` `close` | 原始 OHLC | Tushare `pro.daily` |
| `adj_open` `adj_high` `adj_low` `adj_close` | 后复权 OHLC | 因子**优先**用复权价 |
| `adjfactor` | 复权因子 | Tushare `pro.adj_factor` |
| `volume` `amount` | 成交量 / 成交额 | `amount` 为千元口径 |
| `float_cap` `tot_cap` | 流通市值 / 总市值 | 元（Tushare `circ_mv`/`total_mv` × 10000） |
| `is_trade` `not_st` | 可交易 / 非 ST 标记 | 0/1 |
| `ret` | 日收益 | adj_close 按 instrument pct_change |
| `vwap` `adj_vwap` | 量加权均价 / 其复权版 | `amount/volume`、`vwap×adjfactor` |
| `label_1d_open_to_open` | T+1 开盘 → T+2 开盘 | 脚本默认 label |
| `label_1d_close_to_close` | T+1 → T+2 收盘（1 日持有） | 适合价量因子 |
| `label_10d_close_to_close` | T+1 → T+11 收盘（10 日持有） | 适合基本面因子 |
| `label_20d_close_to_close` | T+1 → T+21 收盘（20 日持有） | 适合基本面因子 |

---

## 7. 相关命令速查

```powershell
# 拉季频基本面缓存（VIP 全 A 股，仅 fina_indicator）
uv run python scripts/fetch_fundamentals.py --start 2015-01-01 --end 2026-12-31

# 同时拉三大表（income/balancesheet/cashflow，需 VIP 5000 积分）
uv run python scripts/fetch_fundamentals.py --start 2015-01-01 --end 2026-12-31 --with-statements

# 从 hq 缓存离线建 panel 并一并 enrich 基本面（+ 行业列）
uv run python scripts/build_panel.py --with-fundamentals --with-industry

# 已有 panel，仅补基本面列（可叠加 --with-industry 补行业列）
uv run python scripts/build_panel.py --enrich-only --with-industry

# 增量更新行情后刷新基本面 + 行业
uv run python scripts/update_panel.py --universe zz1000 --with-fundamentals --with-industry

# 调试基本面因子（用 10 日 label）
uv run python scripts/eval_factor.py --expr-file your.dsl --report --label-col label_10d_close_to_close
```

---

## 8. 权威信息源

字段说明目前分散在三处（**无独立数据字典文件**，本文档即为补充）：

1. `alphaagent/factor/mining/prompts.py`（注入挖掘 LLM 的字段说明表，最贴近实际使用）
2. `docs/operations_manual.md` §1.4（拉数/enrich 命令与 PIT 语义）
3. 代码内映射字典（机器可读的字段定义源头）：`FINA_INDICATOR_COLUMN_MAP`、`INCOME_COLUMN_MAP`、`BALANCESHEET_COLUMN_MAP`、`CASHFLOW_COLUMN_MAP`（均在 `alphaagent/data/fundamental_fetch.py`）；行业分类见 `alphaagent/data/industry.py`
