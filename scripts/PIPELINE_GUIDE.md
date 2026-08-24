# AlphaAgent 数据与因子挖掘全流程指南

> 适用环境：服务器 `recom-gpu-a10-2`，仓库路径 `/mnt/recom/develop/wangchanghao/rtp_fg/AlphaAgent`
> 最后更新：2026-08-24（含 vnpy 归档转换方案）

---

## 0. 总体架构

```
数据源                      缓存层                          应用层
─────                      ─────                          ─────
Tushare REST API   ──►  artifacts/market/daily_hq.parquet  ──►  artifacts/panel/panel_1d.parquet
  (或 vnpy 归档转换)      artifacts/fundamental/*.parquet          │        │
                          artifacts/industry/*.parquet             │        │
                                                                   ▼        ▼
                                                          因子挖掘(LLM)   批量复检
                                                                   │
                                                                   ▼
                                              artifacts/factorzoo/stock_1d/（registry + DSL）
                                                                   │
                                                                   ▼
                                                  导出 vnpy 特征表 → LightGBM 训练/回测
```

**两段式设计**：联网拉数落缓存（慢）→ 离线建 panel / 挖掘 / 导出（快，纯本地计算）。

---

## 1. 关键路径

| 路径 | 内容 |
|------|------|
| `artifacts/market/daily_hq.parquet` | 行情 hq 缓存，索引 `(datetime, instrument)`，含 OHLCV + adjfactor + daily_basic + ST 标记 |
| `artifacts/panel/panel_1d.parquet` | 宽表 panel：hq + adj_*/ret/label + funda_* + industry_sw_l1 |
| `artifacts/fundamental/quarterly.parquet` | 季频基本面缓存（PIT） |
| `artifacts/industry/sw_l1_membership.parquet` | 申万一级行业归属 |
| `artifacts/index/*_members.parquet` | 指数成分快照缓存 |
| `artifacts/factorzoo/stock_1d/mining_delivered_registry.json` | **权威因子清单**（服务器为准） |
| vnpy 归档 | `/mnt/recom/develop/wangchanghao/rtp_fg/em_ak/em_ak/examples/alpha_research/lab/` |

---

## 2. 行情数据准备（首次 / 重建）

### 方案 A：直接从 Tushare 拉取

```bash
# 全市场按日拉取（2010~今约 4000+ 交易日，4 并发约 30~60 分钟）
python -u scripts/fetch_market.py \
  --start 2010-01-01 --end 2026-08-22 \
  --universe none --workers 4 --checkpoint-every 5 \
  > log/fetch_market.log 2>&1 &

# 基本面 + 行业
python -u scripts/fetch_fundamentals.py > log/fetch_funda.log 2>&1 &
```

支持断点续跑：每 5 个交易日 checkpoint 到 `daily_hq_parts/`，中断后重跑自动跳过已有日期。

### 方案 B：从 vnpy 归档转换（推荐，免联网、快）

前提：服务器上已有 vnpy 的 AlphaLab 按股数据 + tushare 归档
（`download_tushare_archive.py all` 的产物：daily_basic / adj_factor / stock_st 等）。

```bash
python -u scripts/convert_vnpy_to_hq.py \
  --vnpy-root /mnt/recom/develop/wangchanghao/rtp_fg/em_ak/em_ak/examples/alpha_research \
  --start 2010-01-01 --end 2026-08-22 \
  > log/convert_vnpy.log 2>&1 &
```

转换映射：

| AlphaAgent 字段 | vnpy 来源 | 换算 |
|----------------|----------|------|
| open/high/low/close | AlphaLab 按股 parquet（前复权） | 直接用 |
| volume | AlphaLab volume（股） | ÷100 → 手 |
| amount | AlphaLab turnover（元） | ÷1000 → 千元 |
| adjfactor | tushare/market/adj_factor | 直接用 |
| pe_ttm/pb/turnover_rate 等 | tushare/market/daily_basic | 直接用 |
| float_cap/tot_cap | daily_basic 的 circ_mv/total_mv | ×10000 |
| is_st/not_st | tushare/events/stock_st | 直接用 |
| 代码格式 | `000001.SZSE` → `000001.SZ` | 自动映射 |

