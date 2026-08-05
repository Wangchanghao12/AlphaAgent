"""列丢失预检：防止 fetch/build 重建时静默丢掉 factorlib 已用到的列。

问题背景：`fetch_fundamentals.py` 不带 ``--with-statements`` 重跑，会把
`quarterly.parquet` 里三大表（``funda_fs_*``）列覆盖掉；`build_panel.py`
同理。若 factorlib 里已有因子引用了这些列，重建后这些因子将无法复现，
且 n_rows 不变时不会触发 realign，静默脱节。

本模块在覆盖前做一次对比：factorlib 因子用到的 ``$列`` vs 操作后仍存在的列，
有缺失就亮警告并列出受影响因子（只警告，不阻止、不减少数据）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Set

_COL_REF_RE = re.compile(r"\$([A-Za-z0-9_]+)")


def factorlib_referenced_columns(factorlib_path: Path | str) -> dict[str, set[str]]:
    """返回 ``{column: {factor_id, ...}}``：factorlib 所有因子 expr 引用的 ``$列``。"""
    from alphaagent.factor.zoo import FactorZoo

    zoo = FactorZoo.open(factorlib_path)
    out: dict[str, set[str]] = {}
    for fid in zoo.catalog.list_factor_ids():
        meta = zoo.catalog.get(fid)
        if meta is None or not meta.expr:
            continue
        for col in _COL_REF_RE.findall(meta.expr):
            out.setdefault(col, set()).add(fid)
    return out


def statement_columns_from_module() -> set[str]:
    """三大表(income/balancesheet/cashflow)会生成的 ``funda_fs_*`` 列名集合。

    用于判断"不带 --with-statements 重跑会丢掉哪些列"。只读本模块里的列映射，
    不以某个具体缓存为准。
    """
    from alphaagent.data import fundamental_fetch as ff

    cols: set[str] = set()
    for spec in ff.STATEMENT_SPECS:
        cols.update(spec.column_map.values())
    return cols


def warn_factorlib_columns_lost(
    factorlib_path: Path | str,
    *,
    available_columns: Set[str],
    context: str = "该操作",
) -> list[str]:
    """对比 factorlib 用到的列 vs ``available_columns`` 中仍存在的列。

    Args:
        factorlib_path: factorzoo 根目录。
        available_columns: 操作后仍会存在的列名集合。
        context: 用于警告文案的操作描述。

    Returns:
        缺失（将被丢失）的列名列表。缺失时打印警告，但**不抛异常、不阻止操作**。
    """
    refs = factorlib_referenced_columns(factorlib_path)
    if not refs:
        return []
    avail = set(available_columns)
    missing = sorted(c for c in refs if c not in avail)
    if missing:
        print("[警告] " + "-" * 70)
        print(f"[警告] {context} 后，以下 {len(missing)} 个 factorlib 用到的列将不存在：")
        for c in missing:
            fids = sorted(refs[c])
            shown = "、".join(fids[:8]) + ("…" if len(fids) > 8 else "")
            print(f"[警告]   - {c}   被 {len(fids)} 个因子引用: {shown}")
        print("[警告] 这些因子将无法复现。若需保留，请补全数据（如带 --with-statements）后再重建。")
        print("[警告] " + "-" * 70)
    return missing