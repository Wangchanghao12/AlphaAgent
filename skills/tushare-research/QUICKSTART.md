# Tushare Research - 快速入门

## 🚀 5 分钟上手

### 1. 配置环境变量

```bash
# 添加到 ~/.bashrc 或 ~/.zshrc
export TUSHARE_TOKEN="your_tushare_token"
export MOONSHOT_API_KEY="your_moonshot_key"

# 使配置生效
source ~/.bashrc
```

### 2. 安装依赖

```bash
cd /root/.openclaw/workspace/skills/tushare-research
pip install -r requirements.txt
```

### 3. 运行第一个投研报告

```bash
# 方法 1: 直接使用 Python
python3 scripts/research_report.py 600519

# 方法 2: 使用快捷脚本
./scripts/生成研报.sh 600519
```

报告将保存到：`/mnt/d/工作区/研报/贵州茅台_600519/`

### 4. 使用网络搜索

```bash
# 通用搜索
python3 scripts/kimi_search.py "贵州茅台 财报"

# 股票新闻
python3 scripts/web_search.py
```

## 📁 模块说明

| 模块 | 功能 | 输入 |
|------|------|------|
| `research_report.py` | 完整投研报告 | 股票代码 |
| `kimi_search.py` | 通用网络搜索 | 搜索关键词 |
| `web_search.py` | 股票/行业搜索 | 股票代码/行业名 |
| `auto_verification_framework.py` | 数据验证 | 报告数据 |

## 🔧 常见问题

**Q: 搜索无结果？**
- 检查 `MOONSHOT_API_KEY` 是否正确配置
- 测试：`echo $MOONSHOT_API_KEY`

**Q: Tushare 数据获取失败？**
- 检查 `TUSHARE_TOKEN` 是否正确
- 确认积分足够（基础数据 120 积分起）

**Q: 如何获取 Moonshot API Key？**
- 访问 https://platform.moonshot.cn
- 注册账号 → 控制台 → API Keys

## 📚 详细文档

- [SKILL.md](../SKILL.md) - 完整功能说明
