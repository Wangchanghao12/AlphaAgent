#!/usr/bin/env python3
"""清理 mining registry 里的孤儿记录（registry 有、factorlib 无的因子）。

背景：registry(json) 与 factorlib(memmap) 可能不同步——某些因子只有 registry 条目、
factorlib 里没有对应值（如从别处拷贝/合并 registry 带进来的幽灵记录）。这些因子
本套数据算不出来，batch 评估会报列缺失。

本脚本只删 registry 里 factorlib 不存在的记录，**不动 factorlib 的真实因子**。
默认 dry-run（只列出），加 --apply 才真正删除；删除前会备份 registry。

用法:
  uv run python scripts/clean_registry_orphans.py                     # 只列出孤儿
  uv run python scripts/clean_registry_orphans.py --apply             # 真正删除
  uv run python scripts/clean_registry_orphans.py --apply --no-backup # 不备份
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="清理 mining registry 孤儿记录")
    p.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "artifacts/factorzoo/stock_1d/mining_delivered_registry.json",
    )
    p.add_argument(
        "--factorlib",
        type=Path,
        default=ROOT / "artifacts/factorzoo/stock_1d",
    )
    p.add_argument("--apply", action="store_true", help="真正删除（默认 dry-run 只列出）")
    p.add_argument("--no-backup", action="store_true", help="删除前不备份 registry")
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    from alphaagent.factor.mining.registry_io import load_mining_registry, save_mining_registry
    from alphaagent.factor.zoo import FactorZoo

    registry_path = Path(args.registry).expanduser().resolve()
    if not registry_path.is_file():
        print(f"错误：registry 不存在 {registry_path}", file=sys.stderr)
        return 1

    registry = load_mining_registry(registry_path)
    zoo = FactorZoo.open(args.factorlib)
    zoo_ids = set(zoo.catalog.list_factor_ids())
    orphans = sorted(set(registry.keys()) - zoo_ids)

    print(f"registry 记录: {len(registry)} | factorlib 实际因子: {len(zoo_ids)}")
    print(f"孤儿(registry有、factorlib无): {len(orphans)}")
    for o in orphans:
        src = registry[o].get("source", "?")
        ts = str(registry[o].get("ingested_at", ""))[:10]
        print(f"  - {o}  (source={src}, ingested={ts})")

    if not orphans:
        print("\n没有孤儿记录，无需清理。")
        return 0

    if not args.apply:
        print("\n[ dry-run ] 未删除。加 --apply 才真正删除这些孤儿 registry 记录。")
        return 0

    # 备份
    if not args.no_backup:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        bak = registry_path.with_name(f"{registry_path.stem}.bak_{stamp}{registry_path.suffix}")
        shutil.copy2(registry_path, bak)
        print(f"\n已备份 registry -> {bak}")

    for o in orphans:
        del registry[o]
    save_mining_registry(registry_path, registry)
    print(f"已删除 {len(orphans)} 个孤儿记录。factorlib 的 {len(zoo_ids)} 个真实因子未动。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())