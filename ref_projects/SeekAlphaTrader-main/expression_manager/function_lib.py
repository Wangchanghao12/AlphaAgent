import numpy as np
import pandas as pd
from joblib import Parallel, delayed


def datatype_adapter(func):
    def wrapper(*args, **kwargs):
        # 对于单个输入，若是np array，则转成df
        if len(args) == 1 and isinstance(args[0], np.ndarray):
            # 转换NumPy数组到DataFrame
            new_args = (pd.DataFrame(args[0]),)
            # 执行函数并转回NumPy数组
            result = func(*new_args, **kwargs)
            return result
        # 对于单个输入，若是float，则转成df再转回float
        if len(args) == 1 and isinstance(args[0], (float, int)):
            new_args = (pd.DataFrame([args[0]]),)
            result = func(*new_args, **kwargs)
            return float(result.iloc[0])
        # 对于典型输入，func(df, p) or func(df)
        if (len(args) == 2 and isinstance(args[0], np.ndarray) and not isinstance(args[1], np.ndarray)):
            # 转换NumPy数组到DataFrame
            new_args = (pd.DataFrame(args[0]), args[1])
            # 执行函数并转回NumPy数组
            result = func(*new_args, **kwargs)
        elif (len(args) == 2 and isinstance(args[1], np.ndarray) and not isinstance(args[0], np.ndarray)):
            # 转换NumPy数组到DataFrame
            new_args = (args[0], pd.DataFrame(args[1]))
            # 执行函数并转回NumPy数组
            result = func(*new_args, **kwargs)
        else:
            result = func(*args, **kwargs)
        return result

    return wrapper


def support_dynamic_window(func):
    def wrapper(*args, **kwargs):
        if len(args) >= 2 and isinstance(args[0], pd.Series) and isinstance(args[1], pd.Series):
                assert len(args[1]) == len(args[0]), "动态窗口的参数长度必须与主DataFrame长度相同"
                # 分组并行按时间顺序计算
                def calculate_one_stock(stock):
                    # 取某只股票，但保留Multiindex
                    df_a = args[0][args[0].index.get_level_values('instrument') == stock]
                    df_b = args[1][args[1].index.get_level_values('instrument') == stock]
                    result = pd.Series(index=df_a.index, dtype=float)
                    for date in args[0].index.get_level_values(0).unique().sort_values():
                        # 只取240天内的数据
                        if not df_b.loc[date].isna().any() and int(df_b.loc[date].iloc[0]) > 0:
                            result.loc[date] = func(df_a.loc[date-pd.Timedelta(days=500):date], int(df_b.loc[date].iloc[0]), n_jobs=-1).iloc[-1]
                        
                    return result
                
                all_stock_result = Parallel(n_jobs=-1)(
                    delayed(calculate_one_stock)(stock)
                    for stock in args[0].index.get_level_values(1).unique().tolist()
                )

                # 将多个股票的结果合并成一个DataFrame
                result = pd.concat(all_stock_result).sort_index()
                return result
        return func(*args, **kwargs)
    return wrapper


@datatype_adapter
def INDUSTRY_NEUTRALIZE(df:pd.DataFrame, df_industry:pd.DataFrame):
    """
    行业中性化
    """
    assert df_industry.dtypes == object, "INDUSTRY_NEUTRALIZE的第二个参数必须为$industry, 例如`INDUSTRY_NEUTRALIZE(TS_STD($close,5), $industry)`。请检查表达式是否正确。"
    def industry_zscore(group):
        return (group - group.mean()) / (group.std() + 1e-8)
    return df.groupby([df.index.get_level_values(0), df_industry]).transform(industry_zscore)

@datatype_adapter
@support_dynamic_window
def DELTA(df:pd.DataFrame, p:int=1, **kwargs):
    return df.groupby('instrument').transform(lambda x: x.diff(periods=p))

@datatype_adapter
def RANK(df:pd.DataFrame):
    """计算横截面排序"""
    return df.groupby('datetime').rank(pct=True)

@datatype_adapter
def MEAN(df:pd.DataFrame):
    """计算横截面平均值"""
    return df.groupby('datetime').mean()

@datatype_adapter
def STD(df:pd.DataFrame):
    """计算横截面标准差"""
    return df.groupby('datetime').std()

@datatype_adapter
def SKEW(df:pd.DataFrame):
    """计算横截面偏度"""
    return df.groupby('datetime').skew()

@datatype_adapter
def KURT(df:pd.DataFrame):
    """计算横截面峰度"""
    return df.groupby('datetime').apply(lambda x: x.kurtosis())

@datatype_adapter
def MAX(df:pd.DataFrame):
    """计算横截面最大值"""
    return df.groupby('datetime').max()

@datatype_adapter
def MIN(df:pd.DataFrame):
    """计算横截面最小值"""
    return df.groupby('datetime').min()

@datatype_adapter
def MEDIAN(df:pd.DataFrame):
    """计算横截面中位数"""
    return df.groupby('datetime').median()



@datatype_adapter
@support_dynamic_window
def TS_RANK(df:pd.DataFrame, p:int=5, **kwargs):
    """计算时间序列的百分比排名"""
    return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).rank(pct=True))

@datatype_adapter
@support_dynamic_window
def TS_MAX(df:pd.DataFrame, p:int=5, **kwargs):
    """计算时间序列的最大值"""
    return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).max())

@datatype_adapter
@support_dynamic_window
def TS_MIN(df:pd.DataFrame, p:int=5, **kwargs):
    """计算时间序列的最小值"""
    return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).min())

@datatype_adapter
@support_dynamic_window
def TS_MEAN(df:pd.DataFrame, p:int=5, **kwargs):
    """计算时间序列的平均值"""
    return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).mean())

@datatype_adapter
@support_dynamic_window
def TS_MEDIAN(df:pd.DataFrame, p:int=5, **kwargs):
    """计算时间序列的中位数"""
    return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).median())

@datatype_adapter
def PERCENTILE(df: pd.DataFrame, q: float, p: int = None):
    """
    计算给定数据的分位数。

    参数:
        df (pd.DataFrame): 输入数据，可以是 DataFrame 或 NumPy 数组。
        q (float): 分位数，范围在 [0, 1] 之间。
        p (int): 滚动窗口大小，如果提供，则计算滚动分位数。

    返回:
        pd.DataFrame: 包含分位数的 DataFrame。
    """
    assert 0 <= q <= 1, "分位数 q 必须在 [0, 1] 之间"
    
    if p is not None:
        # 如果有滚动窗口大小，计算滚动分位数
        return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).quantile(q))
    else:
        # 如果没有滚动窗口大小，直接计算分位数
        return df.groupby('instrument').transform(lambda x: x.quantile(q))



@datatype_adapter
@support_dynamic_window
def TS_SUM(df:pd.DataFrame, p:int=5):
    """计算时间序列的累加和"""
    return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).sum())


@datatype_adapter
@support_dynamic_window
def TS_ARGMAX(df: pd.DataFrame, p: int = 5, **kwargs):
    """计算过去p天内最大值出现的位置距今天数"""
    def rolling_argmax(window):
        return len(window) - window.argmax() - 1
    return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).apply(rolling_argmax, raw=True))

@datatype_adapter
@support_dynamic_window
def TS_ARGMIN(df: pd.DataFrame, p: int = 5, **kwargs):
    """计算过去p天内最小值出现的位置距今天数"""
    def rolling_argmin(window):
        return len(window) - window.argmin() - 1
    return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).apply(rolling_argmin, raw=True))



def MAX(x:pd.DataFrame, y:pd.DataFrame, z:pd.DataFrame=None):
    """计算多个DataFrame之间的最大值"""
    if z is None:
        return np.maximum(x, y)
    else:
        return np.maximum(np.maximum(x, y), z)




def MIN(x:pd.DataFrame, y:pd.DataFrame, z:pd.DataFrame=None):
    """计算多个DataFrame之间的最小值""" 
    if z is None:
        return np.minimum(x, y)
    else:
        return np.minimum(np.minimum(x, y), z)
    


@datatype_adapter
def ABS(df:pd.DataFrame):
    """计算DataFrame中每个元素的绝对值"""   
    return df.groupby('instrument').transform(lambda x: x.abs())    

@datatype_adapter
@support_dynamic_window
def DELAY(df:pd.DataFrame, p:int=1, **kwargs):
    """将数据延迟p个周期"""
    assert p >= 0, ValueError("DELAY的时长不能小于0，否则将会造成数据窥测")
    return df.groupby('instrument').transform(lambda x: x.shift(p))

@datatype_adapter
def TS_CORR(df1:pd.Series, df2: pd.Series, p:int=5, **kwargs):
    """计算两个序列的滚动相关性"""
    if isinstance(df2, np.ndarray) and p != len(df2):
        p = len(df2)
        def corr(window):
            x = window
            y = df2[:len(window)]
            # 计算均值
            mean_x = np.mean(x)
            mean_y = np.mean(y)
            
            # 计算协方差和标准差
            cov = np.sum((x - mean_x) * (y - mean_y))
            std_x = np.sqrt(np.sum((x - mean_x) ** 2))
            std_y = np.sqrt(np.sum((y - mean_y) ** 2))
            
            # 计算相关系数
            return cov / (std_x * std_y)
        
        return df1.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=2).apply(corr, raw=True))
    else:
        def rolling_corr(group, df2, p):
            # 获取当前分组的 instrument
            instrument = group.name
            # 从 df2 中提取对应的 instrument 数据
            df2_group = df2.xs(instrument, level='instrument')
            # 计算滚动相关性
            return group.rolling(p, min_periods=2).corr(df2_group)

        # 使用 groupby 和 apply 来计算每个 instrument 的滚动相关性
        result = df1.groupby('instrument', group_keys=False).apply(lambda x: rolling_corr(x, df2, p))
        return result

