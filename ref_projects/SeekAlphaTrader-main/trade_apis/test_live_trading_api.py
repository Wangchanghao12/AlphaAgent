"""
实盘交易API测试示例
展示如何调用账户信息处理接口
"""
import requests
import json
from datetime import datetime
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# API服务器地址
API_BASE_URL = "http://localhost:8080"

def test_account_positions_api():
    """测试账户持仓接收接口"""
    
    # 构造测试账户持仓数据
    test_account = {
        "account_id": "account_001", 
        "total_asset": 500000.00,
        "market_value": 500000.00,
        "cash": 500000,
        "positions": [
            # {
            #     "stock_code": "000025.SZ",
            #     "volume": 1000,
            #     "can_use_volume": 800,
            #     "frozen_volume": 200,
            #     "open_price": 12.50,
            #     "avg_price": 12.35,
            #     "market_value": 12350.0
            # },
            # {
            #     "stock_code": "688798.SH",
            #     "volume": 500,
            #     "can_use_volume": 500,
            #     "frozen_volume": 0,
            #     "open_price": 8.20,
            #     "avg_price": 8.15,
            #     "market_value": 4075.0
            # },
            # {
            #     "stock_code": "600519.SH",
            #     "volume": 100,
            #     "can_use_volume": 100,
            #     "frozen_volume": 0,
            #     "open_price": 1800.0,
            #     "avg_price": 1850.0,
            #     "market_value": 185000.0
            # }
        ],
        "timestamp": "2025-09-24 15:20:00"
    }
    
    try:
        # 发送POST请求到新的接口
        print("正在发送账户持仓信息到API...")
        response = requests.post(
            f"{API_BASE_URL}/api/v1/trade/account-positions",
            json=test_account,
            headers={"Content-Type": "application/json"}
        )
        
        # 检查响应
        if response.status_code == 200:
            result = response.json()
            print("✅ API调用成功!")
            print(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
            
            if result.get("code") == 200:
                data = result.get("data", {})
                total_provided = data.get("total_provided", 0)
                successful_inserts = data.get("successful_inserts", 0)
                generated_signals = data.get("generated_signals", 0)
                print(f"\n📊 处理结果:")
                print(f"   - 提供的持仓记录总数: {total_provided}")
                print(f"   - 成功处理的持仓记录数量: {successful_inserts}")
                print(f"   - 生成的交易信号数量: {generated_signals}")
            else:
                print(f"\n❌ 接口返回错误: {result.get('message', '未知错误')}")
                    
        else:
            print(f"❌ API调用失败: {response.status_code}")
            print(f"错误信息: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到API服务器，请确保服务器已启动")
        print("启动命令: python start_live_trading_server.py")
    except Exception as e:
        print(f"❌ 请求发生错误: {e}")

def test_health_check():
    """测试健康检查接口"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/health")
        if response.status_code == 200:
            result = response.json()
            print("✅ 健康检查通过")
            print(f"服务状态: {result}")
        else:
            print(f"❌ 健康检查失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 健康检查错误: {e}")

if __name__ == "__main__":
    print("=== 实盘交易策略信号API测试 ===\n")
    
    # 1. 健康检查
    print("1. 健康检查...")
    test_health_check()
    
    # 2. 账户持仓接收测试
    print("2. 账户持仓接收测试...")
    test_account_positions_api()
    
    print("\n=== 测试完成 ===")
    
    print(f"\n📖 API文档地址: {API_BASE_URL}/docs")
    print("💡 可以在浏览器中打开API文档查看详细接口说明")
    print("🎯 中控可以通过 POST /api/v1/trade/account-positions 发送账户持仓信息")