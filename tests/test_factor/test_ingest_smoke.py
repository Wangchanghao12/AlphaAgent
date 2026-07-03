"""因子入库 smoke 测试。"""

from pathlib import Path

from alphaagent.factor import ingest_factor, load_registry

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "configs" / "factors" / "registry.example.json"


def test_registry_loads(mini_factorlib):
    reg = load_registry(REGISTRY, repo_root=ROOT)
    assert "ret_factor" in reg
    assert reg["ret_factor"]["expression"] == "$ret"


def test_ingest_ret_factor(mini_factorlib, mini_panel):
    zoo = mini_factorlib
    reg = load_registry(REGISTRY, repo_root=ROOT)
    spec = reg["ret_factor"]
    result = ingest_factor(
        zoo,
        factor_id="ret_factor",
        name=str(spec["name"]),
        expr=str(spec["expression"]),
        panel=mini_panel.sort_index(),
    )
    assert result.stored, result.skipped_reason
    assert zoo.catalog.get("ret_factor") is not None
