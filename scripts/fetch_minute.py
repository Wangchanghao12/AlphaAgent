#!/usr/bin/env python3
"""从 stockdb HTTP 服务批量拉取分钟K并落盘为按日分区 parquet。

数据语义（已验证）：
- volume/amount 为分钟增量，全天求和与日k完全一致；
- 首根 bar(09:30) 含集合竞价成交；尾盘 14:57-14:59 为零量占位 bar，
  收盘集合竞价成交计入 15:00 bar（全天 241 根）；
- 原始价，不含复权信息（跨日收益类特征需另行拼 adjfactor）。

输出 schema（artifacts/minute/stock_1m/{YYYYMMDD}.parquet）：
    datetime(timestamp) 索引按 (instrument, datetime) 排序，列：
    date(int YYYYMMDDHHMMSS), code(6位), instrument(ts_code),
    open/high/low/close(float32), volume/amount(int64)

股票池默认取本地 artifacts/index/ 的中证1000成分快照并集（离线可用，
不连 Tushare）；也可用 --codes/--codes-file 显式指定。

服务器用法（stockdb 部署于 /mnt/recom/develop/wangchanghao/rtp_fg/stockdb）：
  # 方式A：纯 HTTP（零依赖，默认）
  uv run python scripts/fetch_minute.py \
      --host http://172.16.196.223:8299 \
      --start 2025-01-01 --end 2026-08-19 --workers 16

  # 方式B：stockdb 二进制 SDK 的 rd.pipe() 管道批量（快约一个量级）
  #   前提：releases 的 manylinux 包里的 stockdb 二进制在 PYTHONPATH/工作目录
  uv run python scripts/fetch_minute.py --probe-sdk \
      --sdk-host 172.16.196.223 --sdk-port 8299   # 先探测
  uv run python scripts/fetch_minute.py --backend sdk \
      --sdk-host 172.16.196.223 --sdk-port 8299 \
      --start 2025-01-01 --end 2026-08-19 --pipe-batch 500

  # 数据一致性抽查（分钟和 vs 日k）
  uv run python scripts/fetch_minute.py --check 20

  # 增量补最新交易日：重跑同命令即可（已有日期文件默认跳过）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alphaagent.core.paths import ARTIFACTS_DIR, PANEL_PATH  # noqa: E402

DEFAULT_HOST = "http://127.0.0.1:8299"
DEFAULT_OUT = ARTIFACTS_DIR / "minute" / "stock_1m"
MINUTE_FIELDS = ("open", "high", "low", "close", "volume", "amount")
RETRIES = 3
FLUSH_EVERY_TASKS = 60  # 每累计 N 个任务结果落一次盘


# ---------------------------------------------------------------------------
# stockdb HTTP 客户端
# ---------------------------------------------------------------------------
def stockdb_get(host: str, key_pattern: str, *, timeout: float = 60.0) -> list[dict]:
    """GET cmd=get&t={key_pattern}，返回记录 dict 列表（单条命中时服务端返回 dict）。"""
    url = f"{host}/?{urllib.parse.urlencode({'cmd': 'get', 't': key_pattern})}"
    last_exc: Exception | None = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload is None:  # 高并发下服务偶发返回 null，视为可重试瞬时故障
                raise RuntimeError("server returned null")
            if isinstance(payload, dict):
                if "error" in payload:  # 业务错误 {"error": ...}
                    raise RuntimeError(f"stockdb error: {payload['error']}")
                return [payload]  # 精确命中单条记录
            return [rec for _, rec in payload]
        except Exception as exc:  # noqa: BLE001 网络/解析统一重试
            last_exc = exc
            if attempt + 1 < RETRIES:
                time.sleep(min(10.0, 1.5 * (2**attempt)))
    assert last_exc is not None
    raise last_exc


def to_instrument(code: str) -> str:
    """6 位代码 → Tushare ts_code（与 panel instrument 一致）。"""
    code = code.zfill(6)
    if code[0] in ("6", "9"):
        return f"{code}.SH"
    if code[0] in ("4", "8"):
        return f"{code}.BJ"
    return f"{code}.SZ"


def _records_to_df(records: list[dict], code: str) -> pd.DataFrame:
    """分钟 bar 记录列表 → 标准 schema DataFrame（HTTP/SDK 共用）。"""
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame.from_records(records, columns=MINUTE_FIELDS)
    df["date"] = np.array([int(r["date"]) for r in records], dtype=np.int64)
    df["datetime"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d%H%M%S")
    df["code"] = code
    df["instrument"] = to_instrument(code)
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype(np.float32)
    for c in ("volume", "amount"):
        df[c] = df[c].astype(np.int64)
    cols = ["datetime", "date", "code", "instrument", *MINUTE_FIELDS]
    return df[cols]


def fetch_code_month(host: str, code: str, yyyymm: str) -> pd.DataFrame:
    """拉取单股单月全部分钟 bar（HTTP 后端）。"""
    return _records_to_df(stockdb_get(host, f"分钟k:{code}:{yyyymm}*"), code)


# ---------------------------------------------------------------------------
# stockdb 二进制 SDK 后端（rd.pipe 管道批量，快约一个量级）
# ---------------------------------------------------------------------------
def _normalize_mget_result(items, code: str) -> list[dict]:
    """pipe.mget 返回归一为 dict 列表（兼容 dict / [key,val] 列表两种形态）。"""
    if isinstance(items, dict):
        return [items]
    if isinstance(items, list):
        out = []
        for it in items:
            if isinstance(it, dict):
                out.append(it)
            elif isinstance(it, (list, tuple)) and len(it) > 1 and isinstance(it[1], dict):
                out.append(it[1])
        return out
    return []


def sdk_connect(args: argparse.Namespace):
    """导入 stockdb 二进制模块并连接（本地服务或远程部署）。"""
    try:
        from stockdb import init  # noqa: PLC0415 manylinux 包里的二进制模块
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "缺少 stockdb 二进制模块。部署方法：\n"
            "  1) 下载 releases 的 manylinux 包（free-stockdb-manylinux-x64-*.tar）\n"
            "  2) 把包内 pybao/stockdb.abi3.so 拷到本脚本目录或加入 PYTHONPATH\n"
            "  3) 重跑 --probe-sdk\n"
            "或者直接用 HTTP 后端（零依赖）：不加 --backend sdk 即可"
        ) from exc

    rd = init(host=args.sdk_host, port=args.sdk_port, password=args.sdk_password)
    if rd is None:
        from stockdb import rd as rd_default  # noqa: PLC0415

        rd = rd_default
    return rd


def sdk_probe(args: argparse.Namespace) -> int:
    """小样本探测 SDK 连通性、pipe 批量与通配符语义，通过后再跑全量。"""
    t0 = time.perf_counter()
    rd = sdk_connect(args)
    print(f"connect ok ({time.perf_counter() - t0:.2f}s) host={args.sdk_host}:{args.sdk_port}")

    codes = [c.strip() for c in (args.codes or "600000,000001").split(",") if c.strip()]
    yyyymm = pd.Timestamp(args.end).strftime("%Y%m")

    # 单条同步 vals
    single = list(rd.vals("分钟k", codes[0], f"{yyyymm}*"))
    print(f"rd.vals 单股月查询: {codes[0]} {yyyymm} → {len(single)} 条")
    if not single:
        print("WARN: 单股查询为空，检查数据覆盖/端口")
        return 1

    # pipe 批量（同 stock_sdk.py 内部用法：pp.mget(table, code, time_query) + pp.do()）
    pp = rd.pipe()
    for c in codes:
        pp.mget("分钟k", c, f"{yyyymm}*")
    raw = _pipe_do(pp)
    if not isinstance(raw, list):
        raw = [raw]
    for c, items in zip(codes, raw):
        recs = _normalize_mget_result(items, c)
        print(f"pipe.mget {c} {yyyymm} → {len(recs)} 条")
        if not recs:
            print(f"WARN: pipe 返回形态异常: {str(items)[:200]}")
            return 1
    print(f"probe 通过（{time.perf_counter() - t0:.2f}s），可用 --backend sdk 拉全量")
    return 0


def _chunked(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _pipe_do(pp):
    """执行 pipe：同步 pp.do() 优先；若返回 awaitable（async 版 SDK）则 asyncio.run。"""
    raw = pp.do() if hasattr(pp, "do") else pp
    if asyncio.iscoroutine(raw) or hasattr(raw, "__await__"):
        raw = asyncio.run(raw)
    return raw


def run_fetch_sdk(args: argparse.Namespace, codes: list[str], months: list[str]) -> int:
    """SDK 后端：pipe 批量拉取，主线程落盘（无跨线程 HTTP，吞吐更高）。"""
    start_int = int(args.start.replace("-", ""))
    end_int = int(args.end.replace("-", ""))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rd = sdk_connect(args)
    tasks = [(c, m) for c in codes for m in months]
    batches = list(_chunked(tasks, args.pipe_batch))
    print(
        f"fetch_minute[sdk]: {len(codes)} 股 × {len(months)} 月 = {len(tasks)} 查询, "
        f"pipe 批 {len(batches)} × {args.pipe_batch} ({args.start} ~ {args.end})"
    )

    t0 = time.perf_counter()
    stats = {"queries": 0, "empty": 0, "rows": 0}
    bar_counts: dict[int, int] = {}

    for bi, batch in enumerate(batches, start=1):
        pp = rd.pipe()
        for c, m in batch:
            pp.mget("分钟k", c, f"{m}*")
        raw = _pipe_do(pp)
        if not isinstance(raw, list):
            raw = [raw]

        buffer: dict[int, list[pd.DataFrame]] = {}
        for (c, m), items in zip(batch, raw):
            stats["queries"] += 1
            recs = _normalize_mget_result(items, c)
            if not recs:
                stats["empty"] += 1
                continue
            df = _records_to_df(recs, c)
            day = df["date"] // 1_000_000
            df = df[(day >= start_int) & (day <= end_int)]
            for n in df.groupby(day).size():
                bar_counts[int(n)] = bar_counts.get(int(n), 0) + 1
            for d, part in df.groupby(day):
                buffer.setdefault(int(d), []).append(part)

        for day, parts in sorted(buffer.items()):
            chunk = pd.concat(parts)
            n = _merge_write_day(out_dir, day, chunk, force=args.force)
            stats["rows"] += len(chunk)
            if args.verbose:
                print(f"  flush {day}.parquet +{len(chunk):,} 行 (total={n:,})", flush=True)

        if bi % 10 == 0 or bi == len(batches):
            elapsed = time.perf_counter() - t0
            rate = stats["queries"] / max(elapsed, 1e-6)
            eta = (len(tasks) - stats["queries"]) / max(rate, 1e-6)
            print(
                f"  [{stats['queries']}/{len(tasks)}] rows={stats['rows']:,} "
                f"{rate:.0f} q/s elapsed={_format_elapsed(elapsed)} eta={_format_elapsed(eta)}",
                flush=True,
            )

    print(
        f"\n完成: {stats['queries']} 查询, {stats['rows']:,} 行, empty={stats['empty']}, "
        f"elapsed={_format_elapsed(time.perf_counter() - t0)}"
    )
    if bar_counts:
        dist = ", ".join(f"{k}根:{v}" for k, v in sorted(bar_counts.items()))
        print(f"每日 bar 数分布(股×日): {dist}（预期 241，偏离项建议 --check 抽查）")
    print(f"分区目录: {out_dir.resolve()} ({len(existing_days(out_dir))} 个交易日)")
    return 0


# ---------------------------------------------------------------------------
# 股票池解析
# ---------------------------------------------------------------------------
def instruments_from_panel(panel_path: Path, start: str, end: str) -> list[str]:
    """从已有 panel 提取 [start, end] 区间内出现过的 instrument（只读索引，不占内存）。

    适用无 Tushare 权限环境：池子 = 现有因子管线的股票池（中证1000 成分并集）。
    """
    p = Path(panel_path)
    if not p.is_file():
        raise SystemExit(f"panel 不存在: {p}（--universe panel 需要已有 panel）")
    idx = pd.read_parquet(p, columns=[]).index
    if "instrument" not in (idx.names or []):
        raise SystemExit(f"panel 索引缺 instrument 层: {idx.names}")
    dt = idx.get_level_values("datetime")
    mask = (dt >= pd.Timestamp(start)) & (dt <= pd.Timestamp(end))
    return sorted(set(idx.get_level_values("instrument")[mask]))


def resolve_universe(args: argparse.Namespace) -> list[str]:
    """返回 6 位代码列表（已去重排序）。--extra-codes/--extra-codes-file 与基础池取并集。"""
    extra: list[str] = []
    if args.extra_codes:
        extra += [s.strip() for s in args.extra_codes.split(",") if s.strip()]
    if args.extra_codes_file:
        extra += Path(args.extra_codes_file).read_text(encoding="utf-8").splitlines()

    if args.codes:
        raw = [s.strip() for s in args.codes.split(",") if s.strip()]
    elif args.codes_file:
        raw = Path(args.codes_file).read_text(encoding="utf-8").splitlines()
    elif args.universe == "none":
        raw = []
    elif args.universe == "panel":
        ts_codes = instruments_from_panel(args.panel, args.start, args.end)
        if not ts_codes:
            raise SystemExit("panel 在指定区间无数据")
        print(f"股票池来源: panel {Path(args.panel).name} → {len(ts_codes)} 只")
        raw = ts_codes
    else:
        from alphaagent.data.index_members import load_index_members, members_union

        cache = load_index_members(args.universe)
        ts_codes = members_union(cache, args.start, args.end) if not cache.empty else []
        if not ts_codes:
            # 缓存缺失/未覆盖：联网 Tushare 按月拉 index_weight 快照并持久化
            print(f"成分缓存缺失，从 Tushare 拉取 {args.universe} 月快照（需 .env 配置 token）...")
            from alphaagent.data.index_members import resolve_index_members_cached

            ts_codes = resolve_index_members_cached(args.universe, args.start, args.end)
        if not ts_codes:
            raise SystemExit(f"无法解析 {args.universe} 成分，可用 --codes/--codes-file 显式指定")
        raw = ts_codes

    codes = sorted({s.split(".")[0].zfill(6) for s in raw if s.strip()} | {s.split(".")[0].zfill(6) for s in extra if s.strip()})
    if not codes:
        raise SystemExit("股票池为空")
    if extra:
        print(f"已并入额外代码 {len({s.split('.')[0] for s in extra if s.strip()})} 个 → 合计 {len(codes)} 只")
    return codes


# ---------------------------------------------------------------------------
# 落盘（按日分区，合并写保证乱序/重入幂等）
# ---------------------------------------------------------------------------
def day_path(out_dir: Path, day: int) -> Path:
    return out_dir / f"{day}.parquet"


def _merge_write_day(out_dir: Path, day: int, chunk: pd.DataFrame, *, force: bool) -> int:
    path = day_path(out_dir, day)
    if path.is_file() and not force:
        old = pd.read_parquet(path)
        merged = pd.concat([old, chunk])
        merged = merged.drop_duplicates(subset=["instrument", "datetime"], keep="last")
    else:
        merged = chunk.drop_duplicates(subset=["instrument", "datetime"], keep="last")
    merged = merged.sort_values(["instrument", "datetime"]).reset_index(drop=True)
    tmp = path.with_suffix(".parquet.tmp")
    merged.to_parquet(tmp, index=False)
    tmp.replace(path)
    return len(merged)


def existing_days(out_dir: Path) -> set[int]:
    if not out_dir.is_dir():
        return set()
    return {int(p.stem) for p in out_dir.glob("*.parquet") if p.stem.isdigit()}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def _month_range(start: str, end: str) -> list[str]:
    return [p.strftime("%Y%m") for p in pd.period_range(start, end, freq="M")]


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def run_fetch(args: argparse.Namespace) -> int:
    codes = resolve_universe(args)
    months = _month_range(args.start, args.end)
    start_int = int(args.start.replace("-", ""))
    end_int = int(args.end.replace("-", ""))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    have_days = set() if args.force else existing_days(out_dir)
    tasks = [(c, m) for c in codes for m in months]
    print(
        f"fetch_minute: {len(codes)} 股 × {len(months)} 月 = {len(tasks)} 请求 "
        f"({args.start} ~ {args.end}, workers={args.workers})"
    )
    if have_days:
        print(f"  已有 {len(have_days)} 个日期分区（--force 关闭时跳过其中完整月份）")

    t0 = time.perf_counter()
    buffer: dict[int, list[pd.DataFrame]] = {}
    stats = {"tasks": 0, "empty": 0, "failed": 0, "rows": 0}
    bar_counts: dict[int, int] = {}  # 每股每日 bar 数分布（数据质量监控）
    lock = threading.Lock()

    def flush_buffer() -> None:
        if not buffer:
            return
        for day, parts in sorted(buffer.items()):
            chunk = pd.concat(parts)
            n = _merge_write_day(out_dir, day, chunk, force=args.force)
            stats["rows"] += len(chunk)
            if args.verbose:
                print(
                    f"  flush {day}.parquet +{len(chunk):,} 行 (total={n:,}) "
                    f"elapsed={_format_elapsed(time.perf_counter() - t0)}",
                    flush=True,
                )
        buffer.clear()

    def handle(code: str, yyyymm: str, df: pd.DataFrame | None, exc: Exception | None) -> None:
        with lock:
            stats["tasks"] += 1
            if exc is not None:
                stats["failed"] += 1
                print(f"  WARN: {code} {yyyymm} 失败: {exc}", flush=True)
            elif df is None or df.empty:
                stats["empty"] += 1
            else:
                # 只保留 [start, end] 内的日期（月份请求会带出区间外的行）
                day = df["date"] // 1_000_000
                df = df[(day >= start_int) & (day <= end_int)]
                for n in df.groupby(day).size():
                    bar_counts[int(n)] = bar_counts.get(int(n), 0) + 1
                for d, part in df.groupby(day):
                    buffer.setdefault(int(d), []).append(part)
            if stats["tasks"] % 200 == 0 or stats["tasks"] == len(tasks):
                print(
                    f"  [{stats['tasks']}/{len(tasks)}] empty={stats['empty']} "
                    f"failed={stats['failed']} {_format_elapsed(time.perf_counter() - t0)}",
                    flush=True,
                )
            if stats["tasks"] % FLUSH_EVERY_TASKS == 0:
                flush_buffer()

    def pull(code: str, yyyymm: str) -> tuple[str, str, pd.DataFrame]:
        return code, yyyymm, fetch_code_month(args.host, code, yyyymm)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        inflight: dict = {}
        idx = 0
        while idx < len(tasks) or inflight:
            while idx < len(tasks) and len(inflight) < args.workers * 2:
                c, m = tasks[idx]
                inflight[pool.submit(pull, c, m)] = (c, m)
                idx += 1
            finished, _ = wait(inflight.keys(), return_when=FIRST_COMPLETED)
            for fut in finished:
                c, m = inflight.pop(fut)
                try:
                    _, _, df = fut.result()
                    handle(c, m, df, None)
                except Exception as exc:  # noqa: BLE001
                    handle(c, m, None, exc)

    flush_buffer()
    print(
        f"\n完成: {stats['tasks']} 请求, {stats['rows']:,} 新行, "
        f"empty={stats['empty']} failed={stats['failed']}, "
        f"elapsed={_format_elapsed(time.perf_counter() - t0)}"
    )
    if bar_counts:
        dist = ", ".join(f"{k}根:{v}" for k, v in sorted(bar_counts.items()))
        print(f"每日 bar 数分布(股×日): {dist}（预期 241，偏离项建议 --check 抽查）")
    print(f"分区目录: {out_dir.resolve()} ({len(existing_days(out_dir))} 个交易日)")
    if stats["failed"]:
        print(f"WARN: {stats['failed']} 个请求失败，重跑同命令可补齐")
        return 2
    return 0


def run_check(args: argparse.Namespace) -> int:
    """随机抽 N 个已落盘 (日期, 股票)，分钟和 vs 日k 交叉校验。"""
    out_dir = Path(args.out)
    days = sorted(existing_days(out_dir))
    if not days:
        print(f"{out_dir} 无分区文件，先执行拉取")
        return 1
    rng = random.Random(args.seed)
    bad = 0
    for _ in range(args.check):
        day = rng.choice(days)
        df = pd.read_parquet(day_path(out_dir, day))
        code = rng.choice(df["code"].unique())
        sub = df[df["code"] == code]
        daily = stockdb_get(args.host, f"日k:{code}:{day}*")
        if not daily:
            print(f"  {day} {code}: 日k 无数据，跳过")
            continue
        d0 = daily[0]
        ok_vol = abs(int(sub["volume"].sum()) - int(d0["volume"])) <= max(1e-3 * d0["volume"], 1e4)
        ok_amt = abs(int(sub["amount"].sum()) - int(d0["amount"])) <= max(1e-3 * d0["amount"], 1e6)
        ok_close = abs(float(sub.iloc[-1]["close"]) - float(d0["close"])) < 1e-6
        ok_bars = 241 <= len(sub) <= 242  # 正常 241 根；个别票含额外快照 bar
        flag = "OK" if (ok_vol and ok_amt and ok_close and ok_bars) else "MISMATCH"
        if flag != "OK":
            bad += 1
        print(
            f"  {day} {code}: bars={len(sub)} vol={ok_vol} amt={ok_amt} "
            f"close={ok_close} → {flag}"
        )
    return 1 if bad else 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="stockdb 分钟K → 按日分区 parquet")
    p.add_argument("--backend", choices=["http", "sdk"], default="http",
                   help="http=纯 HTTP 并发（默认）；sdk=stockdb 二进制 rd.pipe 批量")
    p.add_argument("--host", default=DEFAULT_HOST, help="stockdb HTTP 地址（http 后端）")
    p.add_argument("--sdk-host", default="127.0.0.1", help="stockdb 服务地址（sdk 后端）")
    p.add_argument("--sdk-port", type=int, default=8299, help="stockdb 服务端口（sdk 后端）")
    p.add_argument("--sdk-password", default="", help="stockdb 密码（默认空）")
    p.add_argument("--pipe-batch", type=int, default=500, help="每个 pipe 批的查询数（sdk 后端）")
    p.add_argument("--probe-sdk", action="store_true", help="小样本探测 SDK 连接/pipe 语义后退出")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="输出目录")
    p.add_argument("--start", default="2025-01-01", help="起始日 YYYY-MM-DD")
    p.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    p.add_argument("--universe", default="zz1000",
                   help="股票池：zz1000 等指数（成分缓存/Tushare）、panel（已有 panel 免联网）或 none（仅用显式代码）")
    p.add_argument("--panel", type=Path, default=PANEL_PATH, help="--universe panel 时的 panel 路径")
    p.add_argument("--codes", default=None, help="逗号分隔 6 位代码（覆盖 universe）")
    p.add_argument("--codes-file", type=Path, default=None, help="代码文件，每行一个（覆盖 universe）")
    p.add_argument("--extra-codes", default=None, help="逗号分隔 6 位代码，与基础池取并集")
    p.add_argument("--extra-codes-file", type=Path, default=None,
                   help="额外代码文件（与基础池取并集），如 configs/universe/hs300_cons_*.txt")
    p.add_argument("--workers", type=int, default=8, help="并发请求数（http 后端）")
    p.add_argument("--force", action="store_true", help="覆盖已有日期分区（默认合并去重）")
    p.add_argument("--verbose", action="store_true", help="打印每次落盘明细")
    p.add_argument("--check", type=int, default=0, metavar="N", help="随机抽 N 个 (日,股) 校验后退出")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    if args.probe_sdk:
        return sdk_probe(args)
    if args.check > 0:
        return run_check(args)
    if args.backend == "sdk":
        codes = resolve_universe(args)
        return run_fetch_sdk(args, codes, _month_range(args.start, args.end))
    return run_fetch(args)


if __name__ == "__main__":
    raise SystemExit(main())
