"""
测试表达式是否正确

# 使用注意事项：
1. 读取的df格式为多重索引，第一层为datetime，第二层为instrument。
2. 大部分内置函数已经对该格式df进行适配，先进行groupby，然后对每个instrument进行计算。


## 数据格式
### df样例
                            open    high     low   close      volume       amount  change  pct_chg  adj_factor    adj_open    adj_high     adj_low   adj_close  his_low  his_high  ...  buy_elg_amount  sell_elg_vol  sell_elg_amount  net_mf_vol  net_mf_amount  bench_open  bench_high  bench_low  bench_close  bench_preclose  bench_volume  bench_amount  bench_turn  bench_return  industry
    datetime   instrument                                                                                                                                                           ...                                                                                                                                                                                                          
    2021-01-04 000008.SZ     2.54    2.55    2.51    2.52  13795696.0   34796286.0   -0.02  -0.0079     22.4083   56.917082   57.141165   56.244833   56.468916      0.1      13.9  ...       2407000.0     2275500.0        5743900.0  -4727900.0    -11880100.0   6395.6118   6501.5892  6359.0797    6482.7868       6367.1149  1.866212e+10  2.111269e+11    1.918022      0.000000      机械设备
            000009.SZ     7.52    7.93    7.47    7.79  81454236.0  633654156.0    0.26   0.0345      8.8815   66.788880   70.430295   66.344805   69.186885      0.3      15.0  ...      65340800.0     6991600.0       54265000.0   9569100.0     74761100.0   6395.6118   6501.5892  6359.0797    6482.7868       6367.1149  1.866212e+10  2.111269e+11    1.918022      0.000000      电力设备
            000012.SZ     7.38    7.77    7.38    7.65  99099916.0  757568333.0    0.27   0.0366     26.7784  197.624592  208.068168  197.624592  204.854760      0.2      12.4  ...     121899300.0    12850300.0       98094000.0  10839800.0     83146500.0   6395.6118   6501.5892  6359.0797    6482.7868       6367.1149  1.866212e+10  2.111269e+11    1.918022      0.000000      建筑材料
            000021.SZ    19.11   19.60   18.88   19.42  22785985.0  439290164.0    0.41   0.0216     14.0395  268.294845  275.174200  265.065760  272.647090      0.3      27.9  ...      58064700.0     2320800.0       44681000.0   1813300.0     35537200.0   6395.6118   6501.5892  6359.0797    6482.7868       6367.1149  1.866212e+10  2.111269e+11    1.918022      0.000000        电子
            000027.SZ     6.11    6.34    6.03    6.25  89799813.0  559318152.0    0.16   0.0263     16.3984  100.194224  103.965856   98.882352  102.490000      0.1      12.6  ...      48021900.0     8858000.0       55184000.0  -6079800.0    -37343000.0   6395.6118   6501.5892  6359.0797    6482.7868       6367.1149  1.866212e+10  2.111269e+11    1.918022      0.000000      公用事业
    ...                       ...     ...     ...     ...         ...          ...     ...      ...         ...         ...         ...         ...         ...      ...       ...  ...             ...           ...              ...         ...            ...         ...         ...        ...          ...             ...           ...           ...         ...           ...       ...
    2021-12-31 688002.SH    78.33   79.37   77.50   78.57   2448892.0  191996986.0    0.47   0.0060      1.0030   78.564990   79.608110   77.732500   78.805710     29.4     128.4  ...       8932000.0       75700.0        5921400.0   -212000.0    -16328000.0   7320.9363   7368.1297  7317.7047    7359.4024       7310.9600  1.499090e+10  1.694569e+11    1.331232      0.006626      国防军工
            688029.SH   220.33  221.99  211.21  212.67   1084434.0  232127267.0   -7.90  -0.0358      1.0080  222.092640  223.765920  212.899680  214.371360     58.8     222.6  ...      11998900.0       62500.0       13286900.0   -165000.0    -35084800.0   7320.9363   7368.1297  7317.7047    7359.4024       7310.9600  1.499090e+10  1.694569e+11    1.331232      0.006626      医药生物
            688088.SH    43.70   44.35   43.20   44.06   2273629.0   99891052.0    0.56   0.0129      1.0070   44.005900   44.660450   43.502400   44.368420     33.6     106.4  ...       5167100.0       16700.0         734600.0    -94800.0     -4076100.0   7320.9363   7368.1297  7317.7047    7359.4024       7310.9600  1.499090e+10  1.694569e+11    1.331232      0.006626       计算机
            688099.SH   125.66  131.70  123.80  130.20   2436778.0  312221904.0    4.10   0.0325      1.0020  125.911320  131.963400  124.047600  130.460400     40.8     163.2  ...       6655000.0      119500.0       15461800.0    138800.0     17854700.0   7320.9363   7368.1297  7317.7047    7359.4024       7310.9600  1.499090e+10  1.694569e+11    1.331232      0.006626        电子
            688321.SH    34.68   35.26   34.62   35.01   2313347.0   81086257.0    0.34   0.0098      1.0000   34.680000   35.260000   34.620000   35.010000     33.0     124.2  ...             0.0           0.0              0.0    458000.0     16066400.0   7320.9363   7368.1297  7317.7047    7359.4024       7310.9600  1.499090e+10  1.694569e+11    1.331232      0.006626      医药生物

    [118058 rows x 52 columns]


    **注意**：大部分内置函数已经对该格式df进行适配，先进行groupby，然后对每个instrument进行计算。

## 函数
### 函数样例
    def TS_STD(df:pd.DataFrame, p:int=20):
        # 计算时间序列的滚动标准差(Standard Deviation)
        return df.groupby('instrument').transform(lambda x: x.rolling(p, min_periods=1).std())

### 已支持的函数
    ABS, ADD, AND, ATR, BARSLAST, BB_LOWER, BB_MIDDLE, BB_UPPER, CCI, COUNT, DECAYLINEAR, DELAY, DELTA, DIVIDE, EMA, EXP, FILTER, FLOOR, HIGHDAY, INDUSTRY_NEUTRALIZE, 
    INV, KURT, LOG, LOWDAY, MACD, MAX, MEAN, MEDIAN, MIN, MULTIPLY, OR, PERCENTILE, POW, PROD, RANK, REGBETA, REGRESI, RSI, SCALE, SEQUENCE, SIGN, SKEW, SMA, 
    SQRT, STD, SUBTRACT, SUMAC, SUMIF, TS_ARGMAX, TS_ARGMIN, TS_CORR, TS_COVARIANCE, TS_MAD, TS_MAX, TS_MEAN, TS_MEDIAN, TS_MIN, TS_PCTCHANGE, TS_QUANTILE, 
    TS_RANK, TS_STD, TS_SUM, TS_VAR, TS_ZSCORE, WMA, WR, ZIGZAG_BOTTOM, ZIGZAG_BOTTOM_DAYS, ZIGZAG_TOP, ZIGZAG_TOP_DAYS, ZSCORE
"""

