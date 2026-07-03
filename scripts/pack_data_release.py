#!/usr/bin/env python3
"""把 market / fundamental / industry 三类原始 parquet 缓存打成可上传（百度云等）的数据包。

产出 staging 目录（解压即对齐仓库 artifacts/ 布局）+ MANIFEST.json（sha256 校验）+ 双语 README。
他人下载解压到仓库根后，一条离线命令即可从零重构完整 panel：
  uv run python scripts/build_panel.py --with-fundamentals --with-industry

示例:
  uv run python scripts/pack_data_release.py
  uv run python scripts/pack_data_release.py --zip
  uv run python scripts/pack_data_release.py --out-dir dist --name alphaagent-data-20260703
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alphaagent.core.paths import (  # noqa: E402
    DISCLOSURE_CALENDAR_PATH,
    FUNDAMENTAL_QUARTERLY_PATH,
    INDEX_DIR,
    INDUSTRY_SW_PATH,
    MARKET_HQ_PATH,
)

# (源文件, 包内相对路径, 是否必需)
_ENTRIES: list[tuple[Path, str, bool]] = [
    (MARKET_HQ_PATH, "artifacts/market/daily_hq.parquet", True),
    (FUNDAMENTAL_QUARTERLY_PATH, "artifacts/fundamental/quarterly.parquet", True),
    (DISCLOSURE_CALENDAR_PATH, "artifacts/fundamental/disclosure_calendar.parquet", True),
    (INDUSTRY_SW_PATH, "artifacts/industry/sw_l1_membership.parquet", True),
]


def _entries() -> list[tuple[Path, str, bool]]:
    """静态必需项 + 动态发现的指数成分缓存（artifacts/index/*_members.parquet，可选）。"""
    entries = list(_ENTRIES)
    if INDEX_DIR.is_dir():
        for src in sorted(INDEX_DIR.glob("*_members.parquet")):
            entries.append((src, f"artifacts/index/{src.name}", False))
    return entries

_README = """# AlphaAgent open data ({stamp})

Pre-built **raw parquet caches** for the AlphaAgent factor-research
framework (CSI 1000 universe, 2015-01 ~ 2026-06). This package lets you rebuild the full
daily panel **offline** — no Tushare token required after download.

**AlphaAgent 开源数据包**：中证1000成分并集、2015-01 至 2026-06 的原始 parquet 缓存。
下载解压后无需 Tushare token 即可离线重构完整 panel。

| File | Rows (approx.) | Description |
|------|----------------|-------------|
| `market/daily_hq.parquet` | ~6.3M | OHLCV, adj factor, cap, ST flags, daily_basic (turnover, PE/PB/PS, shares, …) |
| `fundamental/quarterly.parquet` | — | Quarterly financials (PIT-aligned) |
| `fundamental/disclosure_calendar.parquet` | — | Earnings disclosure dates |
| `industry/sw_l1_membership.parquet` | — | Shenwan L1 industry (PIT) |
| `index/000852_SH_members.parquet` | — | ZZ1000 monthly constituent snapshots |

Total uncompressed size: see `MANIFEST.json`. Verify integrity with sha256 before use.

## Contents

```
artifacts/
  market/daily_hq.parquet            # daily OHLC/vol/amount/adjfactor/mktcap/ST + daily_basic indicators (turnover/pe/pb/ps/dv/shares)
  fundamental/quarterly.parquet      # quarterly financial indicators
  fundamental/disclosure_calendar.parquet
  industry/sw_l1_membership.parquet  # SW L1 industry membership (PIT)
  index/<code>_members.parquet       # index constituents monthly snapshots (optional)
```

## Restore

**Prerequisites:** clone the AlphaAgent repo, run `uv sync`.

1. Extract this package into the repo root so that `artifacts/market`,
   `artifacts/fundamental`, `artifacts/industry`, and `artifacts/index` are populated.
2. Rebuild the panel offline:

   ```bash
   uv run python scripts/build_panel.py --with-fundamentals --with-industry
   ```

   This reads only the local caches and writes `artifacts/panel/panel_1d.parquet`.
3. (Optional) verify file integrity against `MANIFEST.json` (sha256).
4. Rebuild the factor library from Git-tracked DSL:

   ```bash
   uv run python scripts/init_factorlib.py
   uv run python scripts/ingest_factors.py --expr-dir artifacts/factorzoo/stock_1d/expressions
   ```

The factor memmap (`artifacts/factorzoo`) is **not** included in this package.

## Data source / disclaimer

Data is derived from Tushare Pro. Redistribution is subject to Tushare's terms;
this package is provided for research use only, without warranty.

---

# AlphaAgent 开源数据（{stamp}）

**AlphaAgent 开源数据包**：中证1000（ZZ1000）成分并集、2015-01 至 2026-06 的原始 parquet 缓存。
下载解压到**仓库根目录**后，无需 Tushare token 即可离线重构完整 panel（约 626 万行 × 127 列）。

## 内容

```
artifacts/
  market/daily_hq.parquet            # 日频行情 hq（量价/复权因子/市值/ST + daily_basic 每日指标：换手/pe/pb/ps/股息/股本）
  fundamental/quarterly.parquet      # 季频财务指标
  fundamental/disclosure_calendar.parquet
  industry/sw_l1_membership.parquet  # 申万一级行业成员（PIT）
  index/<code>_members.parquet       # 指数成分股按月快照（可选，仅用于复现拉取范围）
```

## 重构步骤

**前置：** clone AlphaAgent 仓库并 `uv sync`。

1. 解压到仓库根，使 `artifacts/market`、`artifacts/fundamental`、`artifacts/industry`、`artifacts/index` 就位。
2. 离线重建 panel：

   ```bash
   uv run python scripts/build_panel.py --with-fundamentals --with-industry
   ```

   仅读本地缓存，写出 `artifacts/panel/panel_1d.parquet`。
3. （可选）用 `MANIFEST.json` 的 sha256 校验文件完整性。
4. 从 Git 中的 DSL 重建因子库 memmap：

   ```bash
   uv run python scripts/init_factorlib.py
   uv run python scripts/ingest_factors.py --expr-dir artifacts/factorzoo/stock_1d/expressions
   ```

因子 memmap（`artifacts/factorzoo`）**不含**在本数据包内。

## 数据来源 / 免责声明

数据派生自 Tushare Pro，再分发须遵守 Tushare 条款；本数据包仅供研究使用，不作任何担保。
"""


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _parquet_num_rows(path: Path) -> int | None:
    try:
        import pyarrow.parquet as pq

        return pq.read_metadata(path).num_rows
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="打包原始 parquet 缓存为可分发数据包")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "dist", help="staging 输出根目录")
    parser.add_argument(
        "--name",
        type=str,
        default=f"alphaagent-data-{date.today():%Y%m%d}",
        help="数据包目录名",
    )
    parser.add_argument("--zip", action="store_true", help="额外打成 .zip 压缩包")
    args = parser.parse_args()

    entries = _entries()
    missing = [str(src) for src, _, required in entries if required and not src.is_file()]
    if missing:
        raise SystemExit(
            "缺少必需的缓存文件:\n  "
            + "\n  ".join(missing)
            + "\n请先运行 scripts/fetch_market.py 与 scripts/fetch_fundamentals.py 生成缓存。"
        )

    stage = args.out_dir / args.name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    manifest: dict = {
        "name": args.name,
        "generated": date.today().isoformat(),
        "files": [],
    }

    for src, rel, _ in entries:
        if not src.is_file():
            continue
        dst = stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        entry = {
            "path": rel,
            "bytes": dst.stat().st_size,
            "sha256": _sha256(dst),
        }
        n_rows = _parquet_num_rows(dst)
        if n_rows is not None:
            entry["num_rows"] = n_rows
        manifest["files"].append(entry)
        print(f"  + {rel}  ({entry['bytes'] / 1e6:.1f} MB)")

    (stage / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (stage / "README.md").write_text(
        _README.format(stamp=manifest["generated"]), encoding="utf-8"
    )

    total_mb = sum(e["bytes"] for e in manifest["files"]) / 1e6
    print(f"数据包已生成: {stage}  (共 {len(manifest['files'])} 个文件, {total_mb:.1f} MB)")

    if args.zip:
        archive = shutil.make_archive(str(stage), "zip", root_dir=stage.parent, base_dir=args.name)
        print(f"压缩包: {archive}  ({Path(archive).stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
