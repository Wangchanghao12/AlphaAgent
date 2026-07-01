# Backtest API 文档

## 函数概述

`backtest` 函数是一个量化交易策略回测的主要接口函数，支持基于机器学习的多因子策略回测。

## 函数签名

```python
def backtest(
    exprs: Dict[str, str] = None, 
    date_split: Dict[str, str] = None, 
    use_cache: bool = False, 
    **kwargs
) -> dict:
```

## 参数说明

### 必需参数

#### `exprs` (Dict[str, str], 可选)
- **描述**: 因子表达式字典，键为因子名称，值为因子计算表达式
- **默认值**: `None`
- **示例**:
```python
exprs = {
    "Smart_Volume_Cluster_Composite": "(TS_STD($close,5)/(TS_STD($close,20)+1e-8)) * ($volume > TS_QUANTILE($volume,20,0.9))",
    "Dynamic_Volatility_Bands": "(($close - TS_MIN($low, 14)) / (TS_MAX($high, 14) - TS_MIN($low, 14) + 1e-8)) * 100"
}
```

#### `date_split` (Dict[str, str], 可选)
- **描述**: 时间段分割配置，定义训练、验证和测试时间段
- **默认值**: `None`
- **必需字段**:
  - `train_start_time`: 训练开始时间 (格式: 'YYYY-MM-DD')
  - `train_end_time`: 训练结束时间 (格式: 'YYYY-MM-DD')
  - `val_start_time`: 验证开始时间 (格式: 'YYYY-MM-DD')
  - `val_end_time`: 验证结束时间 (格式: 'YYYY-MM-DD')
  - `test_start_time`: 测试开始时间 (格式: 'YYYY-MM-DD')
  - `test_end_time`: 测试结束时间 (格式: 'YYYY-MM-DD')
- **示例**:
```python
date_split = {
    'train_start_time': '2018-01-01',
    'train_end_time': '2023-12-31', 
    'val_start_time': '2024-01-01',
    'val_end_time': '2024-05-31',
    'test_start_time': '2024-06-01',
    'test_end_time': '2025-06-06'
}
```

#### `use_cache` (bool, 可选)
- **描述**: 是否使用数据缓存来加速数据加载
- **默认值**: `False`

### 可选参数 (**kwargs)

#### 交易设置参数

- **`stop_loss_rate`** (float): 止损率，范围 [0, 1]，默认值参考代码示例中的 0.5
- **`stop_profit_rate`** (float): 止盈率，范围 [0, 1]，默认值参考代码示例中的 0.4
- **`start_cash`** (float): 初始资金，默认值参考代码示例中的 1e7 (一千万)
- **`position_size`** (float): 整体仓位大小，范围 [0, 1]，默认值参考代码示例中的 1.0
- **`max_pos_each_stock`** (float): 每只股票最大仓位比例，范围 [0, 1]，默认值参考代码示例中的 0.2

#### 模型训练参数

- **`label_forward_days`** (int): 标签前向天数，即预测多少天后的收益，默认值参考代码示例中的 4
- **`pred_score_industry_neutralization`** (bool): 是否对预测分数进行行业中性化处理，默认值参考代码示例中的 True

#### 组合管理参数

- **`update_freq`** (int): 组合更新频率（天数），默认值参考代码示例中的 4
- **`stock_pool`** (str): 股票池选择，支持的选项包括:
  - '上证50'
  - '中证500' 
  - '沪深300'
  - '中证1000'
  - '上证信息'
  - '上证电信'
  - '全指成长'
  - '全指价值'
  - '中证能源'
  - '中证可选'
  - '中证消费'
  - '中证医药'
  - '中证金融'

#### 回测分析参数

- **`layer_start`** (float): 分层回测起始分位数，范围 [0, 9]，默认值参考代码示例中的 0
- **`layer_end`** (float): 分层回测结束分位数，范围 [1, 10]，默认值参考代码示例中的 1

## 返回值

函数返回一个包含完整回测结果的字典 (`dict`)，主要包含以下字段：

### 顶层字段
- **`code`** (int): 状态码，0表示成功
- **`message`** (str): 执行消息，如 'success'
- **`data`** (dict): 主要数据内容

### data 字段详细结构

#### metrics (性能指标)
包含详细的回测性能指标：

**考虑交易成本的指标** (前缀: `1day.excess_return_with_cost.`):
- `max_drawdown`: 最大回撤
  - **示例**: `0.1344` (表示最大回撤为13.44%)
  - **含义**: 策略在回测期间的最大资产净值回撤幅度
