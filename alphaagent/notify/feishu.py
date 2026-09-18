"""飞书群机器人 text 消息（webhook）。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def send_feishu_text(webhook: str, text: str, *, timeout: float = 15.0) -> str:
    """发送 text 消息。返回飞书 API 响应摘要；webhook 为空则跳过。"""
    if not webhook.strip():
        return "skipped:no_webhook"
    payload = json.dumps({"msg_type": "text", "content": {"text": text}}, ensure_ascii=False).encode(
        "utf-8"
    )
    req = urllib.request.Request(
        webhook.strip(),
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"飞书 HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"飞书请求失败: {exc}") from exc
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body[:200]
    if isinstance(parsed, dict) and parsed.get("code") not in (None, 0):
        raise RuntimeError(f"飞书返回错误: {parsed}")
    return "ok"
