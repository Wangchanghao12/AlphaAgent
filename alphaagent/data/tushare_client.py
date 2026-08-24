#!/usr/bin/env python3
"""
Tushare 客户端
- 优先使用 REST 代理（TUSHARE_REST_URL + TUSHARE_API_KEY，GET + X-API-Key 头）
- 未配置 REST 时退回 SDK 模式（TUSHARE_TOKEN + TUSHARE_HTTP_URL）
- 网络超时 / 限流等可恢复错误自动重试（指数退避）
"""

from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

import pandas as pd
import requests
import tushare as ts
import urllib3
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"

T = TypeVar("T")

DEFAULT_HTTP_URL = "https://api.tushare.pro"
DEFAULT_REST_URL = "https://pcd.mobcvb.cn/tushare/pro"

RETRYABLE_NETWORK_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
    TimeoutError,
    ConnectionResetError,
    ConnectionAbortedError,
    ConnectionRefusedError,
    BrokenPipeError,
)

# Linux: EPIPE / ECONNRESET / ETIMEDOUT / ECONNREFUSED
_RETRYABLE_ERRNOS = {32, 104, 110, 111}

# Tushare 限流 / 临时性 API 报错关键词
# 注意：tushare 常把底层网络错误包装成 Exception(str/tuple)，需靠文案匹配
RETRYABLE_API_MARKERS = (
    "最多访问",
    "请稍后再试",
    "频繁",
    "限流",
    "timeout",
    "timed out",
    "连接",
    "繁忙",
    "connection aborted",
    "connection reset",
    "connection refused",
    "remotely closed",
    "remote end closed",
    "broken pipe",
    "temporarily unavailable",
    "gateway",
    "502",
    "503",
    "504",
)

_config: dict[str, float | int] = {
    "max_retries": int(os.getenv("TUSHARE_MAX_RETRIES", "5")),
    "timeout": int(os.getenv("TUSHARE_TIMEOUT", "60")),
    "retry_base_delay": float(os.getenv("TUSHARE_RETRY_BASE_DELAY", "2.0")),
    "retry_max_delay": float(os.getenv("TUSHARE_RETRY_MAX_DELAY", "120.0")),
}


def configure(
    *,
    max_retries: int | None = None,
    timeout: int | None = None,
    retry_base_delay: float | None = None,
    retry_max_delay: float | None = None,
) -> None:
    """覆盖 Tushare 重试 / 超时配置（供 CLI 或脚本调用）。"""
    if max_retries is not None:
        _config["max_retries"] = max_retries
    if timeout is not None:
        _config["timeout"] = timeout
    if retry_base_delay is not None:
        _config["retry_base_delay"] = retry_base_delay
    if retry_max_delay is not None:
        _config["retry_max_delay"] = retry_max_delay


def _read_token() -> str:
    """从 .env 或环境变量读取 token。"""
    load_dotenv(ENV_FILE)
    token = os.getenv("TUSHARE_TOKEN", "")
    return token.strip().strip('"').strip("'")


def _read_http_url() -> str:
    """读取兼容 Tushare DataApi 的网关地址。"""
    load_dotenv(ENV_FILE)
    url = os.getenv("TUSHARE_HTTP_URL", DEFAULT_HTTP_URL)
    return url.strip().strip('"').strip("'").rstrip("/")


def _read_rest_config() -> tuple[str, str]:
    """读取 REST 代理配置，返回 (url, api_key)；未配置则返回空字符串。"""
    load_dotenv(ENV_FILE)
    url = os.getenv("TUSHARE_REST_URL", "").strip().strip('"').strip("'").rstrip("/")
    key = os.getenv("TUSHARE_API_KEY", "").strip().strip('"').strip("'")
    return url, key


