# 挖掘离线总结（人工维护）

> **给 agent 注入用**：编辑 [`mining_user_discovery.txt`](mining_user_discovery.txt)（discovery cycle 会自动 `--user-file` 传入）。
> 本文件供人读、留档；改完 lessons 后同步更新 `.txt` 里对应段落。

## 写入位置

| 文件 | 用途 |
|------|------|
| `configs/mining_user_discovery.txt` | **挖掘 agent 实际读取**（`--user-file`） |
| `configs/mining_lessons.md` | 人类可读归档 + 更新说明（本文件） |
| `artifacts/mining_runs/<run_id>/report.md` | 每轮 cycle 自动生成的机器报告 |

## 如何重新跑挖掘

```bash
# 循环跑直到 SmartX effective（飞书 webhook 放 .env: FEISHU_WEBHOOK_URL）
nohup python scripts/run_discovery_until_effective.py \
  --vnpy-root /mnt/recom/develop/wangchanghao/rtp_fg/em_ak/em_ak/examples/alpha_research \
  --alpha-python /root/miniconda3/envs/vn311py/bin/python \
  --vnpy-python /root/miniconda3/envs/vn311py/bin/python \
  >> log/discovery_until.log 2>&1 &

# 单轮 cycle（推荐调试，已默认带 user-file）
python scripts/run_discovery_cycle.py \
  --vnpy-root /mnt/recom/develop/wangchanghao/rtp_fg/em_ak/em_ak/examples/alpha_research \
  --alpha-python /root/miniconda3/envs/vn311py/bin/python \
  --vnpy-python /root/miniconda3/envs/vn311py/bin/python

# 仅挖掘（手动指定总结文件）
bash scripts/run_factor_mining_parallel.sh \
  --user-file configs/mining_user_discovery.txt \
  --label-col label_5d_close_to_close \
  --train-start 2010-01-01 --train-end 2020-12-31 \
  --val-start 2021-01-01 --val-end 2022-12-31 \
  --holdout-start 2023-01-01 --holdout-end 2023-12-31
```

## 历史轮次摘要

### 20260904 — 未通过 SmartX

- Gate：6/6 通过
- SmartX：ΔRet -4.53pp，ΔSharpe -0.271
- 分年：2024 +0.066 / 2025 -0.618 / 2026 -0.316（ΔSharpe）
- 因子族：Amihud、隔夜-日内、quiet 低波
- 结论：gate 与组合 alpha 脱节；2025 regime 失效

### 近失轮（3 因子）— 未通过 SmartX（差 0.005）

- Gate：3/3 通过
- SmartX：ΔRet +11.31pp，ΔSharpe +0.264
- 分年：2024 +0.618 / 2025 **-0.105** / 2026 +0.166（ΔSharpe）
- 结论：有 alpha，稳定性规则卡在 2025（-0.105 vs -0.10 下限）

## 更新原则

1. 只写**机制级**教训（饱和族、regime 弱点、与 Alpha158 重叠），不写「继续挖 factor_x 变体」。
2. 每轮 cycle 结束后把 `report.md` 要点追加到本文件，并**同步改** `mining_user_discovery.txt` 顶部「离线总结」段。
3. 保留最近 2–3 轮细节即可，更早轮次压缩成一行，避免 agent 路径依赖。
