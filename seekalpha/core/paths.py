"""仓库路径常量。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = ROOT / "artifacts"
PANEL_PATH = ARTIFACTS_DIR / "panel" / "panel_1d.parquet"
FACTORZOO_DIR = ARTIFACTS_DIR / "factorzoo" / "stock_1d"
CONFIGS_DIR = ROOT / "configs"
FACTOR_REGISTRY_EXAMPLE = CONFIGS_DIR / "factors" / "registry.example.json"
