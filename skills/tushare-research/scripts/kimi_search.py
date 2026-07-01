#!/usr/bin/env python3
"""
Kimi Search 模块 - 基于 Moonshot API 的 $web_search 联网搜索

参考：https://platform.moonshot.cn/docs/guide/use-web-search

使用方式：
  1. 设置环境变量 MOONSHOT_API_KEY（在 https://platform.moonshot.cn 获取）
  2. pip install openai>=1.0
  3. from kimi_search import kimi_search
     results = kimi_search("奥海科技 元器件 政策 2025", limit=5)

模型选用 moonshot-v1-32k（32k 上下文，0.024元/1K tokens，避免 8k 超限）
"""
import os
import json
import re
import time
import warnings
from typing import List, Dict, Any, Optional

# Moonshot 返回 builtin_function 与 OpenAI SDK 期望的 function 类型不一致，触发 Pydantic 序列化警告，此处屏蔽
warnings.filterwarnings("ignore", message=".*Pydantic.*serializer.*", category=UserWarning)


# Moonshot 内置 web_search 工具声明
WEB_SEARCH_TOOL = {
    "type": "builtin_function",
    "function": {"name": "$web_search"},
}


def _search_impl(arguments: Dict[str, Any]) -> Any:
    """
    Moonshot $web_search 的实现：只需原封不动返回 arguments。
    平台会在服务端执行实际搜索，并将结果注入后续对话。
    参考：https://platform.moonshot.cn/docs/guide/use-web-search
    """
    return arguments