@datatype_adapter
def TS_COVARIANCE(df1:pd.DataFrame, df2:pd.DataFrame, p:int=5):  
    """计算两个序列的滚动协方差"""
    if isinstance(df2, np.ndarray) and p != len(df2):
        p = len(df2)
        def cov(window):
            return np.cov(window, df2[:len(window)])
        return df1.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=2).apply(cov, raw=True))
    else:
        def rolling_cov(group, df2, p):
            # 获取当前分组的 instrument
            instrument = group.name
            # 从 df2 中提取对应的 instrument 数据
            df2_group = df2.xs(instrument, level='instrument')
            # 计算滚动相关性
            return group.rolling(p, min_periods=2).cov(df2_group)

        # 使用 groupby 和 apply 来计算每个 instrument 的滚动相关性
        result = df1.groupby('instrument').apply(lambda x: rolling_cov(x, df2, p))
        return result

@datatype_adapter
@support_dynamic_window
def TS_STD(df:pd.DataFrame, p:int=20):
    """计算时间序列的滚动标准差(Standard Deviation)"""
    return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).std())



@datatype_adapter
@support_dynamic_window
def TS_VAR(df: pd.DataFrame, p: int = 5, ddof: int = 1):
    """计算时间序列的滚动方差(Variance)"""
    return df.groupby('instrument').transform(
        lambda x: x.rolling(p, min_periods=1).var(ddof=ddof)
    )

@datatype_adapter
def SIGN(df: pd.DataFrame):
    """计算DataFrame中每个元素的符号"""
    return np.sign(df)

@datatype_adapter
@support_dynamic_window
def SMA(df:pd.DataFrame, m:float=None, n:float=None, **kwargs):
    """
    计算简单移动平均线(Simple Moving Average)
    
    参数:
        df (pd.DataFrame): 输入数据
        m (float, optional): 移动平均的周期数
        n (float, optional): 移动平均的权重
    Y_{i+1} = m/n*X_i + (1 - m/n)*Y_i
    """
        
    if isinstance(m, int) and m >= 1 and n is None:
        return df.groupby('instrument').transform(lambda x: x.rolling(m, min_periods=1).mean())
    else:
        return df.groupby('instrument').transform(lambda x: x.ewm(alpha=n/m).mean())

@datatype_adapter
@support_dynamic_window
def EMA(df:pd.DataFrame, p):
    """
    计算指数移动平均线(Exponential Moving Average)
    
    参数:
        df (pd.DataFrame): 输入数据
        p (int): 移动平均的周期数

    返回:
        pd.DataFrame: 指数移动平均线结果
    """
    return df.groupby('instrument').transform(lambda x: x.ewm(span=int(p), min_periods=1).mean())
    
@datatype_adapter
@support_dynamic_window
def WMA(df:pd.DataFrame, p:int=20):
    """
    计算加权移动平均线(Weighted Moving Average)
    
    参数:
        df (pd.DataFrame): 输入数据
        p (int): 移动平均的周期数
        
    返回:
        pd.DataFrame: 加权移动平均线结果
    """
    # 计算权重，最近的数据（i=0）有最大的权重
    weights = [0.9**i for i in range(p)][::-1]
    def calculate_wma(window):
        return (window * weights[:len(window)]).sum() / sum(weights[:len(window)])

    # 应用权重计算滑动WMA
    return df.groupby('instrument').transform(lambda x: x.rolling(window=p, min_periods=1).apply(calculate_wma, raw=True))

@datatype_adapter
@support_dynamic_window
def COUNT(cond:pd.DataFrame, p:int=20, **kwargs):
    """
    计算条件计数
    
    参数:
        cond (pd.DataFrame): 条件数据
        p (int): 滚动窗口大小
    
    返回:
        pd.DataFrame: 条件计数结果
    """
    return cond.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).sum())

@datatype_adapter
def SUMIF(df:pd.DataFrame, p:int, cond:pd.DataFrame):
    """
    计算满足条件的序列的滚动和
    
    参数:
        df (pd.DataFrame): 输入数据
        p (int): 滚动窗口大小
        cond (pd.DataFrame): 条件数据
    
    返回:
        pd.DataFrame: 满足条件的序列的滚动和
    """
    return (df * cond).groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).sum())

@datatype_adapter
def FILTER(df:pd.DataFrame, cond:pd.DataFrame):
    """
    根据条件过滤序列，保留满足条件的元素，不满足条件的元素置为0
    
    参数:
        df (pd.DataFrame): 输入数据
        cond (pd.DataFrame): 条件数据
    
    返回:
        pd.DataFrame: 根据条件过滤后的序列
    """
    return df.mul(cond)
    

@datatype_adapter
@support_dynamic_window
def PROD(df:pd.DataFrame, p:int=5):
    """
    计算序列的滚动乘积
    
    参数:
        df (pd.DataFrame): 输入数据
        p (int): 滚动窗口大小
    
    返回:
        pd.DataFrame: 滚动乘积结果
    """

    # 使用rolling方法创建一个滑动窗口，然后应用累乘
    if isinstance(p, int):
        return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).apply(lambda x: x.prod(), raw=True))
    else:
        return df.mul(p)    

@datatype_adapter
def DECAYLINEAR(df:pd.DataFrame, p:int=5):
    """
    计算序列的线性衰减加权平均
    
    参数:
        df (pd.DataFrame): 输入数据
        p (int): 滚动窗口大小
    
    返回:
        pd.DataFrame: 线性衰减加权平均结果
    """
    assert isinstance(p, int), ValueError(f"DECAYLINEAR仅接收正整数参数n，接收到{type(p).__name__}")
    decay_weights = np.arange(1, p+1, 1)
    decay_weights = decay_weights / decay_weights.sum()
    
    def calculate_deycaylinear(window):
        return (window * decay_weights[:len(window)]).sum()
    
    return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).apply(calculate_deycaylinear, raw=True))

@datatype_adapter
@support_dynamic_window
def HIGHDAY(df:pd.DataFrame, p:int=5):
    """
    计算序列中最大值出现的位置距今天数
    
    参数:
        df (pd.DataFrame): 输入数据
        p (int): 滚动窗口大小
    
    返回:
        pd.DataFrame: 最大值出现的位置距今天数
    """
    assert isinstance(p, int), ValueError(f"HIGHDAY仅接收正整数参数n，接收到{type(p).__name__}")
    def highday(window):
        return len(window) - window.argmax(axis=0)
    return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).apply(highday, raw=True))


@datatype_adapter
@support_dynamic_window
def LOWDAY(df:pd.DataFrame, p:int=5):
    """
    计算序列中最小值出现的位置距今天数
    
    参数:
        df (pd.DataFrame): 输入数据
        p (int): 滚动窗口大小
    
    返回:
        pd.DataFrame: 最小值出现的位置距今天数
    """
    assert isinstance(p, int), ValueError(f"LOWDAY仅接收正整数参数n，接收到{type(p).__name__}")
    def lowday(window):
        return len(window) - window.argmin(axis=0)
    return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).apply(lowday, raw=True))
    

def SEQUENCE(n):
    """
    生成一个从1到n的等差数列
    
    参数:
        n (int): 数列的长度
    """
    assert isinstance(n, int), ValueError(f"SEQUENCE(n)仅接收正整数参数n，接收到{type(n).__name__}")
    return np.linspace(1, n, n, dtype=np.float32)

@datatype_adapter
@support_dynamic_window
def SUMAC(df:pd.DataFrame, p:int=10):
    """
    计算序列的滚动累加和
    
    参数:
        df (pd.DataFrame): 输入数据
        p (int): 滚动窗口大小
    
    返回:
        pd.DataFrame: 滚动累加和结果
    """
    assert isinstance(p, int), ValueError(f"SUMAC仅接收正整数参数n，接收到{type(p).__name__}")
    return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).sum())



def calculate_beta(y, x):
    """计算回归系数（beta）"""
    X = np.vstack([x, np.ones(len(x))]).T
    beta, _ = np.linalg.lstsq(X, y, rcond=None)[0]
    return beta

def rolling_beta(df1_group, df2_group, p):
    """对 df1 和 df2 的滚动窗口计算 beta"""
    result = np.empty(len(df1_group))
    result[:] = np.nan  # 初始化结果为 NaN

    # 滚动计算 beta
    for i in range(p - 1, len(df1_group)):
        window_y = df1_group.iloc[i - p + 1 : i + 1].values
        window_x = df2_group.iloc[:p].values if df1_group.shape != df2_group.shape else df2_group.iloc[i - p + 1 : i + 1].values
        result[i] = calculate_beta(window_y, window_x)

    # 返回与输入数据索引一致的 Series
    return pd.Series(result, index=df1_group.index)


def REGBETA(df1: pd.DataFrame, df2: pd.DataFrame, p: int = 5, n_jobs: int = -1):
    """
    计算 df1 和 df2 的滚动回归系数（beta）
    
    参数:
        df1 (pd.DataFrame): 第一个 DataFrame，包含目标变量。
        df2 (pd.DataFrame): 第二个 DataFrame，包含解释变量。
        p (int): 滚动窗口大小。
        n_jobs (int): 并行计算的 CPU 核心数。
    
    返回:
        pd.Series: 滚动回归系数结果。
    """
    assert not (isinstance(df2, np.ndarray) and isinstance(df1, np.ndarray)), "df1与df2不能同时是np.ndarray，至少有一个需要是dataframe，例如$close。"
    if isinstance(df2, np.ndarray) or isinstance(df1, np.ndarray):
        if isinstance(df1, np.ndarray):
            df3 = df1
            df1 = df2
            df2 = df3
            p = min(len(df2), p)
            df2 = pd.Series(df2)
        # 填充缺失值
        df1 = df1.fillna(0)
        
        # 获取分组后的数据
        df1_groups = list(df1.groupby('instrument'))
        df2 = pd.Series(df2[:p])
        
        # 使用 joblib 进行并行计算
        results = Parallel(n_jobs=n_jobs)(
            delayed(rolling_beta)(df1_group, df2, p)
            for _, df1_group in df1_groups
        )
        
        # 将结果合并为一个 Series，并确保索引一致
        result = pd.concat(results)
        result = result.sort_index()  # 按索引排序
        return result
    
    else:
        # 确保 df1 和 df2 的索引一致
        assert df1.index.equals(df2.index), "df1 和 df2 的索引必须对齐"
        
        # 填充缺失值
        df1 = df1.fillna(0)
        df2 = df2.fillna(0)
        
        # 获取分组后的数据
        df1_groups = list(df1.groupby('instrument'))
        df2_groups = list(df2.groupby('instrument'))
        
        # 确保分组顺序一致
        if len(df1_groups) != len(df2_groups):
            raise ValueError("df1 和 df2 的分组数量不一致，请检查数据。")
        
        # 使用 joblib 进行并行计算
        results = Parallel(n_jobs=n_jobs)(
            delayed(rolling_beta)(df1_group, df2_group, p)
            for (_, df1_group), (_, df2_group) in zip(df1_groups, df2_groups)
        )
        
        # 将结果合并为一个 Series，并确保索引一致
        result = pd.concat(results)
        result = result.sort_index()  # 按索引排序
        return result



