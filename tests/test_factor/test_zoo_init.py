"""factorzoo 初始化测试。"""

from seekalpha.factor import init_library
from seekalpha.factor.zoo import FactorZoo


def test_init_library(mini_panel, tmp_path):
    lib = tmp_path / "lib"
    _, manifest, index = init_library(
        lib,
        panel=mini_panel,
        n_sample_rows=10,
        max_factors=4,
    )
    assert manifest.n_rows == len(mini_panel)
    assert len(index.rows) == len(mini_panel)
    zoo = FactorZoo.open(lib)
    assert zoo.n_factors == 0
