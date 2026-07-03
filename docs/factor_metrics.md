# 因子评估指标说明

本文档说明 `scripts/eval_factor.py --report` 输出报告中各指标的含义。计算逻辑见 [`seekalpha/factor/metrics.py`](../seekalpha/factor/metrics.py)。

## 如何生成报告

```bash
uv run python scripts/eval_factor.py --expr-file examples/factors/ma_dev.dsl --report
uv run python scripts/eval_factor.py --expr-file your.dsl --report --start-time 2024-06-01 --end-time 2026-05-31
```

- DSL 在**全量 panel** 上求值（保证长窗口因子 warmup 正确）。
- `--start-time` / `--end-time` 仅用于**指标统计区间**切片。
- 默认标签列：`label_1d_open_to_open`（可用 `--label-col` 修改）。

---

## 报告头信息

| 字段 | 含义 |
|------|------|
| **评估区间** | 参与 IC / MLS 等汇总的交易日范围 |
| **标签列** | 因子与之计算相关性的收益标签（见下文） |
| **有效 IC 天数** | 截面 IC 非 NaN 的交易日数量 |

### 常用标签列

| 列名 | 定义（简化） |
|------|----------------|
| `label_1d_open_to_open` | 从 **T+1 开盘** 到 **T+2 开盘** 的收益率（CLI 默认） |
| `label_1d_close_to_close` | 从 **T+1 收盘** 到 **T+2 收盘**（持有 1 个交易日；**推荐价量因子**） |
| `label_10d_close_to_close` | 从 **T+1 收盘** 到 **T+11 收盘**（持有 10 个交易日；**推荐基本面因子**） |
| `label_20d_close_to_close` | 从 **T+1 收盘** 到 **T+21 收盘**（持有 20 个交易日） |
| `ret` | 当日相对前一日收盘的日收益率（多用于描述性统计，作 label 较少） |

**选用建议**：评估 / 挖掘时用 `--label-col` 显式指定——基本面 → `label_10d_close_to_close`；价量 → `label_1d_close_to_close`。

---

## 截面 IC

每个交易日，在股票截面上计算因子值与未来 label 的相关性，再对时间求均值。

| 指标 | 含义 | 解读提示 |
|------|------|----------|
| **IC** | 逐日截面 **Pearson** 相关的均值 | 绝对值越大，线性预测力越强；符号表示因子方向 |
| **ICIR** | `mean(IC) / std(IC)` | IC 的稳定性；\|ICIR\| 越大，信号越稳定 |
| **Rank IC** | 逐日截面 **Spearman** 秩相关的均值 | 对极端值更稳健，关注排序而非线性关系 |
| **Coverage** | 因子有限值占比 | 过低说明表达式大量 NaN，或窗口/数据字段缺失 |
| **CS lag-1 ρ** | 逐日截面 lag-1 自相关 `corr(f_t, f_{t-1})` 的均值 | 过高（如 >0.6）表示排名日度延续性强、换手可能偏低；过低则因子噪声大、换手高 |

---

## MLS / FMB

**Monotonicity + Long-Short，Fama–MacBeth 时序聚合**（非参数版）。

每日在截面上把股票按因子值等频分成 10 组（Q1=最低，Q10=最高），计算：

- **ρ_t**：组号 `{1…10}` 与组内 label 均值 `{R_{1,t}…R_{10,t}}` 的 Spearman 相关，衡量**单调性**（因子越高，label 是否系统性越高）。
- **LS_t**：`R_{Q10,t} - R_{Q1,t}`，**多空组合**当日 label 差（最高组减最低组）。

再对 `{ρ_t}`、`{LS_t}` 时序序列做 Newey–West 稳健检验。

| 指标 | 含义 |
|------|------|
| **mean ρ** | 逐日单调性 ρ_t 的均值 |
| **mean LS** | 逐日多空 LS_t 的均值 |
| **IR_LS** | `mean(LS) / std(LS)`，日频多空收益的信息比 |
| **IR_LS 年化** | `IR_LS × √252` |
| **MLS** | `mean(ρ) × IR_LS 年化`，综合单调性与多空 Sharpe 的得分 |
| **NW-t(ρ)** | mean(ρ) 的 Newey–West t 统计量（检验是否显著异于 0） |
| **NW-t(LS)** | mean(LS) 的 Newey–West t 统计量 |
| **样本天数** | 参与 ρ 序列估计的有效交易日数 |

---

## 十分组 label 均值

全样本（评估区间内）按因子值等频分成 10 组，展示每组的 label 均值。

| 符号 | 含义 |
|------|------|
| **D1** | 因子值**最低**组 |
| **D10** | 因子值**最高**组 |
| **柱状图** | 相对 D1–D10 均值范围的示意，便于肉眼检查单调性 |
| **数值** | 该组 label 的样本均值 |

理想情况下，从 D1 到 D10 label 均值应单调递增（做多因子）或递减（做空因子）。

---

## 入库相关指标（`ingest_factors.py`）

批量入库时除上述 IC 类指标外，还会做**截面相似度查重**（与库内已有因子比较）：

| 规则 | 说明 |
|------|------|
| **max_cs_corr** | 候选因子与库内因子的最大截面 \|Pearson\| 均值；默认 ≥0.8 拒绝入库 |
| **train_start 之前 mask** | 入库值在 `train_start` 之前置 NaN，评估区间从 train_start 起算 |

默认入库策略见 [`seekalpha/factor/types.py`](../seekalpha/factor/types.py) 中的 `IngestPolicy`。

---

## panel 更新后增量 realign（`realign_factorlib.py`）

`update_panel.py` 追加新交易日后，若因子库 index **前缀不变**（仅尾部追加行），可用增量 realign：

```bash
uv run python scripts/update_panel.py --universe zz1000
uv run python scripts/realign_factorlib.py
```

| 步骤 | 说明 |
|------|------|
| **窗口** | 默认取近 **240** 个交易日 + 新增行 N 做 DSL batch 求值 |
| **校验** | update 前最后 **K** 个交易日（默认 **20**）与库内 memmap **float32 完全一致** |
| **失败** | 扩窗至 **480** 重试；仍失败则该因子 **全 panel 重算** |
| **前缀变化** | index 非 append-only 时自动 **全量 realign** |

可选：`--overlap-verify-days 10` 调整校验天数。

| 试跑（不写盘） | `uv run python scripts/realign_factorlib.py --dry-run` |
| **滚动 probe**（库已对齐、模拟多窗口） | `uv run python tests/test_factor/rolling_probe_incremental_realign.py` |

---

## 参考阈值（挖掘 / 入库，非硬约束）

| 指标 | 常见参考 |
|------|----------|
| \|IC\| | > 0.005 有一定预测力 |
| \|ICIR\| | > 0.1 较稳定 |
| Coverage | > 0.9 可实盘化 |
| CS lag-1 ρ | > 0.6 排名延续性尚可（过高可能换手过低） |

具体门槛以策略与 universe 为准，报告仅作研究参考。