def calculate_residuals(y, x):
    """计算残差（实际值 - 预测值）"""
    # 添加常数项以计算截距
    X = np.vstack([x, np.ones(len(x))]).T
    # 使用最小二乘法计算回归系数
    beta, intercept = np.linalg.lstsq(X, y, rcond=None)[0]
    # 计算预测值
    y_pred = beta * x + intercept
    # 计算残差（实际值 - 预测值）
    residuals = y - y_pred
    return residuals[-1]  # 返回最后一个残差值（滚动窗口的最新值）

def rolling_residuals(df1_group, df2_group, p):
    """对 df1 和 df2 的滚动窗口计算残差"""
    result = np.empty(len(df1_group))
    result[:] = np.nan  # 初始化结果为 NaN

    # 滚动计算残差
    for i in range(p - 1, len(df1_group)):
        window_y = df1_group.iloc[i - p + 1 : i + 1].values
        window_x = df2_group.iloc[:p].values if df1_group.shape != df2_group.shape else df2_group.iloc[i - p + 1 : i + 1].values
        result[i] = calculate_residuals(window_y, window_x)

    # 返回与输入数据索引一致的 Series
    return pd.Series(result, index=df1_group.index)


def REGRESI(df1: pd.DataFrame, df2: pd.DataFrame, p: int = 5, n_jobs: int = -1):
    """
    计算 df1 和 df2 的滚动残差
    
    参数:
        df1 (pd.DataFrame): 第一个 DataFrame，包含目标变量。
        df2 (pd.DataFrame): 第二个 DataFrame，包含解释变量。
        p (int): 滚动窗口大小。
        n_jobs (int): 并行计算的 CPU 核心数。
    
    返回:
        pd.Series: 滚动残差结果。
    """
    
    assert not (isinstance(df2, np.ndarray) and isinstance(df1, np.ndarray)), "df1与df2不能同时是np.ndarray，至少有一个需要是dataframe，例如$close。"
    if isinstance(df2, np.ndarray) or isinstance(df1, np.ndarray):
        if isinstance(df1, np.ndarray):
            df3 = df1
            df1 = df2
            df2 = df3
            p = min(len(df2), p)
        # 填充缺失值
        df1 = df1.fillna(0)
        df2 = pd.Series(df2[:p])
        
        # 获取分组后的数据
        df1_groups = list(df1.groupby('instrument'))
        
        # 使用 joblib 进行并行计算
        results = Parallel(n_jobs=n_jobs)(
            delayed(rolling_residuals)(df1_group, df2, p)
            for _, df1_group in df1_groups
        )
        
        # 将结果合并为一个 Series，并确保索引一致
        result = pd.concat(results)
        result = result.sort_index()  # 按索引排序
        return result
    
    else:
        # 确保 df1 和 df2 的索引一致
        assert df1.index.equals(df2.index), "df1 和 df2 的索引必须对齐"
        
        # 填充缺失值
        df1 = df1.fillna(0)
        df2 = df2.fillna(0)
        
        # 获取分组后的数据
        df1_groups = list(df1.groupby('instrument'))
        df2_groups = list(df2.groupby('instrument'))
        
        # 确保分组顺序一致
        if len(df1_groups) != len(df2_groups):
            raise ValueError("df1 和 df2 的分组数量不一致，请检查数据。")
        
        # 使用 joblib 进行并行计算
        results = Parallel(n_jobs=n_jobs)(
            delayed(rolling_residuals)(df1_group, df2_group, p)
            for (_, df1_group), (_, df2_group) in zip(df1_groups, df2_groups)
        )
        
        # 将结果合并为一个 Series，并确保索引一致
        result = pd.concat(results)
        result = result.sort_index()  # 按索引排序
        return result


@support_dynamic_window
def SLOPE(df: pd.DataFrame, p: int = 5, n_jobs: int = -1):
    """
    计算序列的斜率
    """
    return REGBETA(df, SEQUENCE(p), p, n_jobs)


@support_dynamic_window
def RESI(df1: pd.DataFrame, p: int = 5, n_jobs: int = -1):
    """
    计算 df1 和 df2 的滚动残差
    """
    return REGRESI(df1, SEQUENCE(p), p, n_jobs)


@support_dynamic_window
def R_SQUARE(df1: pd.DataFrame, p: int = 5, n_jobs: int = -1):
    """
    计算 df1 和 df2 的滚动相关系数平方
    """
    return 1 - TS_VAR(REGRESI(df1, SEQUENCE(p), p, n_jobs), p) / (TS_VAR(df1, p) + 1e-12)

        
### 数学运算
@datatype_adapter
def EXP(df:pd.DataFrame):
    """
    计算序列的指数值
    
    参数:
        df (pd.DataFrame): 输入数据
        
    返回:
        pd.DataFrame: 指数值结果
    """
    return df.apply(np.exp)

@datatype_adapter
def SQRT(df: pd.DataFrame):
    """计算序列的平方根"""
    if isinstance(df, int):
        return np.sqrt(df)
    return df.apply(np.sqrt)

@datatype_adapter
def LOG(df:pd.DataFrame):
    """计算序列的自然对数"""
    if isinstance(df, int):
        return np.log(df)
    return (df+1).apply(np.log)

@datatype_adapter
def INV(df: pd.DataFrame):
    """计算序列的倒数 (1/x)"""
    return 1 / df

@datatype_adapter
@support_dynamic_window
def POW(df:pd.DataFrame, n:int):
    """计算序列的幂"""
    return np.power(df, n)

def FLOOR(df:pd.DataFrame):
    """计算序列的向下取整"""
    return df.apply(np.floor)

@datatype_adapter
@support_dynamic_window
def TS_ZSCORE(df: pd.DataFrame, p:int=5):
    assert isinstance(p, int), ValueError(f"TS_ZSCORE仅接收正整数参数n，接收到{type(p).__name__}")
    # assert isinstance(df, pd.DataFrame), ValueError(f"TS_ZSCORE仅接收pd.DataFrame作为A的类型，接收到{type(df).__name__}")
    return (df - df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).mean())) / df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).std())

@datatype_adapter
def ZSCORE(df):
    # 在每个因子截面上计算平均值和标准差
    mean = df.groupby('datetime').mean()
    std = df.groupby('datetime').std()
    
    # 计算z-score: (X - μ) / σ
    zscore = (df - mean) / std
    return zscore

@datatype_adapter
def SCALE(df: pd.DataFrame, target_sum: float = 1.0):
    """
    将序列标准化使其绝对值之和等于target_sum
    """
    # 计算当前绝对值之和
    abs_sum = ABS(df).groupby('datetime').sum()
    # 进行缩放
    return df.multiply(target_sum).div(abs_sum, axis=0)


@datatype_adapter
def TS_MAD(df: pd.DataFrame, p: int = 5):
    """
    计算时间序列的滚动中位数绝对偏差(Median Absolute Deviation)
    
    MAD = median(|X_i - median(X)|)
    
    参数:
        df (pd.DataFrame): 输入数据
        p (int): 滚动窗口大小
        
    返回:
        pd.DataFrame: 滚动MAD结果
    """
    def rolling_mad(window):
        # 计算窗口内的中位数
        median_val = np.median(window)
        # 计算每个值与中位数的绝对偏差
        abs_dev = np.abs(window - median_val)
        # 返回这些偏差的中位数
        return np.median(abs_dev)
    
    return df.groupby('instrument').transform(
        lambda x: x.rolling(p, min_periods=1).apply(rolling_mad, raw=True)
    )


@datatype_adapter
def TS_QUANTILE(df: pd.DataFrame, p: int = 5, q: float = 0.5):
    """
    计算时间序列的滚动分位数
    
    参数:
        df (pd.DataFrame): 输入数据
        p (int): 滚动窗口大小
        q (float): 分位数，范围在[0, 1]之间
        
    返回:
        pd.DataFrame: 滚动分位数结果
    """
    assert 0 <= q <= 1, "分位数 q 必须在 [0, 1] 之间"
    return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).quantile(q))

@datatype_adapter
def TS_PCTCHANGE(df: pd.DataFrame, p: int = 1):
    """
    计算时间序列的百分比变化
    
    参数:
        df (pd.DataFrame): 输入数据
        p (int): 计算间隔，默认为1（相邻期）
        
    返回:
        pd.DataFrame: 百分比变化结果
    """
    return df.groupby('instrument').transform(lambda x: x.pct_change(periods=p).fillna(0))


def ADD(df1, df2):
    return np.add(df1, df2)
        
def SUBTRACT(df1, df2):
    return np.subtract(df1, df2)
    
def MULTIPLY(df1, df2):
    return np.multiply(df1, df2)
    