def kimi_search(query: str, limit: int = 5) -> List[Dict]:
    """
    使用 Moonshot API 的 $web_search 进行联网搜索。

    参数:
        query: 搜索关键词
        limit: 期望返回结果数量（模型会尽量返回相应数量）

    返回:
        列表，每项为 {"title": str, "url": str, "snippet": str}
        若 API 不可用则返回 []
    """
    api_key = os.getenv("MOONSHOT_API_KEY", "").strip()
    if not api_key:
        return []

    try:
        from openai import OpenAI
    except ImportError:
        print("kimi_search: 需要安装 openai>=1.0, 执行 pip install openai")
        return []

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.moonshot.cn/v1",
    )

    system_prompt = """你是搜索助手。你必须先调用$web_search工具执行搜索，获取结果后再返回JSON数组，每项含title、url、snippet、date。无链接用"#"。禁止只输出$web_search(...)文本而不调用工具。
重要：在得到完整满意的搜索答案前，不要结束（不要用stop）。若首次搜索结果不够充分或相关度不高，可多次调用$web_search换关键词或补充搜索，直到积累足够的高质量结果后再返回JSON，最多执行3轮。
date字段：必须从搜索结果中提取每条链接的发布时间/发表日期（格式如2025-03-15或2025年3月）。仅返回2025年及以后的政策/资讯，2024年及以前的不要返回。若无法获取日期则填"未知"。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请搜索「{query}」，获取约 {limit} 条最相关的结果。仅返回2025年及以后的政策/资讯，每条必须包含date（链接发布时间）和url（原文链接），返回 JSON 数组。"},
    ]

    max_iterations = 4
    max_retries = 3
    retry_delays = [5, 10, 20]

    for attempt in range(max_retries):
        try:
            return _do_kimi_search(client, messages, query, limit, max_iterations)
        except Exception as e:
            err_str = str(e).lower()
            # 429 过载、503 服务不可用、rate limit 等可重试
            if ('429' in err_str or 'overload' in err_str or '503' in err_str or
                'rate' in err_str or 'timeout' in err_str) and attempt < max_retries - 1:
                delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                if os.getenv("KIMI_DEBUG"):
                    print(f"kimi_search 重试 ({attempt + 1}/{max_retries})，{delay}s 后...")
                time.sleep(delay)
            else:
                print(f"kimi_search 错误: {e}")
                return []
    return []


def _do_kimi_search(client, messages, query, limit, max_iterations):
    """执行单次 Kimi 搜索（供重试调用）"""
    iterations = 0
    finish_reason = None
    final_content = ""

    while iterations < max_iterations:
        completion = client.chat.completions.create(
            model="kimi-k2-0905-preview",
            messages=messages,
            tools=[WEB_SEARCH_TOOL],
            tool_choice="auto",
            extra_body={"thinking": {"type": "disabled"}},
        )
        choice = completion.choices[0]
        finish_reason = choice.finish_reason
        msg = choice.message

        if finish_reason == "stop":
            final_content = (msg.content or "").strip()
            # 若模型只输出了工具调用文本而未实际调用，追加提示并继续
            if final_content and "$web_search" in final_content and "```json" not in final_content and "[" not in final_content[:50]:
                messages.append({"role": "assistant", "content": final_content})
                messages.append({"role": "user", "content": "请调用$web_search工具执行搜索（不要只输出文本），获取结果后返回```json [...]```格式的JSON数组。"})
                iterations += 1
                continue
            break

        if finish_reason == "tool_calls" and msg.tool_calls:
            messages.append(msg)
            for tc in msg.tool_calls:
                name = tc.function.name
                args_str = tc.function.arguments or "{}"
                try:
                    args = json.loads(args_str)
                except json.JSONDecodeError:
                    args = {}
                if name == "$web_search":
                    result = _search_impl(args)
                else:
                    result = args
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                })
        else:
            final_content = (msg.content or "").strip()
            break

        iterations += 1

    if os.getenv("KIMI_DEBUG"):
        print("=== final_content ===\n", repr(final_content[:800]), "\n=== end ===")
    return _parse_search_results(final_content, query, limit)


def _parse_search_results(content: str, query: str, limit: int) -> List[Dict]:
    """从模型返回内容中解析 title/url/snippet 结构"""
    if not content:
        return []

    # 尝试提取 JSON 数组（模型可能先输出 $web_search: ... 等前缀，再输出代码块）
    raw = content.strip()
    json_candidate = None

    # 1. 优先提取 ```json ... ``` 代码块（支持前有 preamble）
    m = re.search(r"```\s*json\s*\n(.*?)```", raw, re.DOTALL)
    if m:
        json_candidate = m.group(1).strip()
    else:
        # 2. 尝试 ``` ... ``` 无语言标识（内容以 [ 或 { 开头则视为 JSON）
        m = re.search(r"```\s*\n(.*?)```", raw, re.DOTALL)
        if m:
            extracted = m.group(1).strip()
            if extracted.startswith("[") or extracted.startswith("{"):
                json_candidate = extracted
        else:
            # 3. 退化为首尾去壳（适用于整体即 JSON 的情况）
            content = re.sub(r"^```\s*json?\s*", "", raw)
            content = re.sub(r"```\s*$", "", content).strip()
            if content.lstrip().startswith(("[", "{")):
                json_candidate = content

    content = json_candidate if json_candidate else raw

    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            results = []
            for item in parsed[:limit]:
                if isinstance(item, dict):
                    results.append({
                        "title": str(item.get("title", "无标题"))[:100],
                        "url": str(item.get("url", "#")).strip() or "#",
                        "snippet": str(item.get("snippet", ""))[:200],
                        "date": str(item.get("date", "未知")).strip() or "未知",
                    })
            return results
        if isinstance(parsed, dict):
            arr = parsed.get("results") or parsed.get("data") or parsed.get("items") or parsed.get("list")
            if isinstance(arr, list):
                return [
                    {
                        "title": str(x.get("title", "无标题"))[:100],
                        "url": str(x.get("url", "#")).strip() or "#",
                        "snippet": str(x.get("snippet", ""))[:200],
                        "date": str(x.get("date", "未知")).strip() or "未知",
                    }
                    for x in arr[:limit]
                    if isinstance(x, dict)
                ]
    except json.JSONDecodeError:
        pass

    # 解析失败时，尝试从 Markdown 链接提取
    # 格式: [标题](url) 或 * 标题: url
    link_pattern = r"\[([^\]]+)\]\((https?://[^\)]+)\)"
    matches = re.findall(link_pattern, content)
    if matches:
        return [
            {"title": t[:100], "url": u, "snippet": "", "date": "未知"}
            for t, u in matches[:limit]
        ]

    # 最终回退：返回单条概括
    return [{"title": f"搜索：{query}", "url": "#", "snippet": content[:300], "date": "未知"}]


if __name__ == "__main__":
    import sys

    query = sys.argv[1] if len(sys.argv) > 1 else "奥海科技 元器件 政策 2025"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    print(f"搜索：{query} (limit={limit})\n")
    results = kimi_search(query, limit=limit)

    if results:
        for i, r in enumerate(results, 1):
            print(f"{i}. {r['title']}")
            print(f"   URL: {r['url']}")
            if r.get("snippet"):
                print(f"   摘要: {r['snippet'][:80]}...")
            print()
        print(f"共 {len(results)} 条结果")
    else:
        print("未找到结果")
        print("\n请确认：")
        print("  1. 已设置环境变量 MOONSHOT_API_KEY")
        print("  2. 已安装 openai: pip install openai")
        print("  3. API Key 有效且有余额")
