"""仓库路径常量。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = ROOT / "artifacts"
PANEL_PATH = ARTIFACTS_DIR / "panel" / "panel_1d.parquet"
FACTORZOO_DIR = ARTIFACTS_DIR / "factorzoo" / "stock_1d"
FACTOR_EXPR_DIR = FACTORZOO_DIR / "expressions"
CONFIGS_DIR = ROOT / "configs"
FACTOR_REGISTRY_EXAMPLE = CONFIGS_DIR / "factors" / "registry.example.json"
MLS_FMB_PERCENTILES_PATH = FACTORZOO_DIR / "mls_fmb_percentiles.json"
MINING_REGISTRY_PATH = FACTORZOO_DIR / "mining_delivered_registry.json"
MINING_EXPR_DIR = FACTOR_EXPR_DIR