def DIVIDE(df1, df2):
    return np.divide(df1, df2)
    
def AND(df1, df2):
    return np.bitwise_and(df1.astype(np.bool_), df2.astype(np.bool_))

def OR(df1, df2):
    return np.bitwise_or(df1.astype(np.bool_), df2.astype(np.bool_))



def MACD(price_df, short_window=12, long_window=26):
    """
    计算MACD指标
    
    参数:
        price_df: pd.DataFrame - 价格数据
        short_window: int - 短期EMA的窗口大小，默认为12
        long_window: int - 长期EMA的窗口大小，默认为26
        
    返回:
        pd.DataFrame: MACD结果
    """
    # 计算短期EMA
    short_ema = EMA(price_df, short_window)
    
    # 计算长期EMA
    long_ema = EMA(price_df, long_window)
    
    # 计算MACD差值
    macd = short_ema - long_ema
    return macd


@support_dynamic_window
def RSI(price_df, window=14):
    """
    计算相对强弱指数(RSI)
    
    参数:
        price_df: pd.DataFrame - 价格数据
        window: int - RSI的窗口大小，默认为14

    返回:
        pd.DataFrame: RSI结果, 值为 0 到 100。
    """
    # 计算价格变化
    price_change = DELTA(price_df, 1)
    
    # 分别计算上涨和下跌（使用向量化操作）
    up = (price_change > 0) * price_change
    down = (price_change < 0) * ABS(price_change)
    
    # 计算EMA
    avg_up = EMA(up, window)
    avg_down = EMA(down, window)
    
    # 计算RSI
    rsi = 100 - (100 / (1 + (avg_up / avg_down)))
    return rsi




def _calculate_rolling_mean(group_data):
    """计算单个组的动态移动平均"""
    price_group, window_group, group_name = group_data
    result = pd.Series(index=price_group.index, dtype=float)
    
    for i in range(len(price_group)):
        curr_window = int(window_group.iloc[i].values)
        if curr_window < 1:
            curr_window = 1
        if i < curr_window:
            result.iloc[i] = price_group.iloc[:i+1].mean()
        else:
            result.iloc[i] = price_group.iloc[i-curr_window+1:i+1].mean()
    
    return group_name, result

def _calculate_rolling_std(group_data):
    """计算单个组的动态标准差"""
    price_group, window_group, group_name = group_data
    result = pd.Series(index=price_group.index, dtype=float)
    
    for i in range(len(price_group)):
        curr_window = int(window_group.iloc[i].values)
        if curr_window < 1:
            curr_window = 1
        if i < curr_window:
            result.iloc[i] = price_group.iloc[:i+1].std()
        else:
            result.iloc[i] = price_group.iloc[i-curr_window+1:i+1].std()
    
    return group_name, result



@datatype_adapter
def BB_MIDDLE(price_df, window, n_jobs=-1):
    """
    计算布林带中轨，支持动态窗口大小和并行计算
    
    参数:
        price_df: pd.DataFrame - 价格数据
        window: int 或 pd.DataFrame - 窗口大小
        n_jobs: int - 并行计算的作业数，默认为-1
    """
    if isinstance(window, (int, float)):
        # 如果window是固定值，使用原来的逻辑
        return price_df.groupby('instrument').transform(lambda x: x.rolling(int(window), min_periods=1).mean())
    else:
        window.index = price_df.index
        # 准备并行计算的数据
        groups_data = [
            (price_group, 
             window.xs(group_name, level='instrument'), 
             group_name)
            for group_name, price_group in price_df.groupby('instrument')
        ]
        
        # 并行计算
        results = Parallel(n_jobs=n_jobs)(
            delayed(_calculate_rolling_mean)(group_data)
            for group_data in groups_data
        )
        
        # 合并结果
        final_result = pd.concat([result for _, result in sorted(results, key=lambda x: x[0])])
        return final_result

@datatype_adapter
def BB_UPPER(price_df, window, n_jobs=-1):
    """
    计算布林带上轨，支持动态窗口大小和并行计算
    
    参数:
        price_df: pd.DataFrame - 价格数据
        window: int 或 pd.DataFrame - 窗口大小
        n_jobs: int - 并行计算的作业数，默认为-1
    """
    
    if isinstance(window, (int, float)):
        # 固定窗口大小的标准差计算
        middle_band = BB_MIDDLE(price_df, window, n_jobs)
        std = price_df.groupby('instrument').transform(lambda x: x.rolling(int(window), min_periods=1).std())
    else:
        window.index = price_df.index
        middle_band = BB_MIDDLE(price_df, window, n_jobs)
        # 准备并行计算的数据
        groups_data = [
            (price_group, 
             window.xs(group_name, level='instrument'), 
             group_name)
            for group_name, price_group in price_df.groupby('instrument')
        ]
        
        # 并行计算标准差
        results = Parallel(n_jobs=n_jobs)(
            delayed(_calculate_rolling_std)(group_data)
            for group_data in groups_data
        )
        
        # 合并结果
        std = pd.concat([result for _, result in sorted(results, key=lambda x: x[0])])
    
    return middle_band + std

@datatype_adapter
def BB_LOWER(price_df, window, n_jobs=-1):
    """
    计算布林带下轨，支持动态窗口大小和并行计算
    
    参数:
        price_df: pd.DataFrame - 价格数据
        window: int 或 pd.DataFrame - 窗口大小
        n_jobs: int - 并行计算的作业数，默认为-1
    """
    
    if isinstance(window, (int, float)):
        # 固定窗口大小的标准差计算
        middle_band = BB_MIDDLE(price_df, window, n_jobs)
        std = price_df.groupby('instrument').transform(lambda x: x.rolling(int(window), min_periods=1).std())
    else:
        window.index = price_df.index
        middle_band = BB_MIDDLE(price_df, window, n_jobs)
        # 准备并行计算的数据
        groups_data = [
            (price_group, 
             window.xs(group_name, level='instrument'), 
             group_name)
            for group_name, price_group in price_df.groupby('instrument')
        ]
        
        # 并行计算标准差
        results = Parallel(n_jobs=n_jobs)(
            delayed(_calculate_rolling_std)(group_data)
            for group_data in groups_data
        )
        
        # 合并结果
        std = pd.concat([result for _, result in sorted(results, key=lambda x: x[0])])
    
    return middle_band - std


@datatype_adapter
def ATR(high_df: pd.DataFrame, low_df: pd.DataFrame, close_df: pd.DataFrame, window: int = 14):
    """
    计算平均真实波动范围 (Average True Range, ATR)

    参数:
        high_df (pd.DataFrame): 最高价
        low_df (pd.DataFrame): 最低价
        close_df (pd.DataFrame): 收盘价
        window (int): ATR 的滚动窗口大小，默认为 14。

    返回:
        pd.DataFrame: ATR 序列，与输入数据索引、分组对齐。
    """
    # 计算真实波动范围 (True Range, TR)
    tr1 = (high_df - low_df).abs()
    tr2 = (high_df - close_df.shift(1)).abs()
    tr3 = (low_df - close_df.shift(1)).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # 计算 ATR
    atr = true_range.groupby("instrument").transform(lambda x: x.rolling(window, min_periods=1).mean())
    # import pdb; pdb.set_trace()
    return atr


@datatype_adapter
def CCI(high_df: pd.DataFrame, low_df: pd.DataFrame, close_df: pd.DataFrame, window: int = 20):
    """
    计算商品通道指数 (Commodity Channel Index, CCI)

    参数:
        high_df (pd.DataFrame): 最高价序列。
        low_df (pd.DataFrame): 最低价序列。
        close_df (pd.DataFrame): 收盘价序列。
        window (int): 计算 CCI 的滚动窗口大小，默认为 20。

    返回:
        pd.DataFrame: CCI 指标，索引与输入对齐，列名为 "CCI"。
    """

    # 典型价格 (Typical Price, TP)
    tp = (high_df + low_df + close_df) / 3

    # TP 的滚动均值
    tp_ma = tp.groupby("instrument").transform(
        lambda x: x.rolling(window, min_periods=1).mean()
    )

    # TP 与其均值的偏差的绝对值
    abs_dev = (tp - tp_ma).abs()

    # 平均偏差 (Mean Deviation)
    mean_dev = abs_dev.groupby("instrument").transform(
        lambda x: x.rolling(window, min_periods=1).mean()
    )

    # 计算 CCI
    cci = (tp - tp_ma) / (0.015 * mean_dev)

    # 返回 DataFrame，与其他指标函数保持一致
    return cci


@datatype_adapter
def BBI(price_df: pd.DataFrame):
    """
    计算多空指标 (BBI)
    """
    return (price_df.groupby("instrument").transform(lambda x: x.rolling(3, min_periods=1).mean()) + 
            price_df.groupby("instrument").transform(lambda x: x.rolling(6, min_periods=1).mean()) + 
            price_df.groupby("instrument").transform(lambda x: x.rolling(12, min_periods=1).mean()) + 
            price_df.groupby("instrument").transform(lambda x: x.rolling(24, min_periods=1).mean())) / 4

@datatype_adapter
def WR(high_df: pd.DataFrame, low_df: pd.DataFrame, close_df: pd.DataFrame, window: int = 14):
    """
    计算威廉指标 (Williams %R)

    参数:
        high_df (pd.DataFrame): 最高价序列。
        low_df (pd.DataFrame): 最低价序列。
        close_df (pd.DataFrame): 收盘价序列。
        window (int): 计算 WR 的滚动窗口大小，默认为 14。

    返回:
        pd.DataFrame: WR 指标，索引与输入对齐，列名为 "WR", 值为 -100 到 0。
    """

    # 计算滚动最大值和最小值
    rolling_high = high_df.groupby("instrument").transform(lambda x: x.rolling(window, min_periods=1).max())
    rolling_low = low_df.groupby("instrument").transform(lambda x: x.rolling(window, min_periods=1).min())

    # 计算 WR
    wr = (rolling_high - close_df) / (rolling_high - rolling_low + 1e-8) * -100
    return wr