def _exception_text(exc: BaseException) -> str:
    parts = [str(exc), repr(exc)]
    if getattr(exc, "args", None):
        parts.append(" ".join(str(a) for a in exc.args))
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if isinstance(cause, BaseException):
        parts.append(_exception_text(cause))
    return " ".join(parts).lower()


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, RETRYABLE_NETWORK_ERRORS):
        return True
    if isinstance(exc, OSError) and getattr(exc, "errno", None) in _RETRYABLE_ERRNOS:
        return True
    msg = _exception_text(exc)
    return any(marker in msg for marker in RETRYABLE_API_MARKERS)


def _retry_delay(attempt: int) -> float:
    base = float(_config["retry_base_delay"])
    cap = float(_config["retry_max_delay"])
    delay = min(cap, base * (2**attempt))
    # 轻微抖动，避免并发任务同一时刻重试
    return delay + random.uniform(0, min(1.0, delay * 0.1))


def call_with_retry(
    func: Callable[..., T],
    *args: Any,
    label: str | None = None,
    **kwargs: Any,
) -> T:
    """对单次 Tushare 调用做指数退避重试。"""
    max_retries = int(_config["max_retries"])
    name = label or getattr(func, "__name__", "tushare")
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt >= max_retries or not _is_retryable(exc):
                raise
            delay = _retry_delay(attempt)
            print(
                f"  [retry {attempt + 1}/{max_retries}] {name}: {exc}，"
                f"{delay:.1f}s 后重试",
                flush=True,
            )
            time.sleep(delay)

    assert last_exc is not None
    raise last_exc


class _RestClient:
    """REST 代理客户端：GET {base_url}/{api_name}?params + X-API-Key 头。

    接口与 Tushare SDK pro_api 兼容：``client.daily(trade_date=...)``
    等价于 ``client.query('daily', trade_date=...)``，可被 _RetryingPro 包装。
    """

    def __init__(self, base_url: str, api_key: str, *, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._session = requests.Session()
        self._session.headers["X-API-Key"] = api_key

    def query(self, api_name: str, fields: str = "", **params: Any) -> pd.DataFrame:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        if fields:
            clean["fields"] = fields
        resp = self._session.get(
            f"{self.base_url}/{api_name}",
            params=clean,
            verify=False,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"{api_name} REST error: {payload.get('msg')}")
        data = payload.get("data") or {}
        return pd.DataFrame(data.get("items") or [], columns=data.get("fields"))

    def __getattr__(self, name: str) -> Any:
        """将 client.daily(trade_date=...) 路由到 self.query('daily', ...)。"""
        if name.startswith("_"):
            raise AttributeError(name)

        def _method(fields: str = "", **kwargs: Any) -> pd.DataFrame:
            return self.query(name, fields=fields, **kwargs)

        return _method


class _RetryingPro:
    """包装 Tushare pro_api，为各接口调用注入重试。"""

    def __init__(self, pro: Any) -> None:
        self._pro = pro

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._pro, name)
        if not callable(attr):
            return attr

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return call_with_retry(attr, *args, label=name, **kwargs)

        return wrapper


def get_pro():
    """初始化并返回 Tushare 客户端（带自动重试）。

    优先使用 REST 模式（TUSHARE_REST_URL + TUSHARE_API_KEY）；
    未配置时退回 SDK 模式（TUSHARE_TOKEN + TUSHARE_HTTP_URL）。
    """
    timeout = int(_config["timeout"])
    max_retries = int(_config["max_retries"])

    rest_url, api_key = _read_rest_config()
    if rest_url and api_key:
        client: Any = _RestClient(rest_url, api_key, timeout=timeout)
        return client if max_retries <= 0 else _RetryingPro(client)

    # 退回 SDK 模式
    token = _read_token()
    if not token:
        raise ValueError(
            f"未找到 Tushare 凭据。请在 {ENV_FILE} 中配置 "
            "TUSHARE_REST_URL + TUSHARE_API_KEY（REST 模式）"
            "或 TUSHARE_TOKEN（SDK 模式）"
        )
    ts.set_token(token)
    pro = ts.pro_api(timeout=timeout)
    pro._DataApi__http_url = _read_http_url()
    return pro if max_retries <= 0 else _RetryingPro(pro)
