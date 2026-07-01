"""增量 realign 测试。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from seekalpha.data.panel import slice_panel
from seekalpha.factor import FactorZoo, ingest_factor, init_library
from seekalpha.factor.zoo.index import verify_index_prefix_stable
from seekalpha.factor.zoo.realign import (
    incremental_realign_factorlib_to_panel,
    list_append_boundary_old_n,
    overlap_row_ids,
    verify_overlap_exact,
)


def _init_lib(panel, tmp_path: Path) -> Path:
    lib_root = tmp_path / "factorzoo"
    init_library(
        lib_root,
        panel=panel,
        panel_path=tmp_path / "panel.parquet",
        n_sample_rows=min(10, len(panel)),
        max_factors=8,
    )
    return lib_root


def test_verify_index_prefix_stable_append(mini_panel, tmp_path):
    old = slice_panel(mini_panel, start="2024-01-02", end="2024-01-04")
    lib_root = _init_lib(old, tmp_path)
    zoo = FactorZoo.open(lib_root)
    from seekalpha.factor.zoo.realign import _candidate_rows_from_panel

    new_rows = _candidate_rows_from_panel(mini_panel)
    assert verify_index_prefix_stable(zoo.index.rows, new_rows, len(old))


def test_incremental_realign_matches_full_tail(mini_panel, tmp_path):
    old = slice_panel(mini_panel, start="2024-01-02", end="2024-01-04")
    lib_root = _init_lib(old, tmp_path)
    zoo = FactorZoo.open(lib_root)
    ingest_factor(
        zoo,
        factor_id="ret_factor",
        name="ret",
        expr="$ret",
        panel=old.sort_index(),
    )

    info = incremental_realign_factorlib_to_panel(
        lib_root,
        panel=mini_panel.sort_index(),
        panel_path=tmp_path / "panel.parquet",
        warmup_days=240,
        warmup_retry_days=480,
    )
    assert info["mode"] == "incremental"
    assert info["incremental_factors"] == ["ret_factor"]
    assert info["fallback_factors"] == []

    zoo_inc = FactorZoo.open(lib_root)
    inc_vals = zoo_inc.read_factor("ret_factor")

    lib_full = tmp_path / "factorzoo_full"
    init_library(
        lib_full,
        panel=mini_panel,
        panel_path=tmp_path / "panel.parquet",
        n_sample_rows=min(10, len(mini_panel)),
        max_factors=8,
    )
    zoo_full = FactorZoo.open(lib_full)
    ingest_factor(
        zoo_full,
        factor_id="ret_factor",
        name="ret",
        expr="$ret",
        panel=mini_panel.sort_index(),
    )
    full_vals = zoo_full.read_factor("ret_factor")

    old_n = len(old)
    assert np.allclose(inc_vals[:old_n], zoo.read_factor("ret_factor"), equal_nan=True)
    assert np.allclose(inc_vals[old_n:], full_vals[old_n:], equal_nan=True)


def test_incremental_fallback_on_prefix_mismatch(mini_panel, tmp_path):
    old = slice_panel(mini_panel, start="2024-01-02", end="2024-01-04")
    lib_root = _init_lib(old, tmp_path)
    zoo = FactorZoo.open(lib_root)
    ingest_factor(
        zoo,
        factor_id="ret_factor",
        name="ret",
        expr="$ret",
        panel=old.sort_index(),
    )

    # 在旧日期段插入新 instrument，破坏 index 前缀
    import pandas as pd

    insert = mini_panel.iloc[[0]].copy()
    insert.index = pd.MultiIndex.from_tuples(
        [(pd.Timestamp("2024-01-02"), "NEW.XX")],
        names=["datetime", "instrument"],
    )
    tail = slice_panel(mini_panel, start="2024-01-05", end="2024-01-08")
    broken = pd.concat([old, insert, tail]).sort_index()

    info = incremental_realign_factorlib_to_panel(
        lib_root,
        panel=broken,
        panel_path=tmp_path / "panel.parquet",
    )
    assert info["mode"] == "full"
    assert info.get("fallback_reason") == "index_prefix_unstable"


def test_list_append_boundary_old_n(mini_panel):
    from seekalpha.factor.zoo.index import _panel_to_index_frame, build_row_index
    from seekalpha.factor.zoo.realign import list_append_boundary_old_n

    rows = build_row_index(_panel_to_index_frame(mini_panel))
    points = list_append_boundary_old_n(rows, append_trade_days=[1, 2])
    assert points
    assert all(0 < p["old_n"] < p["new_n"] for p in points)


def test_probe_incremental_at_old_n(mini_panel, tmp_path):
    old = slice_panel(mini_panel, start="2024-01-02", end="2024-01-04")
    lib_root = _init_lib(mini_panel, tmp_path)
    zoo = FactorZoo.open(lib_root)
    ingest_factor(
        zoo,
        factor_id="ret_factor",
        name="ret",
        expr="$ret",
        panel=mini_panel.sort_index(),
    )
    pt = list_append_boundary_old_n(zoo.index.rows, append_trade_days=[2])[0]
    from seekalpha.factor.zoo.realign import probe_incremental_realign_at_old_n

    result = probe_incremental_realign_at_old_n(
        zoo,
        mini_panel.sort_index(),
        old_n=int(pt["old_n"]),
    )
    assert result["incremental_factors"] == ["ret_factor"]
    assert result["fallback_factors"] == []


def test_overlap_row_ids_last_k_days(mini_panel):
    import pandas as pd

    from seekalpha.factor.zoo.index import _panel_to_index_frame, build_row_index

    rows = build_row_index(_panel_to_index_frame(mini_panel))
    old_n = len(slice_panel(mini_panel, start="2024-01-02", end="2024-01-04"))
    update_start = pd.Timestamp(rows.iloc[old_n]["datetime"])

    ids, verify_start = overlap_row_ids(
        rows,
        old_n=old_n,
        update_start=update_start,
        overlap_verify_days=2,
    )
    dt = pd.to_datetime(rows.loc[rows["row_id"].isin(ids), "datetime"])
    unique_days = sorted(dt.unique())
    assert len(unique_days) <= 2
    assert all(pd.Timestamp(d) < update_start for d in unique_days)
    assert pd.Timestamp(unique_days[0]) >= verify_start


def test_verify_overlap_exact_nan_and_finite():
    import pandas as pd

    stored = np.array([1.0, np.nan, 2.0], dtype=np.float32)
    computed = np.array([1.0, np.nan, 3.0], dtype=np.float32)
    rows = __import__("pandas").DataFrame(
        {
            "row_id": [0, 1, 2],
            "datetime": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "instrument": ["A", "A", "A"],
        }
    )
    ok, rep = verify_overlap_exact(stored, computed, np.array([0, 1, 2]), index_rows=rows)
    assert not ok
    assert rep["n_mismatch"] == 1

    ok2, _ = verify_overlap_exact(stored, computed, np.array([0, 1]), index_rows=rows)
    assert ok2
