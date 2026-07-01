"""
实盘交易API服务器
接收账户信息，生成策略信号并发送到中控
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import uvicorn
from datetime import datetime
import traceback

# 导入现有的API和策略模块
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_manager.api_dataloader import SeekAlphaDatabaseAPI
from trade_apis.account_signal_processor import AccountSignalProcessor

app = FastAPI(title="实盘交易API", description="接收账户信息并生成策略信号")

class Position(BaseModel):
    """持仓信息"""
    stock_code: str = Field(..., description="股票代码，如：000001.SZ", max_length=20)
    volume: int = Field(..., description="持仓股票数量，非负整数", ge=0)
    can_use_volume: int = Field(..., description="可用股票数量，非负整数", ge=0)
    frozen_volume: int = Field(..., description="冻结股票数量，非负整数", ge=0)
    open_price: float = Field(..., description="成本价，正数", gt=0)
    avg_price: float = Field(..., description="平均成本价，正数", gt=0)
    market_value: float = Field(..., description="持仓市值，非负数", ge=0)

class AccountPositionsRequest(BaseModel):
    """账户持仓请求数据"""
    account_id: str = Field(..., description="账户ID，最大50个字符", max_length=50)
    total_asset: float = Field(..., description="总资产", ge=0)
    market_value: float = Field(..., description="持仓市值", ge=0) 
    cash: float = Field(..., description="现金余额", ge=0)
    positions: List[Position] = Field(..., description="持仓列表")
    timestamp: str = Field(..., description="数据快照时间，格式：YYYY-MM-DD HH:MM:SS")

class ApiResponse(BaseModel):
    """API响应格式"""
    success: bool
    message: str
    data: Optional[Any] = None

class ControlApiResponse(BaseModel):
    """中控API响应格式"""
    code: int = Field(..., description="响应状态码，200-成功，其他-失败")
    message: str = Field(..., description="响应消息")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")

class PositionsResponseData(BaseModel):
    """持仓接口响应数据"""
    total_provided: int = Field(..., description="提供的持仓记录总数")
    successful_inserts: int = Field(..., description="成功插入的持仓记录数量")

# 初始化组件
trade_api = SeekAlphaDatabaseAPI(base_url="http://localhost:40042")
signal_processor = AccountSignalProcessor()

@app.post("/api/v1/trade/account-positions", response_model=ControlApiResponse)
async def receive_account_positions(request: AccountPositionsRequest):
    """
    批量插入账户持仓接口 - 接收中控传来的账户持仓信息并生成策略信号,
    
    Args:
        request: 账户持仓请求数据
        
    Returns:
        符合中控API规范的响应
    """
    try:
        # print(f"接收到账户 {request.account_id} 的持仓信息，共 {len(request.positions)} 个持仓")
        print(f"接收到账户信息: {request}")
        
        # 1. 根据账户持仓信息生成策略信号
        signals = await signal_processor.generate_signals(request.model_dump())
        print("发送信号：", signals)
        
        # 2. 发送信号到中控
        signal_count = 0
        if signals:
            signals_result = trade_api.insert_trade_signals(signals)
            print("信号发送结果", signals_result)
            signal_count = len(signals)
            print(f"成功生成并发送 {signal_count} 个交易信号到中控")
        else:
            print("未生成交易信号")
        
        # 3. 返回符合中控API规范的响应
        return ControlApiResponse(
            code=200,
            message="Success",
            data={
                "total_provided": len(request.positions),
                "successful_inserts": len(request.positions),
                "generated_signals": signal_count
            }
        )
            
    except Exception as e:
        error_msg = f"处理账户持仓信息时发生错误: {str(e)}"
        print(f"错误详情: {traceback.format_exc()}")
        
        return ControlApiResponse(
            code=500,
            message=f"Data processing failed: {error_msg}",
            data=None
        )

@app.get("/api/health")
async def health_check():
    """健康检查接口"""
    return ApiResponse(
        success=True,
        message="服务运行正常",
        data={"timestamp": datetime.now().isoformat()}
    )

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "实盘交易策略信号API服务",
        "version": "1.0.0",
        "description": "接收中控账户持仓信息，生成策略信号并回传",
        "endpoints": {
            "账户持仓接收": "POST /api/v1/trade/account-positions",
            "健康检查": "GET /api/health",
            "API文档": "GET /docs"
        }
    }

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        reload=True
    )