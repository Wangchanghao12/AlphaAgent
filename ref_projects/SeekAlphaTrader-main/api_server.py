"""
回测策略API服务器
使用FastAPI和uvicorn提供HTTP接口来调用回测函数
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Optional
import uvicorn
from datetime import datetime
import traceback
import pandas as pd
from expression_manager.expr_parser import parse_expression
from expression_manager.function_lib import *
from jinja2 import Template


# 导入回测函数
from backtest_strategy_api import backtest


def convert_to_dict(df):
    df = df.replace({np.nan: None, pd.NaT: None})
    df['datetime'] = df['datetime'].dt.strftime('%Y-%m-%d')

    # 改为数组返回，column名为key，列值为数组
    data = {}
    if not df.empty:
        for col in df.columns:
            data[col] = df[col].tolist()
    return data


app = FastAPI(
    title="量化回测API",
    description="提供量化交易策略回测的HTTP接口",
    version="1.0.0"
)

# 启动时加载测试数据至内存，供表达式测试接口使用
try:
    DEBUG_DF = pd.read_csv('.debug/debug_df.csv', index_col=[0, 1], parse_dates=True)
    print(DEBUG_DF)
    print(f"成功加载 debug_df.csv, 形状: {DEBUG_DF.shape}")
except FileNotFoundError:
    DEBUG_DF = None
    print("警告: 未找到 debug_df.csv, /test_expr 接口将无法使用")
except Exception as e:
    DEBUG_DF = None
    print(f"警告: 读取 debug_df.csv 失败: {e}")

class DateSplit(BaseModel):
    """时间分割配置"""
    train_start_time: str = Field(..., description="训练开始时间，格式：YYYY-MM-DD")
    train_end_time: str = Field(..., description="训练结束时间，格式：YYYY-MM-DD")
    val_start_time: str = Field(..., description="验证开始时间，格式：YYYY-MM-DD")
    val_end_time: str = Field(..., description="验证结束时间，格式：YYYY-MM-DD")
    test_start_time: str = Field(..., description="测试开始时间，格式：YYYY-MM-DD")
    test_end_time: str = Field(..., description="测试结束时间，格式：YYYY-MM-DD")

class BacktestRequest(BaseModel):
    """回测请求参数"""
    exprs: Dict[str, str] = Field(..., description="因子表达式字典，键为因子名，值为表达式")
    date_split: DateSplit = Field(..., description="时间分割配置")
    start_cash: float = Field(default=1e7, description="初始资金")
    update_freq: int = Field(default=4, description="更新频率（天）")
    label_forward_days: int = Field(default=4, description="标签前瞻天数")
    stock_pool: str = Field(default="中证500", description="股票池")
    stop_loss_rate: Optional[float] = Field(default=0.5, description="止损比例")
    stop_profit_rate: Optional[float] = Field(default=0.4, description="止盈比例")
    position_size: Optional[float] = Field(default=1.0, description="仓位大小")
    max_pos_each_stock: Optional[float] = Field(default=0.2, description="单股最大仓位")
    industry_neutralization: Optional[str] = Field(default="zscore", description="行业中性化方法")
    use_cache: Optional[bool] = Field(default=False, description="是否使用缓存")
    layer_start: Optional[int] = Field(default=0, description="层级开始")
    layer_end: Optional[int] = Field(default=1, description="层级结束")
    pred_score_industry_neutralization: Optional[bool] = Field(default=False, description="预测分数行业中性化")

class BacktestResponse(BaseModel):
    """回测响应结果"""
    success: bool = Field(..., description="请求是否成功")
    message: str = Field(..., description="响应消息")
    data: Optional[Dict] = Field(None, description="回测结果数据")
    error: Optional[str] = Field(None, description="错误信息")

# 新增: 表达式测试请求/响应模型
class ExprTestRequest(BaseModel):
    """表达式合法性测试请求参数"""
    name: str = Field(..., description="因子名称，用于标识该表达式")
    expr: str = Field(..., description="待测试的表达式，形如 'TS_STD($close,5)'")

class ExprTestResponse(BaseModel):
    """表达式合法性测试返回结果"""
    success: bool = Field(..., description="API调用是否成功")
    message: str = Field(..., description="返回信息")
    exe_feedback: Optional[str] = Field(None, description="执行反馈，成功时为None，失败时为traceback")
    code: Optional[str] = Field(None, description="实际执行的代码")
    sample: Optional[Dict] = Field(None, description="样本数据（dict格式）")

@app.get("/")
async def root():
    """根路径，返回API信息"""
    return {
        "message": "量化回测API服务",
        "version": "1.0.0",
        "endpoints": {
            "POST /backtest": "执行回测",
            "GET /health": "健康检查"
        }
    }

@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "量化回测API"
    }

@app.post("/backtest", response_model=BacktestResponse)
async def run_backtest(request: BacktestRequest):
    """
    执行回测
    
    参数:
    - exprs: 因子表达式字典
    - date_split: 时间分割配置
    - start_cash: 初始资金
    - update_freq: 更新频率
    - label_forward_days: 标签前瞻天数
    - stock_pool: 股票池
    - 其他可选参数...
    
    返回:
    - 回测结果数据
    """
    try:
        # 验证日期格式
        try:
            datetime.strptime(request.date_split.train_start_time, '%Y-%m-%d')
            datetime.strptime(request.date_split.train_end_time, '%Y-%m-%d')
            datetime.strptime(request.date_split.val_start_time, '%Y-%m-%d')
            datetime.strptime(request.date_split.val_end_time, '%Y-%m-%d')
            datetime.strptime(request.date_split.test_start_time, '%Y-%m-%d')
            datetime.strptime(request.date_split.test_end_time, '%Y-%m-%d')
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"日期格式错误: {str(e)}")
        
        # 准备回测参数
        backtest_params = {
            'exprs': request.exprs,
            'date_split': request.date_split.dict(),
            'start_cash': request.start_cash,
            'update_freq': request.update_freq,
            'label_forward_days': request.label_forward_days,
            'stock_pool': request.stock_pool,
            'stop_loss_rate': request.stop_loss_rate,
            'stop_profit_rate': request.stop_profit_rate,
            'position_size': request.position_size,
            'max_pos_each_stock': request.max_pos_each_stock,
            'use_cache': request.use_cache,
            'layer_start': request.layer_start,
            'layer_end': request.layer_end,
            'pred_score_industry_neutralization': request.pred_score_industry_neutralization,
        }
        
        # 执行回测
        print(f"开始执行回测，参数: {backtest_params}")
        results = backtest(**backtest_params)
        
        # 处理结果，移除不能序列化的对象
        serializable_results = {}
        for k, v in results.items():
            try:
                # 尝试转换为可序列化格式
                if hasattr(v, 'to_dict'):
                    serializable_results[k] = v.to_dict()
                elif hasattr(v, 'tolist'):
                    serializable_results[k] = v.tolist()
                elif isinstance(v, (int, float, str, bool, list, dict)):
                    serializable_results[k] = v
                else:
                    serializable_results[k] = str(v)
            except:
                serializable_results[k] = str(v)
        
        return BacktestResponse(
            success=True,
            message="回测执行成功",
            data=serializable_results
        )
        
    except Exception as e:
        print(f"错误类型: {type(e)}")
        error_msg = f"回测执行失败: {str(e)}"
        print(f"错误详情: {traceback.format_exc()}")
        
        # 返回500状态码表示服务器内部错误
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "message": "回测执行失败",
                "error": error_msg
            }
        )

@app.get("/example")
async def get_example_request():
    """获取示例请求参数"""
    return {
        "exprs": {
            "Smart_Volume_Cluster_Composite": "(TS_STD($close,5)/(TS_STD($close,20)+1e-8)) * ($volume > TS_QUANTILE($volume,20,0.9))",
            "RangeVolume_SlopeProduct_5D": "COUNT((($high - $low) < TS_MEAN(($high - $low),5)) && ($volume < TS_MEAN($volume,5)),5)",
            "Dynamic_Volatility_Bands_Momentum_Stochastic_Oscillator_Factor": "(($close - TS_MIN($low, 14)) / (TS_MAX($high, 14) - TS_MIN($low, 14) + 1e-8)) * 100"
        },
        "date_split": {
            "train_start_time": "2018-01-01",
            "train_end_time": "2022-12-31",
            "val_start_time": "2023-01-01",
            "val_end_time": "2023-12-31",
            "test_start_time": "2024-01-01",
            "test_end_time": "2024-12-31"
        },
        "start_cash": 10000000.0,
        "update_freq": 4,
        "label_forward_days": 4,
        "stock_pool": "中证金融",
        "stop_loss_rate": 0.5,
        "stop_profit_rate": 0.4,
        "position_size": 1.0,
        "max_pos_each_stock": 0.2,
        "use_cache": False,
        "layer_start": 0,
        "layer_end": 1,
        "pred_score_industry_neutralization": False
    }

@app.post("/test_expr", response_model=ExprTestResponse)
async def test_expression(request: ExprTestRequest):
    """
    测试因子表达式合法性

    流程:
    1. 获取测试数据
    2. 使用 Jinja2 模板渲染表达式，生成可执行的 Python 代码
    3. 使用 `exec` 执行生成的代码
    
    返回说明:
    - success: API调用是否成功
    - exe_feedback: 执行反馈，成功时为None，失败时为完整的traceback
    - code: 实际执行的代码
    """
    try:
        # 1. 获取测试数据
        if DEBUG_DF is None:
            return ExprTestResponse(
                success=True,
                message="服务器未加载 debug_df.csv，无法测试表达式",
                exe_feedback="服务器未加载 debug_df.csv，无法测试表达式",
                code=None,
                sample=None
            )
        
        df = DEBUG_DF.copy()

        # 2. 使用模板渲染表达式
        import os
        os.makedirs('.debug', exist_ok=True)  # 确保目录存在
        
        with open('expression_manager/template.jinjia2', 'r') as f:
            template_content = f.read()
        template = Template(template_content)
        rendered_code = template.render(
            expression=request.expr,
            factor_name=request.name
        )

        print(f"{'='*100}\n {rendered_code}\n {'='*100}")
        # 执行渲染后的代码
        try:
            exec(rendered_code)
            print("执行成功")
        except Exception as e:
            print(traceback.format_exc())
            return ExprTestResponse(
                success=True,
                message="表达式执行失败",
                exe_feedback=traceback.format_exc(),
                code=rendered_code,
                sample=None
            )
        
        # 读取因子表达式计算结果
        result_df = pd.read_pickle('.debug/result_df.pkl').reset_index()
        sample = convert_to_dict(result_df)
        
        # 执行成功
        return ExprTestResponse(
            success=True,
            message="表达式解析与计算成功",
            exe_feedback=None,
            code=rendered_code,
            sample=sample
        )
            

    except Exception as e:
        # API调用本身的异常
        raise HTTPException(
            status_code=500,
            detail=f"API调用异常: {str(e)}"
        )

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
        port=8001,
        reload=True,
        log_level="info"
    ) 