> 注意：vnpy 归档是历史快照，**当天数据不在其中**，转换后需增量补齐（见第 4 节）。
> 归档中如有重复行，脚本已做 `~index.duplicated(keep="last")` 去重。

### 验证 hq 缓存

```bash
python - <<'EOF'
import pandas as pd
hq = pd.read_parquet('artifacts/market/daily_hq.parquet')
print("shape:", hq.shape, "index:", hq.index.names)
dt = hq.index.get_level_values('datetime')
print("日期:", dt.min().date(), "~", dt.max().date())
print("股票数:", hq.index.get_level_values('instrument').nunique())
print("adjfactor 非1比例:", (hq['adjfactor'] != 1.0).mean())
print("pe_ttm 非空比例:", hq['pe_ttm'].notna().mean())
EOF
```

---

## 3. Panel 构建（离线）

```bash
# 全量重建（hq 缓存大改后用这个，13.8M 行约 4~5 分钟）
python -u scripts/build_panel.py --with-fundamentals --with-industry \
  > log/build_panel.log 2>&1 &
```

耗时参考（13.8M 行）：加载 hq ~4s → 派生 adj/ret/label ~54s → enrich 基本面+行业 ~170s → 写盘 ~23s。

验证：

```bash
python - <<'EOF'
import pandas as pd
p = pd.read_parquet('artifacts/panel/panel_1d.parquet')
print("shape:", p.shape)
for c in ['adj_close', 'ret', 'label_10d_close_to_close', 'funda_roe', 'industry_sw_l1']:
    if c in p.columns:
        print(f"  {c}: {p[c].notna().mean():.1%}")
EOF
```

`label_10d_close_to_close` 非空率 >95% 即正常（末尾 10 天天然无未来标签）。

---

## 4. 日常增量更新

```bash
# 一条命令：检测缺口 → 拉行情 → 追加 hq → panel 增量重建
python -u scripts/update_panel.py --universe zz1000 \
  --with-fundamentals --with-industry \
  > log/update_panel.log 2>&1 &
```

注意事项：

- **当天数据 17:00 后才发布**：盘中/刚收盘跑会拉到 0 行（`逐股拉取，累计 0 行`），晚上再跑。
- **成分缓存可能不全**：若日志出现 `共 300 只`（zz1000 应为 1000 只），用
  `python scripts/fetch_market.py --update --universe zz1000 --refresh-members` 刷新成分后重跑。
- 只补行情不建 panel：`python scripts/fetch_market.py --update --universe zz1000`

---

## 5. 因子挖掘（LLM 并行）

```bash
export OPENAI_API_KEY=sk-xxxx
bash scripts/run_factor_mining_parallel.sh --lanes momentum,volatility,volume,weekly
# 可选：--no-submit（只评估不入库）、--max-turns N、--panel <路径>
```

**评估窗口（默认，刻意取近年数据）**：

| 窗口 | 范围 | 用途 |
|------|------|------|
| train | 2019-01-01 ~ 2021-12-31 | 主力探索 |
| val | 2022-01-01 ~ 2024-12-31 | 泛化验证 |
| holdout | 2025-01-01 ~ 2026-07-31 | submit 强制 OOS 复检 |

> **2019 年之前的数据不参与挖掘评估**（连 TS warmup 都不用）——这是刻意设计：
> 2026 市场状态是因子有效性的权威验证基准，远古行情结构差异太大会稀释信号。
> 早期历史留给 vnpy 长周期回测。