- `information_ratio`: 信息比率  
  - **示例**: `2.456` 
  - **含义**: 超额收益与跟踪误差的比值，衡量单位风险的超额收益
- `std`: 收益率标准差
  - **示例**: `0.0045` (表示日收益率标准差为0.45%)
  - **含义**: 策略日收益率的波动程度
- `mean`: 平均日收益率
  - **示例**: `0.0004` (表示平均日收益率为0.04%)
  - **含义**: 策略在回测期间的平均每日收益率
- `annualized_return`: 年化收益率
  - **示例**: `0.1702` (表示年化收益率为17.02%)
  - **含义**: 策略年化后的收益率

**不考虑交易成本的指标** (前缀: `1day.excess_return_without_cost.`):
- `max_drawdown`: 最大回撤
  - **示例**: `0.1181` (表示最大回撤为11.81%)
  - **含义**: 不考虑交易成本时的最大资产净值回撤幅度
- `information_ratio`: 信息比率
  - **示例**: `3.621`
  - **含义**: 不考虑交易成本时的信息比率
- `std`: 收益率标准差  
  - **示例**: `0.0045` (表示日收益率标准差为0.45%)
  - **含义**: 不考虑交易成本时策略日收益率的波动程度
- `mean`: 平均日收益率
  - **示例**: `0.0007` (表示平均日收益率为0.07%)
  - **含义**: 不考虑交易成本时策略的平均每日收益率
- `annualized_return`: 年化收益率
  - **示例**: `0.2508` (表示年化收益率为25.08%)
  - **含义**: 不考虑交易成本时策略年化后的收益率

**因子有效性指标**:
- `IC`: 信息系数 (Information Coefficient)
  - **示例**: `0.0233` 
  - **含义**: 因子预测值与真实收益的相关性，范围[-1,1]，越接近±1越好
- `ICIR`: 信息系数比率 (IC Information Ratio)
  - **示例**: `0.2113`
  - **含义**: IC的均值除以IC的标准差，衡量IC的稳定性
- `RankIC`: 排序信息系数 (Rank Information Coefficient)
  - **示例**: `0.0005`
  - **含义**: 因子排序值与收益排序值的相关性
- `RankICIR`: 排序信息系数比率 (Rank IC Information Ratio)
  - **示例**: `0.0054`
  - **含义**: RankIC的均值除以RankIC的标准差

#### chart (图表数据)
包含绘制回测图表所需的时间序列数据：
- **`dates`** (List[str]): 交易日期列表，格式为 'YYYY-MM-DD'
  - **示例**: `['2024-06-03', '2024-06-04', '2024-06-05', '2024-06-06', ...]`
  - **含义**: 回测期间所有的交易日期，按时间顺序排列
- **`bench`** (List[float]): 基准指数的累计收益率序列
  - **示例**: `[0.0, 0.0094, 0.0010, -0.0030, ...]`
  - **含义**: 基准指数从开始日期到当前日期的累计收益率，第一个值为0.0
- **`return`** (List[float]): 策略的累计收益率序列
  - **示例**: `[0.0, -0.0002, -0.0056, -0.0127, ...]`
  - **含义**: 策略从开始日期到当前日期的累计收益率，第一个值为0.0
- **`cost`** (List[float]): 每日交易成本序列
  - **示例**: `[0.0, 0.0002, 0.0, 0.0, 0.0, 0.0012, ...]`
  - **含义**: 每个交易日产生的交易成本，0.0表示该日无交易
- **`turnover`** (List[float]): 每日换手率序列
  - **示例**: `[0.0, 1.0, 0.0, 0.0, 0.0, 1.635, ...]`
  - **含义**: 每个交易日的投资组合换手率，1.0表示100%换手

### 配置参数字段
回测中使用的配置参数会被保存在返回结果中：
- **`stop_loss_rate`** (float): 止损率
  - **示例**: `0.5`
  - **含义**: 当单只股票亏损达到50%时触发止损
- **`stop_profit_rate`** (float): 止盈率
  - **示例**: `0.4`
  - **含义**: 当单只股票盈利达到40%时触发止盈
- **`start_cash`** (float): 初始资金
  - **示例**: `10000000`
  - **含义**: 回测开始时的初始资金为1000万元
- **`position_size`** (float): 整体仓位大小
  - **示例**: `1.0`
  - **含义**: 使用100%的资金进行投资，不留现金
- **`update_freq`** (int): 组合更新频率
  - **示例**: `4`
  - **含义**: 每4个交易日重新调整一次投资组合
- **`max_pos_each_stock`** (float): 每只股票最大仓位比例
  - **示例**: `0.2`
  - **含义**: 单只股票最大占投资组合的20%
