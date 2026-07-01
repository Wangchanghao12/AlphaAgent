# 实盘交易API模块

## 📁 目录结构

```
trade_apis/
├── __init__.py                      # 包初始化
├── generate_today_signal.py        # 现有策略信号生成
├── account_signal_processor.py     # 账户信号处理模块  
├── live_trading_server.py          # FastAPI服务器主程序
├── start_server.py                 # 服务器启动脚本
├── test_live_trading_api.py        # API测试示例
└── README.md                       # 说明文档
```

## 🚀 快速开始

### 1. 启动服务器

**方法一（推荐）：** 在项目根目录运行
```bash
python start_live_trading.py
```

**方法二：** 直接启动
```bash
python trade_apis/start_server.py
```

### 2. 测试API

```bash
python trade_apis/test_live_trading_api.py
```

### 3. 访问API文档

浏览器打开：`http://localhost:8080/docs`

## 📊 API接口

### POST /api/v1/trade/account-positions

批量插入账户持仓接口 - 接收中控传来的账户持仓信息并生成策略信号

**请求示例：**
```json
{
  "account_id": "test_account",
  "total_asset": 1000000.0,
  "market_value": 800000.0,
  "cash": 200000.0,
  "positions": [
    {
      "stock_code": "000001.SZ",
      "volume": 1000,
      "can_use_volume": 800,
      "frozen_volume": 200,
      "open_price": 12.50,
      "avg_price": 12.35,
      "market_value": 12350.0
    }
  ],
  "timestamp": "2025-01-20 15:30:00"
}
```

**响应示例：**
```json
{
  "code": 200,
  "message": "Success",
  "data": {
    "total_provided": 2,
    "successful_inserts": 2,
    "generated_signals": 3
  }
}
```

## 🔧 工作流程

1. **接收账户持仓数据** → 中控通过 `POST /api/v1/trade/account-positions` 发送
2. **数据验证** → Pydantic自动验证字段格式和范围  
3. **策略计算** → 基于持仓信息和现有策略表达式分析
4. **生成交易信号** → 考虑冻结股票，卖出使用可用数量
5. **自动回传** → 通过 `insert_trade_signals()` 发送信号到中控

## 🛠️ 技术栈

- **FastAPI** - Web框架
- **Pydantic** - 数据验证
- **Pandas/Numpy** - 数据处理
- **现有策略模块** - 信号计算

## 📝 注意事项

- 确保中控数据库API (`http://localhost:40024`) 正常运行
- 本服务仅接收账户持仓信息，不存储到本地数据库
- 生成的交易信号会自动发送回中控系统
- 符合中控API规范的响应格式 (`code`, `message`, `data`)