"""股票因子挖掘评估上下文：panel 路径与 train/val 日期切分。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from alphaagent.factor.types import DEFAULT_LABEL_COL


@dataclass
class StockEvalContext:
    """一次挖掘会话的数据与标签配置。"""

    panel_path: Path
    train_start: str = "2019-01-01"
    train_end: str = "2021-12-31"
    val_start: str = "2022-01-01"
    val_end: str = "2024-12-31"
    holdout_start: str | None = None
    """最终 OOS 窗（如 2025-01-01~2026-07-31）；submit 时按自然年拆分复检，最近一年为门槛、更早年份为参考。None 表示不启用。"""
    holdout_end: str | None = None
    label_col: str = DEFAULT_LABEL_COL
    include_fundamentals: bool = True
    """是否载入基本面列（``funda_*``）。挖价量因子时可关闭以省内存。"""
    columns: tuple[str, ...] | None = None
    """只载入这些列（lane 化内存优化）；None 载入全量。始终隐含 label_col。"""

    def split_range(self, split: str) -> tuple[str, str]:
        if split == "train":
            return self.train_start, self.train_end
        if split == "val":
            return self.val_start, self.val_end
        if split == "holdout":
            if not self.holdout_start or not self.holdout_end:
                raise ValueError("holdout 未配置 holdout_start/holdout_end")
            return self.holdout_start, self.holdout_end
        raise ValueError(f"未知 split: {split!r}")

    def coverage_range(self) -> tuple[str, str]:
        """train ∪ val ∪ holdout 日期并集。"""
        starts = [self.train_start, self.val_start]
        ends = [self.train_end, self.val_end]
        if self.holdout_start and self.holdout_end:
            starts.append(self.holdout_start)
            ends.append(self.holdout_end)
        return min(starts), max(ends)
