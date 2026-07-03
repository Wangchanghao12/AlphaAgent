"""factor 测试 fixtures。"""

from __future__ import annotations

import pytest

from alphaagent.factor import FactorZoo, init_library


@pytest.fixture
def mini_factorlib(tmp_path, mini_panel):
    lib_root = tmp_path / "factorzoo"
    init_library(
        lib_root,
        panel=mini_panel,
        n_sample_rows=min(10, len(mini_panel)),
        max_factors=8,
    )
    return FactorZoo.open(lib_root, verify_hash=True)