def calculate_zigzag_pivots(close_series, pct=0.03):
    """
    计算单个序列的ZigZag转折点
    
    参数:
        close_series: pd.Series - 收盘价序列
        pct: float - 百分比阈值，默认3%
        
    返回:
        list: 转折点列表，每个元素为(index, value, direction, confirm_date)
        confirm_date: 转折点被确认的日期
    
    注意：
        为避免数据窥测问题，转折点的确认需要等到价格反向变化超过阈值后才能确定。
        例如：如果第10天是一个低点，但需要等到第12天价格上涨超过pct%才能确认。
        在这种情况下，第10天的转折点直到第12天才被确认，confirm_date = 第12天。
    """
    if len(close_series) < 2:
        return []
    
    # 转折点列表，存储(index, value, direction, confirm_date)
    # direction: 1表示高点，-1表示低点
    # confirm_date: 转折点被确认的日期
    pivots = []
    
    # 从第一个点开始
    current_idx = close_series.index[0]
    current_price = close_series.iloc[0]
    direction = 0  # 0表示未确定方向，1表示寻找高点，-1表示寻找低点
    
    # 添加第一个点作为初始转折点（确认日期为自己）
    pivots.append((current_idx, current_price, 0, current_idx))
    
    i = 1
    while i < len(close_series):
        idx = close_series.index[i]
        price = close_series.iloc[i]
        
        if direction == 0:
            # 确定初始方向
            change_pct = (price - current_price) / current_price
            if abs(change_pct) >= pct:
                if change_pct > 0:
                    direction = -1  # 价格上涨超过阈值，下一步寻找低点
                else:
                    direction = 1   # 价格下跌超过阈值，下一步寻找高点
                # 更新第一个转折点的方向，确认日期为当前日期
                pivots[0] = (current_idx, current_price, -direction, idx)
                pivots.append((idx, price, direction, idx))
                current_idx = idx
                current_price = price
        
        elif direction == 1:  # 寻找高点
            if price > current_price:
                # 更新当前高点
                current_idx = idx
                current_price = price
                # 更新最后一个转折点，但确认日期还未确定
                pivots[-1] = (current_idx, current_price, direction, None)
            else:
                # 检查是否回撤足够确认低点
                change_pct = (price - current_price) / current_price
                if change_pct <= -pct:
                    # 确认之前的高点，确认日期为当前日期
                    if pivots[-1][3] is None:
                        pivots[-1] = (pivots[-1][0], pivots[-1][1], pivots[-1][2], idx)
                    # 确认新的低点
                    pivots.append((idx, price, -1, idx))
                    current_idx = idx
                    current_price = price
                    direction = -1  # 下一步寻找高点
        
        else:  # direction == -1, 寻找低点
            if price < current_price:
                # 更新当前低点
                current_idx = idx
                current_price = price
                # 更新最后一个转折点，但确认日期还未确定
                pivots[-1] = (current_idx, current_price, direction, None)
            else:
                # 检查是否反弹足够确认高点
                change_pct = (price - current_price) / current_price
                if change_pct >= pct:
                    # 确认之前的低点，确认日期为当前日期
                    if pivots[-1][3] is None:
                        pivots[-1] = (pivots[-1][0], pivots[-1][1], pivots[-1][2], idx)
                    # 确认新的高点
                    pivots.append((idx, price, 1, idx))
                    current_idx = idx
                    current_price = price
                    direction = 1  # 下一步寻找低点
        
        i += 1
    
    # 最后一个转折点可能还没有被确认，我们不应该使用它
    # 过滤掉未确认的转折点
    confirmed_pivots = [(idx, val, direction, confirm_date) 
                       for idx, val, direction, confirm_date in pivots 
                       if confirm_date is not None]
    
    return confirmed_pivots


def get_nth_pivot(close_group, n, pivot_type, pct=0.03):
    """
    高性能增量版本：严格避免数据窥视，使用增量计算优化性能
    时间复杂度从 O(n²) 优化到 O(n)
    
    参数:
        close_group: pd.Series - 单个instrument的价格序列
        n: int - 倒数第n个转折点
        pivot_type: int - 1表示高点，-1表示低点
        pct: float - ZigZag阈值
        
    返回:
        pd.Series - 包含每个日期对应的第n个转折点价格的序列
    """
    result = pd.Series(index=close_group.index, dtype=float)
    result[:] = np.nan
    
    if len(close_group) < 2:
        return result
    
    # 寻找第一个非NaN值作为起始点
    start_idx = 0
    while start_idx < len(close_group) and pd.isna(close_group.iloc[start_idx]):
        start_idx += 1
    
    # 如果整个序列都是NaN，直接返回
    if start_idx >= len(close_group):
        return result
    
    # 增量维护转折点状态 - 关键优化点
    confirmed_pivots = []  # 已确认的转折点 [(position, value, direction)]
    current_extreme_pos = start_idx
    current_extreme_value = close_group.iloc[start_idx]
    current_direction = 0  # 0:未确定, 1:寻找高点, -1:寻找低点
    
    # 逐个处理每个时间点，严格保证只使用历史数据
    for i in range(start_idx + 1, len(close_group)):
        current_price = close_group.iloc[i]
        
        # 跳过NaN值
        if pd.isna(current_price):
            continue
        
        # 增量更新转折点逻辑 - 避免重复计算
        updated = False
        
        if current_direction == 0:
            # 确定初始方向
            change_pct = (current_price - current_extreme_value) / current_extreme_value
            if abs(change_pct) >= pct:
                if change_pct > 0:
                    current_direction = -1  # 寻找低点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, 1))
                else:
                    current_direction = 1   # 寻找高点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, -1))
                
                current_extreme_pos = i
                current_extreme_value = current_price
                updated = True
        
        elif current_direction == 1:  # 寻找高点
            if current_price > current_extreme_value:
                current_extreme_pos = i
                current_extreme_value = current_price
                updated = True
            else:
                change_pct = (current_price - current_extreme_value) / current_extreme_value
                if change_pct <= -pct:
                    # 确认高点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, 1))
                    current_extreme_pos = i
                    current_extreme_value = current_price
                    current_direction = -1
                    updated = True
        
        else:  # current_direction == -1, 寻找低点
            if current_price < current_extreme_value:
                current_extreme_pos = i
                current_extreme_value = current_price
                updated = True
            else:
                change_pct = (current_price - current_extreme_value) / current_extreme_value
                if change_pct >= pct:
                    # 确认低点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, -1))
                    current_extreme_pos = i
                    current_extreme_value = current_price
                    current_direction = 1
                    updated = True
        
        # 查找第n个指定类型的转折点 - 只在有更新时才重新查找
        target_pivots = [pivot for pivot in confirmed_pivots if pivot[2] == pivot_type]
        if len(target_pivots) >= n:
            result.iloc[i] = target_pivots[-n][1]
    
    return result



def get_nth_pivot_days(close_group, n, pivot_type, pct=0.03):
    """
    高性能增量版本：获取每个日期对应的第n个转折点距离该日期的天数
    严格避免数据窥视，使用增量计算优化性能，时间复杂度从 O(n²) 优化到 O(n)
    
    参数:
        close_group: pd.Series - 单个instrument的价格序列
        n: int - 倒数第n个转折点
        pivot_type: int - 1表示高点，-1表示低点
        pct: float - ZigZag阈值
        
    返回:
        pd.Series - 包含每个日期对应的第n个转折点距离该日期天数的序列
    """
    result = pd.Series(index=close_group.index, dtype=float)
    result[:] = np.nan
    
    if len(close_group) < 2:
        return result
    
    # 寻找第一个非NaN值作为起始点
    start_idx = 0
    while start_idx < len(close_group) and pd.isna(close_group.iloc[start_idx]):
        start_idx += 1
    
    # 如果整个序列都是NaN，直接返回
    if start_idx >= len(close_group):
        return result
    
    # 增量维护转折点状态 - 关键优化点
    confirmed_pivots = []  # 已确认的转折点 [(position, value, direction)]
    current_extreme_pos = start_idx
    current_extreme_value = close_group.iloc[start_idx]
    current_direction = 0  # 0:未确定, 1:寻找高点, -1:寻找低点
    
    # 逐个处理每个时间点，严格保证只使用历史数据
    for i in range(start_idx + 1, len(close_group)):
        current_price = close_group.iloc[i]
        
        # 跳过NaN值
        if pd.isna(current_price):
            continue
        
        # 增量更新转折点逻辑 - 避免重复计算
        if current_direction == 0:
            # 确定初始方向
            change_pct = (current_price - current_extreme_value) / current_extreme_value
            if abs(change_pct) >= pct:
                if change_pct > 0:
                    current_direction = -1  # 寻找低点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, 1))
                else:
                    current_direction = 1   # 寻找高点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, -1))
                
                current_extreme_pos = i
                current_extreme_value = current_price
        
        elif current_direction == 1:  # 寻找高点
            if current_price > current_extreme_value:
                current_extreme_pos = i
                current_extreme_value = current_price
            else:
                change_pct = (current_price - current_extreme_value) / current_extreme_value
                if change_pct <= -pct:
                    # 确认高点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, 1))
                    current_extreme_pos = i
                    current_extreme_value = current_price
                    current_direction = -1
        
        else:  # current_direction == -1, 寻找低点
            if current_price < current_extreme_value:
                current_extreme_pos = i
                current_extreme_value = current_price
            else:
                change_pct = (current_price - current_extreme_value) / current_extreme_value
                if change_pct >= pct:
                    # 确认低点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, -1))
                    current_extreme_pos = i
                    current_extreme_value = current_price
                    current_direction = 1
        
        # 查找第n个指定类型的转折点并计算天数差
        target_pivots = [pivot for pivot in confirmed_pivots if pivot[2] == pivot_type]
        if len(target_pivots) >= n:
            target_pivot_pos = target_pivots[-n][0]
            days_diff = i - target_pivot_pos
            result.iloc[i] = days_diff
    
    return result