产物：`artifacts/factorzoo/stock_1d/`（registry + expressions/*.dsl）。
日志：`logs/factor_mining/<lane>/cli_<时间戳>.log`。

---

## 6. 因子批量复检

```bash
# 复检本轮 submit 的因子
python -u scripts/eval_mining_batch.py --source-filter submit

# 全部因子（含 seed）
python -u scripts/eval_mining_batch.py --source-filter all

# 收紧门槛（2026 regime-aware 筛选协议）
python -u scripts/eval_mining_batch.py --source-filter all \
  --min-holdout-ic 0.02 --min-holdout-icir 0.25 --min-holdout-t 3
```

筛查要点（2026 regime-aware 协议）：

1. 同标签口径（`label_10d_close_to_close`），否则 IC 不可比。
2. holdout ICIR > 2× val ICIR 的因子标记为"疑似 2026 过拟合"，人工复查。
3. 同家族因子先按相似度去重，再进 vnpy。
4. 最终有效性以 vnpy 侧 LightGBM 边际提升为准，单因子 IC 不充分。

---

## 7. 导出 vnpy 特征表

```bash
python -u scripts/export_factors_to_vnpy.py \
  --registry artifacts/factorzoo/stock_1d/mining_delivered_registry.json \
  --out /mnt/recom/develop/wangchanghao/rtp_fg/em_ak/em_ak/examples/alpha_research/lab/factor_tables/mining_factors.parquet
```

行为说明：

- 对**完整 panel（2010 起）**求值每个因子 DSL → 与 vnpy 侧 Alpha158 等特征自然对齐。
- 2010~2018 的因子值是"外推计算"（DSL 逻辑正确但 IC 未验证），供长周期回测使用。
- TS 算子头部 warmup 为 NaN，属正常，LightGBM 可处理。
- 默认合并已有输出文件的旧因子列；`--no-merge` 完全覆盖。原子写（tmp + rename）。
- 服务器 registry 是权威因子清单，本地表达式须从服务器同步。

vnpy 侧用 `inject_mining_factors` 左连进 raw_df/infer_df/learn_df，因子列自动成为 LightGBM 特征。

---

## 8. 常见坑（Troubleshooting）

| 现象 | 原因 | 处理 |
|------|------|------|
| `fetch_market` 报 `已缓存 0 天` 但文件存在 | 旧版文件的 MultiIndex 与 `pd.read_parquet(columns=[])` 扫描不兼容 | 让它重跑即可，跑完格式统一 |
| 增量拉当天 `累计 0 行` | 当天行情 17:00 后才发布 | 晚上再跑 |
| 增量只显示 `共 300 只` | 指数成分缓存不全 | `--refresh-members` 刷新 |
| `nohup` 日志为空 | Python stdout 缓冲 | 加 `-u`：`python -u script.py` |
| 转换报 `non-unique multi-index` | vnpy 归档有重复行 | 脚本已去重（`~index.duplicated(keep="last")`） |
| 进程在跑但 panel 文件没变 | 还在内存计算/联网阶段 | `watch -n 10 'ls -la artifacts/panel/panel_1d.parquet'` |
| 挖掘内存爆 | 全列加载 | lane 模式自动带 `--cols`；或 `--no-fundamentals` |
| 因子只在最近一段日期有效（`first_finite` 异常靠后），早期全 NaN | 归档行情含 `amount=0 且 volume>0` 脏行（约每天 1 行）→ `vwap=0` → 表达式除零产生 `inf` → `CS_ZSCORE` 等截面算子被单个 inf 打成整截面 NaN | 已修：`panel.py` vwap 要求 amount/volume 均 >0；CS_* 算子用 `isfinite` 判有效（不再用 `notna`，它放行 inf）。重建 panel 后生效；诊断时先查中间量是否有 inf |

---

## 9. 速查：从零到挖掘的最短路径

```bash
cd /mnt/recom/develop/wangchanghao/rtp_fg/AlphaAgent

# 1) 行情：vnpy 归档转换（约 10 分钟）或 Tushare 直拉（约 30~60 分钟）
python -u scripts/convert_vnpy_to_hq.py --vnpy-root <VN> --start 2010-01-01 --end 2026-08-22

# 2) 建 panel（约 5 分钟）
python -u scripts/build_panel.py --with-fundamentals --with-industry

# 3) 挖因子
bash scripts/run_factor_mining_parallel.sh --lanes momentum,volatility,volume,weekly

# 4) 复检
python -u scripts/eval_mining_batch.py --source-filter submit

# 5) 导出 vnpy
python -u scripts/export_factors_to_vnpy.py --out <VN>/lab/factor_tables/mining_factors.parquet
```
