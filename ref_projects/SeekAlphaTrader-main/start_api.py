#!/usr/bin/env python3
"""
API服务器启动脚本
"""
import os
import sys
import uvicorn

if __name__ == "__main__":
    print("="*60)
    print("启动量化回测API服务器")
    print("="*60)
    print("服务地址: http://localhost:8001")
    print("API文档: http://localhost:8001/docs")
    print("健康检查: http://localhost:8001/health")
    print("示例参数: http://localhost:8001/example")
    print("表达式测试(POST): http://localhost:8001/test_expr")
    print("="*60)
    
    # 启动服务器
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8003,
        reload=True,
        log_level="info"
    ) 