@datatype_adapter
@support_dynamic_window
def ZIGZAG_TOP(df: pd.DataFrame, n: int = 1, pct: float = 0.03, n_jobs: int = -1):
    """
    计算从后往前数的第n个高点价格
    
    参数:
        df (pd.DataFrame): 输入价格数据
        n (int): 倒数第n个高点，n=1表示最近的第1个高点
        pct (float): ZigZag阈值，默认3%
        n_jobs (int): 并行计算的CPU核心数
        
    返回:
        pd.DataFrame: 第n个高点价格
    """
    assert n >= 1, "n必须大于等于1"
    
    # 填充缺失值
    df = df.ffill()
    
    # 获取分组后的数据
    groups = list(df.groupby('instrument'))
    
    # 使用 joblib 进行并行计算
    results = Parallel(n_jobs=n_jobs)(
        delayed(get_nth_pivot)(group, n, 1, pct)  # 1表示高点
        for _, group in groups
    )
    
    # 将结果合并为一个 Series，并确保索引一致
    result = pd.concat(results, sort=False)
    result = result.sort_index()  # 按索引排序
    
    # 确保返回的索引与输入数据的索引完全一致
    result = result.reindex(df.index)
    return result


@datatype_adapter
@support_dynamic_window
def ZIGZAG_BOTTOM(df: pd.DataFrame, n: int = 1, pct: float = 0.03, n_jobs: int = -1):
    """
    计算从后往前数的第n个低点价格
    
    参数:
        df (pd.DataFrame): 输入价格数据
        n (int): 倒数第n个低点，n=1表示最近的第1个低点
        pct (float): ZigZag阈值，默认3%
        n_jobs (int): 并行计算的CPU核心数
        
    返回:
        pd.DataFrame: 第n个低点价格
    """
    assert n >= 1, "n必须大于等于1"
    
    # 填充缺失值
    df = df.ffill()
    
    # 获取分组后的数据
    groups = list(df.groupby('instrument'))
    
    # 使用 joblib 进行并行计算
    results = Parallel(n_jobs=n_jobs)(
        delayed(get_nth_pivot)(group, n, -1, pct)  # -1表示低点
        for _, group in groups
    )
    
    # 将结果合并为一个 Series，并确保索引一致
    result = pd.concat(results, sort=False)
    result = result.sort_index()  # 按索引排序
    
    # 确保返回的索引与输入数据的索引完全一致
    result = result.reindex(df.index)
    return result


@datatype_adapter
@support_dynamic_window
def ZIGZAG_TOP_DAYS(df: pd.DataFrame, n: int = 1, pct: float = 0.03, n_jobs: int = -1):
    """
    计算从后往前数的第n个高点距离今天的天数
    
    参数:
        df (pd.DataFrame): 输入价格数据
        n (int): 倒数第n个高点，n=1表示最近的第1个高点
        pct (float): ZigZag阈值，默认3%
        n_jobs (int): 并行计算的CPU核心数
        
    返回:
        pd.DataFrame: 第n个高点距离今天的天数
    """
    assert n >= 1, "n必须大于等于1"
    
    # 填充缺失值
    df = df.ffill()
    
    # 获取分组后的数据
    groups = list(df.groupby('instrument'))
    
    # 使用 joblib 进行并行计算
    results = Parallel(n_jobs=n_jobs)(
        delayed(get_nth_pivot_days)(group, n, 1, pct)  # 1表示高点
        for _, group in groups
    )
    
    # 将结果合并为一个 Series，并确保索引一致
    result = pd.concat(results, sort=False)
    result = result.sort_index()  # 按索引排序
    
    # 确保返回的索引与输入数据的索引完全一致
    result = result.reindex(df.index)
    return result


@datatype_adapter
@support_dynamic_window
def ZIGZAG_BOTTOM_DAYS(df: pd.DataFrame, n: int = 1, pct: float = 0.03, n_jobs: int = -1):
    """
    计算从后往前数的第n个低点距离今天的天数
    
    参数:
        df (pd.DataFrame): 输入价格数据
        n (int): 倒数第n个低点，n=1表示最近的第1个低点
        pct (float): ZigZag阈值，默认3%
        n_jobs (int): 并行计算的CPU核心数
        
    返回:
        pd.DataFrame: 第n个低点距离今天的天数
    """
    assert n >= 1, "n必须大于等于1"
    
    # 填充缺失值
    df = df.ffill()
    
    # 获取分组后的数据
    groups = list(df.groupby('instrument'))
    
    # 使用 joblib 进行并行计算
    results = Parallel(n_jobs=n_jobs)(
        delayed(get_nth_pivot_days)(group, n, -1, pct)  # -1表示低点
        for _, group in groups
    )
    
    # 将结果合并为一个 Series，并确保索引一致
    result = pd.concat(results, sort=False)
    result = result.sort_index()  # 按索引排序
    
    # 确保返回的索引与输入数据的索引完全一致
    result = result.reindex(df.index)
    return result


    


def get_highest_pivot_in_lookback_fast_incremental(close_group, n, pct=0.03):
    """
    高性能增量版本：在回望区间内寻找价格最高的高点
    严格避免数据窥视，使用增量计算优化性能
    
    参数:
        close_group: pd.Series - 单个instrument的价格序列
        n: int - 回望区间天数
        pct: float - ZigZag阈值
        
    返回:
        pd.Series - 包含每个日期对应的回望区间内最高高点价格的序列
    """
    result = pd.Series(index=close_group.index, dtype=float)
    result[:] = np.nan
    
    if len(close_group) < 2:
        return result
    
    # 寻找第一个非NaN值作为起始点
    start_idx = 0
    while start_idx < len(close_group) and pd.isna(close_group.iloc[start_idx]):
        start_idx += 1
    
    # 如果整个序列都是NaN，直接返回
    if start_idx >= len(close_group):
        return result
    
    # 增量维护转折点状态
    confirmed_pivots = []  # 已确认的转折点 [(position, value, direction)]
    current_extreme_pos = start_idx
    current_extreme_value = close_group.iloc[start_idx]
    current_direction = 0  # 0:未确定, 1:寻找高点, -1:寻找低点
    
    # 逐个处理每个时间点，严格保证只使用历史数据
    for i in range(start_idx + 1, len(close_group)):
        current_price = close_group.iloc[i]
        
        # 跳过NaN值
        if pd.isna(current_price):
            continue
        
        # 增量更新转折点逻辑
        if current_direction == 0:
            # 确定初始方向
            change_pct = (current_price - current_extreme_value) / current_extreme_value
            if abs(change_pct) >= pct:
                if change_pct > 0:
                    current_direction = -1  # 寻找低点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, 1))
                else:
                    current_direction = 1   # 寻找高点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, -1))
                
                current_extreme_pos = i
                current_extreme_value = current_price
        
        elif current_direction == 1:  # 寻找高点
            if current_price > current_extreme_value:
                current_extreme_pos = i
                current_extreme_value = current_price
            else:
                change_pct = (current_price - current_extreme_value) / current_extreme_value
                if change_pct <= -pct:
                    # 确认高点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, 1))
                    current_extreme_pos = i
                    current_extreme_value = current_price
                    current_direction = -1
        
        else:  # current_direction == -1, 寻找低点
            if current_price < current_extreme_value:
                current_extreme_pos = i
                current_extreme_value = current_price
            else:
                change_pct = (current_price - current_extreme_value) / current_extreme_value
                if change_pct >= pct:
                    # 确认低点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, -1))
                    current_extreme_pos = i
                    current_extreme_value = current_price
                    current_direction = 1
        
        # 在回望区间内寻找价格最高的高点
        lookback_start = max(0, i - n + 1)
        high_pivots_in_lookback = [
            (pos, val) for pos, val, direction in confirmed_pivots
            if direction == 1 and lookback_start <= pos <= i
        ]
        
        if high_pivots_in_lookback:
            # 找到价格最高的高点
            highest_pivot = max(high_pivots_in_lookback, key=lambda x: x[1])
            result.iloc[i] = highest_pivot[1]
    
    return result


def get_lowest_pivot_in_lookback_fast_incremental(close_group, n, pct=0.03):
    """
    高性能增量版本：在回望区间内寻找价格最低的低点
    严格避免数据窥视，使用增量计算优化性能
    
    参数:
        close_group: pd.Series - 单个instrument的价格序列
        n: int - 回望区间天数
        pct: float - ZigZag阈值
        
    返回:
        pd.Series - 包含每个日期对应的回望区间内最低低点价格的序列
    """
    result = pd.Series(index=close_group.index, dtype=float)
    result[:] = np.nan
    
    if len(close_group) < 2:
        return result
    
    # 寻找第一个非NaN值作为起始点
    start_idx = 0
    while start_idx < len(close_group) and pd.isna(close_group.iloc[start_idx]):
        start_idx += 1
    
    # 如果整个序列都是NaN，直接返回
    if start_idx >= len(close_group):
        return result
    
    # 增量维护转折点状态
    confirmed_pivots = []  # 已确认的转折点 [(position, value, direction)]
    current_extreme_pos = start_idx
    current_extreme_value = close_group.iloc[start_idx]
    current_direction = 0  # 0:未确定, 1:寻找高点, -1:寻找低点
    
    # 逐个处理每个时间点，严格保证只使用历史数据
    for i in range(start_idx + 1, len(close_group)):
        current_price = close_group.iloc[i]
        
        # 跳过NaN值
        if pd.isna(current_price):
            continue
        
        # 增量更新转折点逻辑
        if current_direction == 0:
            # 确定初始方向
            change_pct = (current_price - current_extreme_value) / current_extreme_value
            if abs(change_pct) >= pct:
                if change_pct > 0:
                    current_direction = -1  # 寻找低点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, 1))
                else:
                    current_direction = 1   # 寻找高点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, -1))
                
                current_extreme_pos = i
                current_extreme_value = current_price
        
        elif current_direction == 1:  # 寻找高点
            if current_price > current_extreme_value:
                current_extreme_pos = i
                current_extreme_value = current_price
            else:
                change_pct = (current_price - current_extreme_value) / current_extreme_value
                if change_pct <= -pct:
                    # 确认高点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, 1))
                    current_extreme_pos = i
                    current_extreme_value = current_price
                    current_direction = -1
        
        else:  # current_direction == -1, 寻找低点
            if current_price < current_extreme_value:
                current_extreme_pos = i
                current_extreme_value = current_price
            else:
                change_pct = (current_price - current_extreme_value) / current_extreme_value
                if change_pct >= pct:
                    # 确认低点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, -1))
                    current_extreme_pos = i
                    current_extreme_value = current_price
                    current_direction = 1
        

        # 在回望区间内寻找价格最低的低点
        lookback_start = max(0, i - n + 1)
        low_pivots_in_lookback = [
            (pos, val) for pos, val, direction in confirmed_pivots
            if direction == -1 and lookback_start <= pos <= i
        ]
        
        if low_pivots_in_lookback:
            # 找到价格最低的低点
            lowest_pivot = min(low_pivots_in_lookback, key=lambda x: x[1])
            result.iloc[i] = lowest_pivot[1]
    
    return result