import pdb
import pandas as pd
import numpy as np
from expr_parser import parse_expression
from function_lib import *
import re
import matplotlib.pyplot as plt

def calculate_factor(expr: str, name: str, df: pd.DataFrame):
    # Stock DataFrame
    # print(df)

    # parse expression
    expr = parse_expression(expr)

    # 先检查表达式中是否包含不存在的列引用
    # 找出所有的 $var_name 模式
    var_pattern = r'\$([a-zA-Z_]\w*)'
    variables_in_expr = re.findall(var_pattern, expr)
    
    # 检查是否有不存在的列
    missing_columns = []
    # print(variables_in_expr)
    # print(df.columns)
    for var in variables_in_expr:
        if var not in df.columns:
            missing_columns.append(var)
    
    if missing_columns:
        raise ValueError(f"表达式中引用了不存在的列: {missing_columns}. 可用的列: {list(df.columns)}")

    # replace '$var_name' by 'df['$var_name']' to get the real data
    for col in df.columns:
        expr = expr.replace(f"${col}", f"df['{col}']")

    expr = expr.replace("nan", "np.nan")
    # print(expr) 
    # calculate the factor
    df[name] = eval(expr)
    # print(df[name])

    return df

if __name__ == '__main__':
    # Input factor expression. Do NOT use the variable format like "df['$xxx']" in factor expressions. Instead, you should use "$xxx". 
    
    df_ori = pd.read_pickle('.cache/cached_中证1000_combine_df_2023-01-01_2025-09-01.pkl')
    # df_points = pd.read_csv('.cache/points.csv', index_col=[0, 1], parse_dates=True)
    # df_ori = pd.merge(df_ori, df_points, left_index=True, right_index=True, how='left')
    # 从多重index取[000155.SZ, 000156.SZ]的df_ori

    selected_stocks = ['000869.SZ','603938.SH',]
    code = selected_stocks[1]
    start_date = '2024-09-01'
    end_date = '2025-09-30'
    # 用布尔索引保留这些 instrument 的数据
    df_filtered = df_ori[df_ori.index.get_level_values('instrument').isin(selected_stocks)]


    # import pdb; pdb.set_trace()
    # expr = "($buy_sm_vol + $buy_md_vol - $sell_sm_vol - $sell_md_vol) / ($volume + 1e-8) / ($chip_conct_70 - $chip_conct_90)"
    # expr = "ZIGZAG_HIGHEST_TOP($high, 560)"
    # expr = "ZIGZAG_BOTTOM($low, 1) > ZIGZAG_LOWEST_BOTTOM($low, 120)? $pct_chg: 0" # 最高价右边最低的极点
    expr = "GOLDEN_KEY($close)"
    name = "first_top_before_B_point"
    df1 = calculate_factor(expr, name, df_filtered.copy())
    df2 = calculate_factor("SMA($high, 5)", "xindong xian", df_filtered.copy())
    df3 = calculate_factor("SMA($low, 5)", "baoming xian", df_filtered.copy())


    # df3 = calculate_factor("ZIGZAG_HIGHEST_TOP($high, $pos_point_b)", "highest_top_after_B_point", df_filtered.copy())
    # df4 = calculate_factor("ZIGZAG_HIGHEST_TOP_DAYS($high, $pos_point_b)", "highest_top_days_after_B_point", df_filtered.copy())

    # # 最高的高点等于倒数第一个高点才行
    # df5 = calculate_factor("ZIGZAG_TOP($high, 1)", "last_top_point", df_filtered.copy())
    # df6 = calculate_factor("ZIGZAG_TOP_DAYS($high, 1)", "last_top_days_point", df_filtered.copy())

    # df7 = calculate_factor("DELAY(ZIGZAG_TOP($high, 1), $pos_point_zero)", "top_before_zero_point", df_filtered.copy())
    # df8 = calculate_factor("$pos_point_zero + DELAY(ZIGZAG_TOP_DAYS($high, 1), $pos_point_zero)", "top_days_before_zero_point", df_filtered.copy())

    # import pdb; pdb.set_trace()

    
    # 获取指定股票和时间范围的数据
    stock_data = df_ori.xs(code, level=1).loc[start_date:end_date]
    
    # import pdb; pdb.set_trace()
    # 绘制K线图
    fig, ax = plt.subplots(figsize=(18, 8))
    
    # 准备数据
    dates = stock_data.index
    opens = stock_data['open']
    highs = stock_data['high']
    lows = stock_data['low']
    closes = stock_data['close']
    volumes = stock_data['volume']
    
    # 绘制K线图
    for i, (date, open_price, high_price, low_price, close_price) in enumerate(zip(dates, opens, highs, lows, closes)):
        # 判断涨跌：收盘价 > 开盘价为红色(涨)，否则为绿色(跌)
        color = 'red' if close_price >= open_price else 'green'
        
        # 绘制上下影线
        ax.plot([i, i], [low_price, high_price], color='black', linewidth=0.5)
        
        # 绘制实体
        body_height = abs(close_price - open_price)
        body_bottom = min(open_price, close_price)
        
        if close_price >= open_price:
            # 阳线：空心
            rect = plt.Rectangle((i-0.3, body_bottom), 0.6, body_height, 
                               facecolor='white', edgecolor='red', linewidth=1)
        else:
            # 阴线：实心
            rect = plt.Rectangle((i-0.3, body_bottom), 0.6, body_height, 
                               facecolor='green', edgecolor='green', linewidth=1)
        
        ax.add_patch(rect)

    ax.plot(range(len(dates)), closes.rolling(5).mean(), color='orange', linestyle='-', linewidth=3, label='5MA')
    ax.plot(range(len(dates)), closes.rolling(20).mean(), color='red', linestyle='-', linewidth=3, label='20MA')
    ax.plot(range(len(dates)), closes.rolling(90).mean(), color='green', linestyle='-', linewidth=3, label='90MA')

    # pdb.set_trace()
    ax.plot(range(len(dates)), df2.xs(code, level=1)["xindong xian"][dates], linestyle='--', linewidth=1, label='Xindong Xian')
    ax.plot(range(len(dates)), df3.xs(code, level=1)["baoming xian"][dates], linestyle='--', linewidth=1, label='Baoming Xian')

    # ax.plot(range(len(dates)), (volumes*closes).rolling(20).mean()/(volumes.rolling(20).mean()+1e-8), color='blue', linestyle='-', linewidth=1, label='20VWAP')
    # ax.plot(range(len(dates)), BBI(df_ori['close']).xs(code, level=1).loc[start_date:end_date], color='red', linestyle='-', linewidth=1, label='BBI')
    
    # 设置x轴标签
    ax.set_xlabel('日期')
    ax.set_ylabel('价格')
    ax.set_title(f'{code} K线图 ({start_date} 到 {end_date})')

    # pdb.set_trace()
    mask = df1.xs(code, level=1)[name][dates].astype(bool)
    ax.scatter(
        [i for i, m in enumerate(mask) if m],
        closes[mask] * df1.xs(code, level=1)[name][dates][mask],
        s=60, color='blue', marker='*', edgecolor='black', linewidths=1.5, label='golden key'
    )
    # 绘制零启动点
    # ax.scatter(len(dates)-df_filtered.xs(code, level=1).loc[end_date]['pos_point_zero'], df_filtered.xs(code, level=1).loc[end_date]['point_zero'], s=100, color='blue', marker='s', label='zero point')
    # # 绘制A点
    # ax.scatter(len(dates)-df_filtered.xs(code, level=1).loc[end_date]['pos_point_a'], df_filtered.xs(code, level=1).loc[end_date]['point_a'], s=100, color='red', marker='o', label='A point')
    # # 绘制B点
    # ax.scatter(len(dates)-df_filtered.xs(code, level=1).loc[end_date]['pos_point_b'], df_filtered.xs(code, level=1).loc[end_date]['point_b'], s=100, color='green', marker='s', label='B point')
    # 绘制第一个B点左侧前高
    # ax.hlines(df1.xs(code, level=1).loc[end_date]['first_top_before_B_point'], 
    #           xmin=len(dates)-df2.xs(code, level=1).loc[end_date]['top_days_before_B_point'] - 2, 
    #           xmax=len(dates)-df2.xs(code, level=1).loc[end_date]['top_days_before_B_point'] + 2, 
    #           color='purple', linestyle='--', linewidth=2, label='first top before B point')
    # # 绘制B点右侧最高点
    # ax.hlines(df3.xs(code, level=1).loc[end_date]['highest_top_after_B_point'], 
    #           xmin=len(dates)-df4.xs(code, level=1).loc[end_date]['highest_top_days_after_B_point'] - 2, 
    #           xmax=len(dates)-df4.xs(code, level=1).loc[end_date]['highest_top_days_after_B_point'] + 2, 
    #           color='green', linestyle='--', linewidth=2, label='highest top after B point')
    # # 绘制倒数第一个高点
    # ax.hlines(df5.xs(code, level=1).loc[end_date]['last_top_point'], 
    #           xmin=len(dates)-df6.xs(code, level=1).loc[end_date]['last_top_days_point'] - 2, 
    #           xmax=len(dates)-df6.xs(code, level=1).loc[end_date]['last_top_days_point'] + 2, 
    #           color='blue', linestyle='--', linewidth=2, label='last top point')
    # # 绘制零启动点左侧前高
    # ax.hlines(df7.xs(code, level=1).loc[end_date]['top_before_zero_point'], 
    #           xmin=len(dates)-df8.xs(code, level=1).loc[end_date]['top_days_before_zero_point'] - 2, 
    #           xmax=len(dates)-df8.xs(code, level=1).loc[end_date]['top_days_before_zero_point'] + 2, 
    #           color='purple', linestyle='--', linewidth=2, label='top before zero point')
    # # 用线段连接零启动点与A点
    # ax.plot([len(dates)-df_filtered.xs(code, level=1).loc[end_date]['pos_point_zero'], len(dates)-df_filtered.xs(code, level=1).loc[end_date]['pos_point_a']], [df_filtered.xs(code, level=1).loc[end_date]['point_zero'], df_filtered.xs(code, level=1).loc[end_date]['point_a']], color='blue', linestyle='--')
    # # 用线段连接A点与B点
    # ax.plot([len(dates)-df_filtered.xs(code, level=1).loc[end_date]['pos_point_a'], len(dates)-df_filtered.xs(code, level=1).loc[end_date]['pos_point_b']], [df_filtered.xs(code, level=1).loc[end_date]['point_a'], df_filtered.xs(code, level=1).loc[end_date]['point_b']], color='red', linestyle='--')



    # 设置x轴刻度
    step = max(1, len(dates) // 10)  # 显示大约10个日期标签
    ax.set_xticks(range(0, len(dates), step))
    ax.set_xticklabels([dates[i].strftime('%Y-%m-%d') for i in range(0, len(dates), step)], rotation=45)
    
    # 调整布局
    plt.legend(loc='upper left')
    plt.tight_layout()
    plt.savefig('test_expr2.png', dpi=150, bbox_inches='tight')
    print('K线图已保存为 test_expr2.png')
    # print("一涨时间", df_filtered.xs(code, level=1).loc[end_date]['pos_point_zero'] - df_filtered.xs(code, level=1).loc[end_date]['pos_point_a'])
    # print("二浪回踩时间", df_filtered.xs(code, level=1).loc[end_date]['pos_point_a'] - df_filtered.xs(code, level=1).loc[end_date]['pos_point_b'])
    # plt.show()

    # for date in df_ori.index.get_level_values(0).unique()[-300:]:
    #     df_now = df_ori.loc[:date]
    #     df_now = calculate_factor(expr, name, df_now)
    #     # import pdb; pdb.set_trace()
    #     assert (df_now.loc[date][name] == df1.loc[date][name]).all()
    #     print(df1.loc[date][name])


    # expr = "DELAY($close, TS_ARGMAX($high, 10))"
    # df2 = calculate_factor(expr, name, df_ori)


    # expr = "ZIGZAG_BOTTOM_DAYS($close, 1, 0.03)"
    # name2 = "zigzag_days"
    # df3 = calculate_factor(expr, name2, df_ori)

    # expr = "ZIGZAG_TOP_DAYS($close, 1, 0.03)"
    # df4 = calculate_factor(expr, name2, df_ori)


    # plt.figure(figsize=(10, 5))
    # code = '600062.SH'
    # start_date = '2023-01-04'
    # end_date = '2025-06-06'

    # plt.plot(df1.xs(code, level=1).loc[start_date:end_date]['close']) # 
    # plt.plot(df1.xs(code, level=1).loc[start_date:end_date][name], label=name+"_bottom", color='blue')
    # plt.plot(df2.xs(code, level=1).loc[start_date:end_date][name], label=name+"_top", color='red')
    # plt.legend()

    # plt.twinx()
    # plt.plot(df3.xs(code, level=1).loc[start_date:end_date][name2], label=name2+"_bottom", color='blue', linestyle='--', alpha=0.5)
    # plt.plot(df4.xs(code, level=1).loc[start_date:end_date][name2], label=name2+"_top", color='red', linestyle='--', alpha=0.5)
    # plt.ylim(-10, 300)
    # plt.legend()
    # plt.savefig('test_expr2.png')
    # print('test_expr2.png saved')
    # plt.show()




    