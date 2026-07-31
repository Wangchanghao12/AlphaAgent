"""Tushare 客户端测试（不调用 API）。"""

import os

import pytest
import requests


def test_token_from_env(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_abc")
    from alphaagent.data import tushare_client

    # 重新加载模块内逻辑
    assert tushare_client._read_token() == "test_token_abc"


def test_http_url_from_env(monkeypatch):
    monkeypatch.setenv("TUSHARE_HTTP_URL", "https://tushare.example.com/")
    from alphaagent.data import tushare_client

    assert tushare_client._read_http_url() == "https://tushare.example.com"


def test_get_pro_sets_token_and_http_url(monkeypatch):
    from alphaagent.data import tushare_client

    class FakePro:
        pass

    fake_pro = FakePro()
    seen: dict[str, object] = {}
    monkeypatch.setattr(tushare_client, "_read_token", lambda: "temporary-token")
    monkeypatch.setattr(tushare_client, "_read_http_url", lambda: "https://gateway.example.com")
    monkeypatch.setattr(tushare_client.ts, "set_token", lambda token: seen.update(token=token))
    monkeypatch.setattr(
        tushare_client.ts,
        "pro_api",
        lambda **kwargs: (seen.update(kwargs=kwargs) or fake_pro),
    )
    tushare_client.configure(max_retries=0, timeout=45)

    result = tushare_client.get_pro()

    assert result is fake_pro
    assert seen == {"token": "temporary-token", "kwargs": {"timeout": 45}}
    assert fake_pro._DataApi__http_url == "https://gateway.example.com"


def test_token_missing_raises(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    from alphaagent.data.tushare_client import _read_token, get_pro

    # 清空 .env 影响：若 .env 存在仍可能有 token，仅测 get_pro 无 token 分支
    monkeypatch.setattr(
        "alphaagent.data.tushare_client._read_token",
        lambda: "",
    )
    with pytest.raises(ValueError, match="TUSHARE_TOKEN"):
        get_pro()


def test_is_retryable_network_error():
    from alphaagent.data.tushare_client import _is_retryable

    assert _is_retryable(requests.exceptions.ConnectionError("timed out"))
    assert _is_retryable(TimeoutError("timed out"))
    assert _is_retryable(Exception("抱歉，您每分钟最多访问该接口500次"))
    # tushare 常把 Connection reset 包装成普通 Exception
    assert _is_retryable(
        Exception(("Connection aborted.", ConnectionResetError(104, "Connection reset by peer")))
    )
    assert _is_retryable(ConnectionResetError(104, "Connection reset by peer"))


def test_is_not_retryable_auth_error():
    from alphaagent.data.tushare_client import _is_retryable

    assert not _is_retryable(Exception("token invalid"))


def test_call_with_retry_recovers(monkeypatch):
    from alphaagent.data import tushare_client

    tushare_client.configure(max_retries=3, retry_base_delay=0.0, retry_max_delay=0.0)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.exceptions.ConnectionError("Read timed out.")
        return "ok"

    assert tushare_client.call_with_retry(flaky, label="flaky") == "ok"
    assert calls["n"] == 3


def test_call_with_retry_exhausts(monkeypatch):
    from alphaagent.data import tushare_client

    tushare_client.configure(max_retries=2, retry_base_delay=0.0, retry_max_delay=0.0)

    def always_fail():
        raise requests.exceptions.Timeout("timeout")

    with pytest.raises(requests.exceptions.Timeout):
        tushare_client.call_with_retry(always_fail, label="always_fail")