def get_highest_pivot_days_in_lookback_fast_incremental(close_group, n, pct=0.03):
    """
    高性能增量版本：在回望区间内寻找价格最高的高点距离今天的天数
    严格避免数据窥视，使用增量计算优化性能
    
    参数:
        close_group: pd.Series - 单个instrument的价格序列
        n: int - 回望区间天数
        pct: float - ZigZag阈值
        
    返回:
        pd.Series - 包含每个日期对应的回望区间内最高高点距离该日期天数的序列
    """
    result = pd.Series(index=close_group.index, dtype=float)
    result[:] = np.nan
    
    if len(close_group) < 2:
        return result
    
    # 寻找第一个非NaN值作为起始点
    start_idx = 0
    while start_idx < len(close_group) and pd.isna(close_group.iloc[start_idx]):
        start_idx += 1
    
    # 如果整个序列都是NaN，直接返回
    if start_idx >= len(close_group):
        return result
    
    # 增量维护转折点状态
    confirmed_pivots = []  # 已确认的转折点 [(position, value, direction)]
    current_extreme_pos = start_idx
    current_extreme_value = close_group.iloc[start_idx]
    current_direction = 0  # 0:未确定, 1:寻找高点, -1:寻找低点
    
    # 逐个处理每个时间点，严格保证只使用历史数据
    for i in range(start_idx + 1, len(close_group)):
        current_price = close_group.iloc[i]
        
        # 跳过NaN值
        if pd.isna(current_price):
            continue
        
        # 增量更新转折点逻辑
        if current_direction == 0:
            # 确定初始方向
            change_pct = (current_price - current_extreme_value) / current_extreme_value
            if abs(change_pct) >= pct:
                if change_pct > 0:
                    current_direction = -1  # 寻找低点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, 1))
                else:
                    current_direction = 1   # 寻找高点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, -1))
                
                current_extreme_pos = i
                current_extreme_value = current_price
        
        elif current_direction == 1:  # 寻找高点
            if current_price > current_extreme_value:
                current_extreme_pos = i
                current_extreme_value = current_price
            else:
                change_pct = (current_price - current_extreme_value) / current_extreme_value
                if change_pct <= -pct:
                    # 确认高点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, 1))
                    current_extreme_pos = i
                    current_extreme_value = current_price
                    current_direction = -1
        
        else:  # current_direction == -1, 寻找低点
            if current_price < current_extreme_value:
                current_extreme_pos = i
                current_extreme_value = current_price
            else:
                change_pct = (current_price - current_extreme_value) / current_extreme_value
                if change_pct >= pct:
                    # 确认低点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, -1))
                    current_extreme_pos = i
                    current_extreme_value = current_price
                    current_direction = 1
        
        # 在回望区间内寻找价格最高的高点并计算天数差
        lookback_start = max(0, i - n + 1) # 回望区间开始位置

        # 回望区间内寻找价格最高的高点
        high_pivots_in_lookback = [
            (pos, val) for pos, val, direction in confirmed_pivots
            if direction == 1 and lookback_start <= pos <= i
        ]
        
        if high_pivots_in_lookback:
            # 找到价格最高的高点
            highest_pivot = max(high_pivots_in_lookback, key=lambda x: x[1])
            days_diff = i - highest_pivot[0]
            result.iloc[i] = days_diff
    
    return result


def get_lowest_pivot_days_in_lookback_fast_incremental(close_group, n, pct=0.03):
    """
    高性能增量版本：在回望区间内寻找价格最低的低点距离今天的天数
    严格避免数据窥视，使用增量计算优化性能
    
    参数:
        close_group: pd.Series - 单个instrument的价格序列
        n: int - 回望区间天数
        pct: float - ZigZag阈值
        
    返回:
        pd.Series - 包含每个日期对应的回望区间内最低低点距离该日期天数的序列
    """
    result = pd.Series(index=close_group.index, dtype=float)
    result[:] = np.nan
    
    if len(close_group) < 2:
        return result
    
    # 寻找第一个非NaN值作为起始点
    start_idx = 0
    while start_idx < len(close_group) and pd.isna(close_group.iloc[start_idx]):
        start_idx += 1
    
    # 如果整个序列都是NaN，直接返回
    if start_idx >= len(close_group):
        return result
    
    # 增量维护转折点状态
    confirmed_pivots = []  # 已确认的转折点 [(position, value, direction)]
    current_extreme_pos = start_idx
    current_extreme_value = close_group.iloc[start_idx]
    current_direction = 0  # 0:未确定, 1:寻找高点, -1:寻找低点
    
    # 逐个处理每个时间点，严格保证只使用历史数据
    for i in range(start_idx + 1, len(close_group)):
        current_price = close_group.iloc[i]
        
        # 跳过NaN值
        if pd.isna(current_price):
            continue
        
        # 增量更新转折点逻辑
        if current_direction == 0:
            # 确定初始方向
            change_pct = (current_price - current_extreme_value) / current_extreme_value
            if abs(change_pct) >= pct:
                if change_pct > 0:
                    current_direction = -1  # 寻找低点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, 1))
                else:
                    current_direction = 1   # 寻找高点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, -1))
                
                current_extreme_pos = i
                current_extreme_value = current_price
        
        elif current_direction == 1:  # 寻找高点
            if current_price > current_extreme_value:
                current_extreme_pos = i
                current_extreme_value = current_price
            else:
                change_pct = (current_price - current_extreme_value) / current_extreme_value
                if change_pct <= -pct:
                    # 确认高点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, 1))
                    current_extreme_pos = i
                    current_extreme_value = current_price
                    current_direction = -1
        
        else:  # current_direction == -1, 寻找低点
            if current_price < current_extreme_value:
                current_extreme_pos = i
                current_extreme_value = current_price
            else:
                change_pct = (current_price - current_extreme_value) / current_extreme_value
                if change_pct >= pct:
                    # 确认低点
                    confirmed_pivots.append((current_extreme_pos, current_extreme_value, -1))
                    current_extreme_pos = i
                    current_extreme_value = current_price
                    current_direction = 1
        
        # 在回望区间内寻找价格最低的低点并计算天数差
        lookback_start = max(0, i - n + 1)
        low_pivots_in_lookback = [
            (pos, val) for pos, val, direction in confirmed_pivots
            if direction == -1 and lookback_start <= pos <= i
        ]
        
        if low_pivots_in_lookback:
            # 找到价格最低的低点
            lowest_pivot = min(low_pivots_in_lookback, key=lambda x: x[1])
            days_diff = i - lowest_pivot[0]
            result.iloc[i] = days_diff
    
    return result


@datatype_adapter
@support_dynamic_window
def ZIGZAG_HIGHEST_TOP(df: pd.DataFrame, n: int = 240, pct: float = 0.03, n_jobs: int = -1):
    """
    在回望区间内寻找价格最高的高点
    
    参数:
        df (pd.DataFrame): 输入价格数据
        n (int): 回望区间天数
        pct (float): ZigZag阈值，默认3%
        n_jobs (int): 并行计算的CPU核心数
        
    返回:
        pd.DataFrame: 回望区间内最高的高点价格
    """
    assert n >= 1, f"回望区间n必须大于等于1, 当前n={n}"
    
    # 填充缺失值
    df = df.ffill()
    
    # 获取分组后的数据
    groups = list(df.groupby('instrument'))
    
    # 使用 joblib 进行并行计算
    results = Parallel(n_jobs=n_jobs)(
        delayed(get_highest_pivot_in_lookback_fast_incremental)(group, n, pct)
        for _, group in groups
    )
    
    # 将结果合并为一个 Series，并确保索引一致
    result = pd.concat(results, sort=False)
    result = result.sort_index()  # 按索引排序
    
    # 确保返回的索引与输入数据的索引完全一致
    result = result.reindex(df.index)
    return result


@datatype_adapter
@support_dynamic_window
def ZIGZAG_LOWEST_BOTTOM(df: pd.DataFrame, n: int = 240, pct: float = 0.03, n_jobs: int = -1):
    """
    在回望区间内寻找价格最低的低点
    
    参数:
        df (pd.DataFrame): 输入价格数据
        n (int): 回望区间天数
        pct (float): ZigZag阈值，默认3%
        n_jobs (int): 并行计算的CPU核心数
        
    返回:
        pd.DataFrame: 回望区间内最低的低点价格
    """
    assert n >= 1, "回望区间n必须大于等于1"
    
    # 填充缺失值
    df = df.ffill()
    
    # 获取分组后的数据
    groups = list(df.groupby('instrument'))
    
    # 使用 joblib 进行并行计算
    results = Parallel(n_jobs=n_jobs)(
        delayed(get_lowest_pivot_in_lookback_fast_incremental)(group, n, pct)
        for _, group in groups
    )
    
    # 将结果合并为一个 Series，并确保索引一致
    result = pd.concat(results, sort=False)
    result = result.sort_index()  # 按索引排序
    
    # 确保返回的索引与输入数据的索引完全一致
    result = result.reindex(df.index)
    return result


