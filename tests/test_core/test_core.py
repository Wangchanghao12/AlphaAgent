"""core 模块测试。"""

from seekalpha.core.config import load_yaml
from seekalpha.core.hash import panel_index_hash
from seekalpha.core.paths import ROOT


def test_root_exists():
    assert ROOT.is_dir()


def test_load_data_yaml():
    cfg = load_yaml("data.yaml")
    assert "panel" in cfg
    assert "tushare" in cfg


def test_panel_index_hash_stable(mini_panel):
    h1 = panel_index_hash(mini_panel)
    h2 = panel_index_hash(mini_panel)
    assert h1 == h2
    assert len(h1) == 16
