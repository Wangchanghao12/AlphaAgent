"""panel 行数变化时重建 factorlib index 并重算库内因子值。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from seekalpha.factor.types import DEFAULT_INGEST_POLICY, IngestPolicy
from seekalpha.factor.ingest import compute_ingest_metrics, prepare_stored_values
from seekalpha.factor.zoo import FactorStatus, FactorZoo, init_library
from seekalpha.factor.zoo.similarity import SimilarityMatrix
from seekalpha.factor.zoo.types import FactorMeta


def _resolve_panel_path(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def panel_paths_match(a: Path, b: Path) -> bool:
    return _resolve_panel_path(a) == _resolve_panel_path(b)


def _reset_similarity_matrix(zoo: FactorZoo) -> None:
    sim = SimilarityMatrix(zoo.paths, zoo.manifest.max_factors)
    if sim.matrix_path.is_file():
        sim.matrix_path.unlink()
    if sim.meta_path.is_file():
        sim.meta_path.unlink()


def _rebuild_similarity(zoo: FactorZoo) -> None:
    _reset_similarity_matrix(zoo)
    if zoo.n_factors == 0:
        return
    sim = SimilarityMatrix(zoo.paths, zoo.manifest.max_factors)
    for fid in zoo.catalog.list_factor_ids():
        meta = zoo.catalog.get(fid)
        if meta is None:
            continue
        values = zoo.read_factor(fid)
        sim.append_factor_correlations(
            zoo,
            factor_id=fid,
            col_idx=meta.col_idx,
            values=values,
        )


def _rematerialize_factor(
    zoo: FactorZoo,
    meta: FactorMeta,
    panel: pd.DataFrame,
    policy: IngestPolicy,
) -> None:
    values_path = zoo.paths.factor_values_path(meta.factor_id)
    if values_path.is_file():
        values_path.unlink()
    stored_values, expr, aux_tags, clip_extra = prepare_stored_values(meta.expr, panel, zoo, policy)
    metrics = compute_ingest_metrics(stored_values, panel, policy)
    extra = dict(meta.extra or {})
    extra.update({**clip_extra, "aux_tags": aux_tags, "metrics": metrics})
    zoo.overwrite_factor(
        factor_id=meta.factor_id,
        name=meta.name,
        expr=expr,
        values=stored_values,
        status=meta.status,
        extra=extra,
    )


def remask_factorlib(
    lib_root: Path,
    *,
    panel: pd.DataFrame,
    policy: IngestPolicy | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """对库内全部因子按 policy 重新物化、mask 并重算 extra.metrics。"""
    pol = policy or DEFAULT_INGEST_POLICY
    lib_root = Path(lib_root).expanduser().resolve()
    panel = panel.sort_index()
    zoo = FactorZoo.open(lib_root)
    remasked: list[str] = []
    for fid in zoo.catalog.list_factor_ids():
        meta = zoo.catalog.get(fid)
        if meta is None:
            continue
        remasked.append(fid)
        if dry_run:
            continue
        _rematerialize_factor(zoo, meta, panel, pol)
    if not dry_run and remasked:
        _rebuild_similarity(zoo)
    return {
        "remasked_factors": remasked,
        "n_factors": len(remasked),
        "dry_run": dry_run,
        "ingest_policy": pol.to_dict(),
    }


def realign_factorlib_to_panel(
    lib_root: Path,
    *,
    panel: pd.DataFrame,
    panel_path: Path,
    policy: IngestPolicy | None = None,
) -> dict[str, Any]:
    """同一 panel 路径下行数变化：重建 manifest/index，并重算全部已有因子 memmap。"""
    pol = policy or DEFAULT_INGEST_POLICY
    lib_root = Path(lib_root).expanduser().resolve()
    panel_path = _resolve_panel_path(panel_path)
    panel = panel.sort_index()

    zoo = FactorZoo.open(lib_root, verify_hash=False)
    old_n_rows = zoo.manifest.n_rows
    if len(panel) == old_n_rows:
        return {"realigned": False, "n_rows": old_n_rows}

    saved: list[FactorMeta] = []
    for fid in zoo.catalog.list_factor_ids():
        meta = zoo.catalog.get(fid)
        if meta is not None:
            saved.append(meta)

    init_library(
        lib_root,
        panel=panel,
        panel_path=panel_path,
        n_sample_rows=min(zoo.manifest.n_sample_rows, len(panel)),
        max_factors=zoo.manifest.max_factors,
        sample_seed=zoo.manifest.sample_seed,
    )

    zoo = FactorZoo.open(lib_root, verify_hash=True)
    _reset_similarity_matrix(zoo)

    rematerialized: list[str] = []
    for meta in sorted(saved, key=lambda m: m.col_idx):
        _rematerialize_factor(zoo, meta, panel, pol)
        rematerialized.append(meta.factor_id)

    _rebuild_similarity(zoo)

    return {
        "realigned": True,
        "old_n_rows": old_n_rows,
        "new_n_rows": len(panel),
        "panel_path": str(panel_path),
        "rematerialized_factors": rematerialized,
        "n_factors": len(rematerialized),
        "ingest_policy": pol.to_dict(),
    }