@datatype_adapter
@support_dynamic_window
def ZIGZAG_HIGHEST_TOP_DAYS(df: pd.DataFrame, n: int = 240, pct: float = 0.03, n_jobs: int = -1):
    """
    在回望区间内寻找价格最高的高点距离今天的天数
    
    参数:
        df (pd.DataFrame): 输入价格数据
        n (int): 回望区间天数
        pct (float): ZigZag阈值，默认3%
        n_jobs (int): 并行计算的CPU核心数
        
    返回:
        pd.DataFrame: 回望区间内最高的高点距离今天的天数
    """
    assert n >= 1, "回望区间n必须大于等于1"
    
    # 填充缺失值
    df = df.ffill()
    
    # 获取分组后的数据
    groups = list(df.groupby('instrument'))
    
    # 使用 joblib 进行并行计算
    results = Parallel(n_jobs=n_jobs)(
        delayed(get_highest_pivot_days_in_lookback_fast_incremental)(group, n, pct)
        for _, group in groups
    )
    
    # 将结果合并为一个 Series，并确保索引一致
    result = pd.concat(results, sort=False)
    result = result.sort_index()  # 按索引排序
    
    # 确保返回的索引与输入数据的索引完全一致
    result = result.reindex(df.index)
    return result


@datatype_adapter
@support_dynamic_window
def ZIGZAG_LOWEST_BOTTOM_DAYS(df: pd.DataFrame, n: int = 240, pct: float = 0.03, n_jobs: int = -1):
    """
    在回望区间内寻找价格最低的低点距离今天的天数
    
    参数:
        df (pd.DataFrame): 输入价格数据
        n (int): 回望区间天数
        pct (float): ZigZag阈值，默认3%
        n_jobs (int): 并行计算的CPU核心数
        
    返回:
        pd.DataFrame: 回望区间内最低的低点距离今天的天数
    """
    assert n >= 1, "回望区间n必须大于等于1"
    
    # 填充缺失值
    df = df.ffill()
    
    # 获取分组后的数据
    groups = list(df.groupby('instrument'))
    
    # 使用 joblib 进行并行计算
    results = Parallel(n_jobs=n_jobs)(
        delayed(get_lowest_pivot_days_in_lookback_fast_incremental)(group, n, pct)
        for _, group in groups
    )
    
    # 将结果合并为一个 Series，并确保索引一致
    result = pd.concat(results, sort=False)
    result = result.sort_index()  # 按索引排序
    
    # 确保返回的索引与输入数据的索引完全一致
    result = result.reindex(df.index)
    return result







# @datatype_adapter
# def XS_OUTER_UPPER(high_df: pd.DataFrame, window: int = 100):
#     """
#     薛斯通道外上轨（长期压力线）
#     取 ``window`` 日最高价的滚动最高值。
#     参数:
#         high_df (pd.DataFrame): 最高价序列。
#         window (int): 通道周期，默认为 100。
#     返回:
#         pd.DataFrame: 外上轨。
#     """
#     return high_df.groupby("instrument").transform(lambda x: x.rolling(window, min_periods=1).max())


# @datatype_adapter
# def XS_OUTER_LOWER(low_df: pd.DataFrame, window: int = 100):
#     """
#     薛斯通道外下轨（长期支撑线）
#     取 ``window`` 日最低价的滚动最低值。
#     参数:
#         low_df (pd.DataFrame): 最低价序列。
#         window (int): 通道周期，默认为 100。
#     返回:
#         pd.DataFrame: 外下轨。
#     """
#     return low_df.groupby("instrument").transform(lambda x: x.rolling(window, min_periods=1).min())


# @datatype_adapter
# def XS_INNER_UPPER(high_df: pd.DataFrame, window: int = 10):
#     """
#     薛斯通道内上轨（短期压力线）
#     取 ``window`` 日最高价的滚动最高值。
#     参数:
#         high_df (pd.DataFrame): 最高价序列。
#         window (int): 通道周期，默认为 10。
#     返回:
#         pd.DataFrame: 内上轨。
#     """
#     return high_df.groupby("instrument").transform(lambda x: x.rolling(window, min_periods=1).max())


# @datatype_adapter
# def XS_INNER_LOWER(low_df: pd.DataFrame, window: int = 10):
#     """
#     薛斯通道内下轨（短期支撑线）
#     取 ``window`` 日最低价的滚动最低值。
#     参数:
#         low_df (pd.DataFrame): 最低价序列。
#         window (int): 通道周期，默认为 10。
#     返回:
#         pd.DataFrame: 内下轨。
#     """
#     return low_df.groupby("instrument").transform(lambda x: x.rolling(window, min_periods=1).min())


# @datatype_adapter
# def DONCHIAN_UPPER(high_df: pd.DataFrame, window: int = 20):
#     """
#     唐安奇通道上轨（Donchian Upper Band）
#     取最近 ``window`` 个周期最高价的滚动最高值。
#     参数:
#         high_df (pd.DataFrame): 最高价序列。
#         window (int): 通道窗口大小，默认为 20。
#     返回:
#         pd.DataFrame: 上轨。
#     """
#     return high_df.groupby("instrument").transform(lambda x: x.rolling(window, min_periods=1).max())


# @datatype_adapter
# def DONCHIAN_LOWER(low_df: pd.DataFrame, window: int = 20):
#     """
#     唐安奇通道下轨（Donchian Lower Band）
#     取最近 ``window`` 个周期最低价的滚动最低值。
#     参数:
#         low_df (pd.DataFrame): 最低价序列。
#         window (int): 通道窗口大小，默认为 20。
#     返回:
#         pd.DataFrame: 下轨。
#     """
#     return low_df.groupby("instrument").transform(lambda x: x.rolling(window, min_periods=1).min())


# @datatype_adapter
# def DONCHIAN_MIDDLE(high_df: pd.DataFrame, low_df: pd.DataFrame, window: int = 20):
#     """
#     唐安奇通道中轨（Donchian Middle Band）
#     为上轨与下轨的平均值。
#     参数:
#         high_df (pd.DataFrame): 最高价序列。
#         low_df (pd.DataFrame): 最低价序列。
#         window (int): 通道窗口大小，默认为 20。
#     返回:
#         pd.DataFrame: 中轨。
#     """
#     upper = DONCHIAN_UPPER(high_df, window)
#     lower = DONCHIAN_LOWER(low_df, window)
#     return (upper + lower) / 2.0


def calculate_barslast(condition_group):
    """
    计算条件最后一次为真到当前时间的天数
    
    参数:
        condition_group: pd.Series - 单个instrument的条件序列
        
    返回:
        pd.Series - 包含每个日期对应的BARSLAST值的序列
    """
    result = pd.Series(index=condition_group.index, dtype=float)
    result[:] = 0
    
    if len(condition_group) == 0:
        return result
    
    # 记录条件最后一次为真的位置
    last_true_pos = -1
    
    for i in range(len(condition_group)):
        current_value = condition_group.iloc[i]
        
        # 如果当前条件为真，更新last_true_pos
        if pd.notna(current_value) and current_value:
            last_true_pos = i
        
        # 计算距离最后一次为真的天数
        if last_true_pos == -1:
            # 如果条件从未为真，返回0
            result.iloc[i] = 0
        else:
            # 返回当前位置到最后一次为真的位置的差值
            result.iloc[i] = i - last_true_pos
    
    return result


@datatype_adapter
def BARSLAST(condition: pd.DataFrame, n_jobs: int = -1):
    """
    计算条件最后一次为真到当前时间的天数
    
    参数:
        condition (pd.DataFrame): 条件序列，True/False 或 1/0
        n_jobs (int): 并行计算的CPU核心数
        
    返回:
        pd.DataFrame: 每个日期条件最后一次为真的天数
    """
    # 将条件转换为布尔值
    condition = condition.astype(bool)
    
    # 获取分组后的数据
    groups = list(condition.groupby('instrument'))
    
    # 使用 joblib 进行并行计算
    results = Parallel(n_jobs=n_jobs)(
        delayed(calculate_barslast)(group)
        for _, group in groups
    )
    
    # 将结果合并为一个 Series，并确保索引一致
    result = pd.concat(results, sort=False)
    result = result.sort_index()  # 按索引排序
    
    # 确保返回的索引与输入数据的索引完全一致
    result = result.reindex(condition.index)
    return result



def GOLDEN_KEY(df: pd.DataFrame) -> pd.Series:
    """
    金钥匙函数：当5日、20日、90日均线刚开始多头排列时返回True（前一天未形成，后一天刚形成）
    多头排列定义：MA5 > MA20 > MA90

    参数:
        df (pd.DataFrame): 包含价格数据的DataFrame，需有'instrument'和'datetime'多级索引
        price_col (str): 价格列名，默认为'close'

    返回:
        pd.Series: 与df同索引的布尔序列，True表示刚形成多头排列
    """
    # 计算均线
    ma5 = df.groupby('instrument').transform(lambda x: x.rolling(5, min_periods=5).mean())
    ma20 = df.groupby('instrument').transform(lambda x: x.rolling(20, min_periods=20).mean())
    ma90 = df.groupby('instrument').transform(lambda x: x.rolling(90, min_periods=90).mean())

    # 多头排列条件
    bull = (ma5 > ma20) & (ma20 > ma90)

    # shift(1)判断“刚开始”多头排列
    just_formed = bull & (~bull.groupby('instrument').shift(1).fillna(False))

    return just_formed
