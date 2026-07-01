"""
启动实盘交易API服务器
"""
import uvicorn
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ == "__main__":
    print("正在启动实盘交易API服务器...")
    print("API文档地址: http://localhost:8080/docs")
    print("健康检查: http://localhost:8080/api/health")
    print("账户信息处理接口: POST http://localhost:8080/api/account/process")
    
    uvicorn.run(
        "trade_apis.live_trading_server:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info"
    )