- **`stock_pool`** (str): 使用的股票池
  - **示例**: `'上证中小'`
  - **含义**: 从上证中小盘股票池中选择投资标的

### 返回值示例

```python
{
    'code': 0,
    'message': 'success',
    'data': {
        'metrics': {
            # 考虑交易成本的指标
            '1day.excess_return_with_cost.max_drawdown': 0.1344,
            '1day.excess_return_with_cost.information_ratio': 2.456,
            '1day.excess_return_with_cost.std': 0.0045,
            '1day.excess_return_with_cost.mean': 0.0004,
            '1day.excess_return_with_cost.annualized_return': 0.1702,
            
            # 不考虑交易成本的指标
            '1day.excess_return_without_cost.annualized_return': 0.2508,
            '1day.excess_return_without_cost.mean': 0.0007,
            '1day.excess_return_without_cost.std': 0.0045,
            '1day.excess_return_without_cost.information_ratio': 3.621,
            '1day.excess_return_without_cost.max_drawdown': 0.1181,
            
            # 因子有效性指标
            'IC': 0.0233,
            'ICIR': 0.2113,
            'RankIC': 0.0005,
            'RankICIR': 0.0054
        },
        'chart': {
            'dates': ['2024-06-03', '2024-06-04', '2024-06-05', ...],
            'bench': [0.0, 0.0094, 0.0010, -0.0030, ...],
            'return': [0.0, -0.0002, -0.0056, -0.0127, ...],
            'cost': [0.0, 0.0002, 0.0, ...],
            'turnover': [0.0, 1.0, 0.0, ...]
        }
    },
    # 配置参数
    'stop_loss_rate': 0.5,
    'stop_profit_rate': 0.4,
    'start_cash': 10000000,
    'position_size': 1.0,
    'update_freq': 4,
    'max_pos_each_stock': 0.2,
    'stock_pool': '上证中小'
}
```

## 使用示例

```python
# 完整的回测示例
results = backtest(
    exprs={
        "momentum_factor": "RANK(DELTA($close, 20))",
        "volume_factor": "RANK($volume / TS_MEAN($volume, 20))"
    },
    date_split={
        'train_start_time': '2018-01-01',
        'train_end_time': '2023-12-31',
        'val_start_time': '2024-01-01', 
        'val_end_time': '2024-05-31',
        'test_start_time': '2024-06-01',
        'test_end_time': '2024-12-31'
    },
    use_cache=True,
    stop_loss_rate=0.05,
    stop_profit_rate=0.10,
    start_cash=10000000,
    position_size=0.95,
    update_freq=5,
    label_forward_days=3,
    max_pos_each_stock=0.15,
    stock_pool='中证500',
    layer_start=0,
    layer_end=1,
    pred_score_industry_neutralization=True
)

# 获取关键指标
if results['code'] == 0:
    metrics = results['data']['metrics']
    
    # 考虑交易成本的指标
    annual_return_with_cost = metrics['1day.excess_return_with_cost.annualized_return']
    max_drawdown_with_cost = metrics['1day.excess_return_with_cost.max_drawdown']
    information_ratio_with_cost = metrics['1day.excess_return_with_cost.information_ratio']
    
    # 不考虑交易成本的指标
    annual_return_without_cost = metrics['1day.excess_return_without_cost.annualized_return']
    max_drawdown_without_cost = metrics['1day.excess_return_without_cost.max_drawdown']
    information_ratio_without_cost = metrics['1day.excess_return_without_cost.information_ratio']
    
    # 因子有效性指标
    ic = metrics['IC']
    icir = metrics['ICIR']
    rank_ic = metrics['RankIC']
    rank_icir = metrics['RankICIR']
    
    # 图表数据
    chart_data = results['data']['chart']
    dates = chart_data['dates']
    strategy_returns = chart_data['return']
    benchmark_returns = chart_data['bench']
    trading_costs = chart_data['cost']
    turnover_rates = chart_data['turnover']
```

## 注意事项

1. **时间限制**: 测试结束时间不能大于当前时间
2. **数据依赖**: 需要确保相应的股票池数据和指数数据可用
3. **内存要求**: 大规模回测可能需要较多内存，建议适当设置缓存
4. **因子表达式**: 需要使用系统支持的因子计算语法
5. **股票池**: 不同股票池的历史数据可用性可能不同

## 异常处理

函数内部包含错误处理机制，主要的异常情况包括：
- 日期格式错误或时间范围不合理
- 股票池代码不支持
- 数据加载失败
- 模型训练失败

建议在调用时使用 try-except 块来处理可能的异常。 