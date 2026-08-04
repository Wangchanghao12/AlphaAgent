"""挖掘 lane 目录：把因子空间切成"主维度 + 控制列"，供多进程并行时各挖各的。

每个 lane 声明：
- ``primary_columns``：该 lane 的**主信号维度**所需列（支持 ``funda_*`` 通配符）。
- ``control_columns``：允许做**中性化 / 增强**的控制列（市值、流动性等），
  但**不得当作首要信号源** —— 这样既避免多进程重复挖掘，又不牺牲混合因子
  （如"低波动+动量""价值+动量""市值中性化后的动量"）。
- ``prompt_addendum``：注入 system prompt 的软约束文本。

内存上每个进程只加载 ``主列 + 控制列``（远小于全量 panel），由 ``columns`` 属性合并。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# --- 各 lane 共享的必需列（DSL 求值 / 对齐 / 标签都依赖） ---
_COMMON = (
    "adj_close",
    "ret",
    "vwap",
)

# --- 各 lane 允许的中性化 / 增强控制列（市值、流动性；不得作首要信号源） ---
_CONTROL = (
    "float_cap",
    "tot_cap",
    "turnover_rate",
    "volume_ratio",
    "amount",
    "volume",
)

# --- 各 lane 的主信号维度列 ---
_MOMENTUM_PRIMARY = (*_COMMON, "open", "high", "low", "close", "adj_open", "adj_high", "adj_low")
_VOLATILITY_PRIMARY = (*_COMMON, "open", "high", "low")
_VOLUME_PRIMARY = (*_COMMON, "volume", "amount", "turnover_rate", "turnover_rate_f", "volume_ratio", "float_cap", "tot_cap", "float_share", "free_share")
_FUNDAMENTAL_PRIMARY = (*_COMMON, "funda_*")  # 通配符在加载时展开为所有 funda_* 列
_WEEKLY_PRIMARY = (*_COMMON, "open", "high", "low", "close")
_CROSSSECTIONAL_PRIMARY = (*_COMMON, "float_cap", "tot_cap", "turnover_rate")


@dataclass(frozen=True)
class MiningLane:
    name: str
    title: str
    primary_columns: tuple[str, ...]
    control_columns: tuple[str, ...] = _CONTROL
    include_fundamentals: bool = False
    prompt_addendum: str = ""
    seed_exprs: tuple[str, ...] = field(default_factory=tuple)

    @property
    def columns(self) -> tuple[str, ...]:
        """加载用列 = 主列 + 控制列（去重）。"""
        return tuple(dict.fromkeys((*self.primary_columns, *self.control_columns)))


_LANES: dict[str, MiningLane] = {
    "momentum": MiningLane(
        name="momentum",
        title="价格动量与均值回归",
        primary_columns=_MOMENTUM_PRIMARY,
        prompt_addendum=(
            "首要信号必须来自**价格动量 / 均值回归**维度："
            "用 open/high/low/close/adj_* 的 TS 动量、反转、加速度、乖离等算子。"
            "允许用 float_cap/tot_cap/turnover_rate/volume_ratio/amount/volume 做市值/流动性中性化或增强，"
            "但不得把它们当作首要信号源。"
        ),
    ),
    "volatility": MiningLane(
        name="volatility",
        title="波动与风险",
        primary_columns=_VOLATILITY_PRIMARY,
        prompt_addendum=(
            "首要信号必须来自**波动 / 风险**维度："
            "用 close/high/low/ret 的已实现波动、下行波动、极差、峰谷等算子。"
            "允许用 float_cap/tot_cap/turnover_rate/volume_ratio/amount/volume 做市值/流动性中性化或增强，"
            "但不得把它们当作首要信号源。"
        ),
    ),
    "volume": MiningLane(
        name="volume",
        title="量价与流动性",
        primary_columns=_VOLUME_PRIMARY,
        prompt_addendum=(
            "首要信号必须来自**量价 / 流动性**维度："
            "用 volume/amount/turnover_rate/float_cap/tot_cap 的换手、量比、资金流、流动性等算子。"
            "允许用 ret/adj_close 派生价格动量或波动做增强，但不得把纯价格动量当首要信号源。"
        ),
    ),
    "fundamental": MiningLane(
        name="fundamental",
        title="基本面财务",
        primary_columns=_FUNDAMENTAL_PRIMARY,
        include_fundamentals=True,
        prompt_addendum=(
            "首要信号必须来自**基本面财务**维度："
            "用各种 funda_* 财务指标（funda_roe/roa/…/funda_days_* 披露日历）构建价值、盈利、成长、质量因子。"
            "允许把 adj_close/ret 的价格动量/波动作为次级增强信号，或与 float_cap/tot_cap 做市值中性化；"
            "但因子主导信号必须来自基本面。"
        ),
    ),
    "weekly": MiningLane(
        name="weekly",
        title="周线结构",
        primary_columns=_WEEKLY_PRIMARY,
        prompt_addendum=(
            "首要信号必须来自**周线结构**维度："
            "用 close/high/low/ret 通过 @1w 周线重采样构建周度动量、周内模式、周线突破等算子。"
            "允许用 float_cap/tot_cap/turnover_rate/volume_ratio/amount/volume 做市值/流动性中性化或增强，"
            "但不得把它们当作首要信号源。"
        ),
    ),
    "crosssectional": MiningLane(
        name="crosssectional",
        title="截面与市值中性化",
        primary_columns=_CROSSSECTIONAL_PRIMARY,
        prompt_addendum=(
            "首要信号必须来自**截面 / 市值中性化**维度："
            "用 adj_close/ret 结合 float_cap/tot_cap/turnover_rate 做截面标准化、市值中性化、残差化。"
            "允许用 volume/amount/volume_ratio 做流动性增强，但不得把基本面当首要信号源。"
        ),
    ),
}


def lane_names() -> list[str]:
    return sorted(_LANES)


def get_lane(name: str) -> MiningLane:
    key = name.strip().lower()
    lane = _LANES.get(key)
    if lane is None:
        raise KeyError(f"未知 lane: {name!r}（可用：{', '.join(lane_names())}）")
    return lane


def lanes_for(names: Iterable[str]) -> list[MiningLane]:
    return [get_lane(n) for n in names]


def build_lane_prompt_addendum(lane: MiningLane) -> str:
    """把 lane 的主/控制列白名单 + 约束合成一段可追加进 system prompt 的文本。"""
    primary = ", ".join(lane.primary_columns)
    control = ", ".join(lane.control_columns)
    all_cols = ", ".join(lane.columns)
    return (
        f"【本会话赛道：{lane.name}】{lane.prompt_addendum}\n"
        f"主维度可用列：{primary}。\n"
        f"控制/中性化列（不得作首要信号源）：{control}。\n"
        f"本会话可用列合计：{all_cols}。DSL 表达式只准引用这些列。"
    ).strip()