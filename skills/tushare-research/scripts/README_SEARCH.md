# 网络搜索模块

本模块提供 A 股投研过程中的网络信息搜索和验证功能。

## 文件结构

```
scripts/
├── kimi_search.py              # 核心搜索模块（多后端支持）
├── web_search.py               # 统一搜索接口（股票/行业/公司）
└── auto_verification_framework.py  # 自动验证框架
```

## 配置

### 必需配置

```bash
# Moonshot API Key（推荐）
export MOONSHOT_API_KEY="sk-xxx"
```

### 备选配置

```bash
# Brave Search API
export BRAVE_API_KEY="xxx"

# SearXNG 实例
export SEARXNG_URL="https://searx.example.com"
```

**注意：** DuckDuckGo 无需配置，但可能受网络限制。

## 使用方法

### 1. 命令行搜索

```bash
# 通用搜索
python3 kimi_search.py "贵州茅台 股票"

# 测试完整功能
python3 web_search.py
```

### 2. Python 调用

```python
from kimi_search import kimi_search, moonshot_search
from web_search import search_news, search_industry, search_company_info

# 通用搜索
results = kimi_search("贵州茅台 2024 年报", limit=5)
for r in results:
    print(f"{r['title']}: {r['url']}")

# 搜索股票新闻
news = search_news("600519", "贵州茅台", limit=10)

# 搜索行业信息
industry = search_industry("白酒", limit=5)

# 搜索公司信息
info = search_company_info("宁德时代", info_type="competitors")
```

### 3. 自动验证

```python
from auto_verification_framework import AutoVerificationFramework

framework = AutoVerificationFramework()

report_data = {
    'financials': {'revenue': 1000000000, 'net_profit': 200000000},
    'news': [{'title': '贵州茅台发布 2024 年业绩预告', 'date': '2024-01-15'}],
    'valuation': {'pe': 25.5, 'pb': 6.8},
    'report_date': '2024-01-20',
}

report = framework.run_full_verification(
    stock_code='600519',
    stock_name='贵州茅台',
    report_data=report_data
)

print(f"验证通过：{report['summary']['pass']}/{report['summary']['total']}")
print(f"整体置信度：{report['confidence']:.2f}")
```

## API 说明

### kimi_search(query, limit=5, include_content=False)

通用搜索接口，自动降级选择可用后端。

**参数：**
- `query`: 搜索关键词
- `limit`: 返回结果数量（1-10）
- `include_content`: 是否包含完整内容

**返回：**
```python
[
    {
        'title': '标题',
        'url': '链接',
        'snippet': '摘要',
        'content': '完整内容'  # 如果 include_content=True
    }
]
```

### search_news(stock_code, stock_name, limit=10)

搜索股票相关新闻。

### search_industry(industry, limit=5)

搜索行业分析信息。

### search_company_info(company_name, info_type="general", limit=5)

搜索公司信息。

**info_type 选项：**
- `general`: 公司简介
- `competitors`: 竞争对手
- `products`: 主要产品
- `financial`: 财务状况

## 后端优先级

1. **Moonshot API** - 智能搜索，支持中文理解（推荐）
2. **Brave Search API** - 高质量搜索结果
3. **DuckDuckGo** - 无需 API key
4. **SearXNG** - 自建搜索引擎

## 依赖安装

```bash
# 基础依赖
pip install requests

# DuckDuckGo 搜索（可选）
pip install duckduckgo-search
```

## 故障排查

### 问题：搜索无结果

**检查：**
1. 环境变量是否正确配置
2. 网络连接是否正常
3. API key 是否有效

```bash
# 检查环境变量
echo $MOONSHOT_API_KEY

# 测试 Moonshot API
curl -X POST https://api.moonshot.cn/v1/chat/completions \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"moonshot-v1-8k","messages":[{"role":"user","content":"test"}]}'
```

### 问题：Moonshot API 返回错误

**可能原因：**
- API key 无效或过期
- 余额不足
- 请求频率过高

**解决：**
1. 检查 API key 是否正确
2. 登录 Moonshot 控制台查看余额
3. 降低请求频率或添加重试逻辑

## 示例输出

```
搜索：贵州茅台 股票

1. 贵州茅台：2024 年净利润预计增长 18%
   https://example.com/news/123456
   贵州茅台发布业绩预告，预计 2024 年实现净利润...

2. 白酒行业分析：高端酒市场持续增长
   https://example.com/analysis/789012
   2024 年白酒行业整体表现稳健，高端酒企...
```

## 注意事项

1. **API 配额**：Moonshot API 有请求限制，建议合理使用
2. **结果缓存**：频繁搜索相同关键词时，考虑添加缓存层
3. **数据时效**：网络搜索结果可能有时效性，注意验证
4. **错误处理**：生产环境请添加完善的错误处理和重试逻辑
