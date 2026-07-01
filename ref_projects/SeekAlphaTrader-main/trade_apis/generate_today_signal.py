'''
主回测文件, 使用FactorStrategy类进行回测
'''
import datetime
import pickle
import os
import re
import argparse
import json
import pyparsing
import requests
import json
import shutil
from typing import Text, List, Dict, Tuple
import pandas as pd
import numpy as np
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_manager.dataloader import BaoStockLoader, TushareLoader
from data_manager.api_dataloader import SeekAlphaDatabaseAPI
from portfolio_manager.portfolio_management import alpha_to_portfolio, AlphaGPTPortfolioManager
from evaluator.performance_evaluation import PerformanceEvaluator
from portfolio_manager.action_management import ActionManager
from data_manager.zip_files import zip_files
from expression_manager.expr_parser import parse_expression
from expression_manager.function_lib import *
from strategy import FactorStrategy  # 导入FactorStrategy类
from tqdm import tqdm
from ml_models import LightGBMModel, XGBoostModel, NoModel
import pdb
import gc
import asyncio

# EXPR = """(
#             (TS_MIN($close, 250) >= 2) \
#             & (ZIGZAG_BOTTOM_DAYS($low,2,0.3) <= 250) \
#             & (ZIGZAG_TOP_DAYS($high,1,0.3) <= ZIGZAG_BOTTOM_DAYS($low,2,0.3)) \
#             & (ZIGZAG_BOTTOM_DAYS($low,2,0.3) - ZIGZAG_TOP_DAYS($high,1,0.3) < ZIGZAG_TOP_DAYS($high,1,0.3) - ZIGZAG_BOTTOM_DAYS($low,1,0.2)) \
#             & (ZIGZAG_BOTTOM($low,1,0.2) > ZIGZAG_BOTTOM($low,2,0.3)) \
#             & (TS_MIN($low, ZIGZAG_TOP_DAYS($high,1,0.3)) / ZIGZAG_TOP($high,1,0.3) < 0.75) \
#             & (TS_MAX($high,ZIGZAG_BOTTOM_DAYS($low,1,0.2)) > TS_MAX(DELAY($high, ZIGZAG_BOTTOM_DAYS($low,1,0.2)), 20)) \
#             & ($close <= ZIGZAG_TOP($high,1,0.3))
#             ) ? RANK(
#             $chip_conct_70 + $chip_conct_90
#             + TS_SUM($amount, 20)/(TS_SUM($volume, 20) + 1e-8)/$close * 5
#             - SUMIF($return < 0, 10, $close - $open)
#             - ($volume / TS_MEAN($volume,10)) * 5
#             + ($his_high / $cost_85pct) * 5
#             ) : nan"""

EXPR = """(
            (TS_MIN($close, 250) >= 2) \
            & (ZIGZAG_BOTTOM_DAYS($low,2,0.3) <= 250) \
            & (ZIGZAG_TOP_DAYS($high,1,0.3) <= ZIGZAG_BOTTOM_DAYS($low,2,0.3)) \
            & (ZIGZAG_BOTTOM_DAYS($low,2,0.3) - ZIGZAG_TOP_DAYS($high,1,0.3) < ZIGZAG_TOP_DAYS($high,1,0.3) - ZIGZAG_BOTTOM_DAYS($low,1,0.2)) \
            & (ZIGZAG_BOTTOM($low,1,0.2) > ZIGZAG_BOTTOM($low,2,0.3)) \
            & (TS_MIN($low, ZIGZAG_TOP_DAYS($high,1,0.3)) / ZIGZAG_TOP($high,1,0.3) < 0.75) \
            & (TS_MAX($high,ZIGZAG_BOTTOM_DAYS($low,1,0.2)) > TS_MAX(DELAY($high, ZIGZAG_BOTTOM_DAYS($low,1,0.2)), 20)) \
            & ($close <= ZIGZAG_TOP($high,1,0.3))
            ) ? RANK(
            $chip_conct_70 + $chip_conct_90
            + TS_SUM($amount, 20)/(TS_SUM($volume, 20) + 1e-8)/$close * 5
            - SUMIF($return < 0, 10, $close - $open)
            - ($volume / TS_MEAN($volume,30)) * 5
            - TS_MIN($low, TS_ARGMAX($high, 20)) / TS_MAX($high, 20)
            + ATR($high, $low, $close, 20) / $close * 5
            + ($his_high / $cost_50pct) * 5
            ) : nan"""



api = SeekAlphaDatabaseAPI(base_url="http://localhost:40042")
# api.insert_trade_strategy(strategy_name="ChipConcentrationBreakout_SeekAlphaStrategy001", strategy_desc="ChipConcentrationBreakout_SeekAlphaStrategy001", factor_names=["expr001"], factor_expressions=[EXPR], extra_params={})



async def generate_oneday_signal(expr:str=None, 
                           date:str=None, 
                           account_info:dict={},
                           lookback_window:int=365*2, 
                           layer_start:float=0,
                           layer_end:float=5,
                           stop_loss_rate:float=0.04,
                           stop_profit_rate:float=0.4,
                           update_freq:str | int = 5,
                           position_size:float=0.8,
                           max_pos_each_stock:float=0.2,
                           stock_pool:str='中证1000',
                           strategy_start_date="2024-01-02", # 生成信号的开始日期 "2025-01-08"
                           backtest_start_time="2023-01-01", 
                           verbose:bool=False,
                           **kwargs) -> dict:
    # 加载策略参数，根据用户选择的股票池获取对应股票指数的数据集ID

    print("layer_start: ", layer_start)
    print("layer_end: ", layer_end)
    date = pd.to_datetime(date)
    backtest_start_time = pd.to_datetime(backtest_start_time)
    backtest_end_time = pd.to_datetime(date)

    index_code = 'sh.000852'

    loader = TushareLoader(
        data_dir='./cache',
    )
    # 获取指数成分股
    constituent_stock_codes = loader.load_index_stocklist_timerange(index_code, backtest_start_time, backtest_end_time, use_cache=True)

    # 获取指数数据
    benchmark_data = api.get_index_data(
        index_list=[index_code.split('.')[1] + '.' + index_code.split('.')[0].upper()],
        start_date=str(backtest_start_time.strftime("%Y-%m-%d")),
        end_date=str(backtest_end_time.strftime("%Y-%m-%d"))
    ).astype(np.float32)
    print("\n\n指数数据：\n {} \n\n".format(benchmark_data))

    # 获取个股数据
    # 从 constituent_stock_codes 字典中提取全部不重复的股票代码
    all_instruments = set()
    for codes in constituent_stock_codes.values():
        all_instruments.update(codes)

    # 调用后端 API 获取合并后的行情数据
    combined_df = api.get_combined_data(
        stock_list=list(all_instruments),
        start_date=str(backtest_start_time.strftime("%Y-%m-%d")),
        end_date=str(backtest_end_time.strftime("%Y-%m-%d"))
    ) # .astype(np.float32)
    

    # 如果close_backadj不存在，则计算
    if 'close_backadj' not in combined_df.columns:
        combined_df.loc[:, 'close_backadj'] = combined_df.loc[:, 'close'] * combined_df.loc[:, 'adj_factor']
        print(f"已根据adj_factor计算close_backadj")

    # 合并benchmark_data和combined_df

    # 获取combined_df和benchmark_data的索引并集
    combined_index = combined_df.index.get_level_values('datetime').unique()
    benchmark_index = benchmark_data.index        
    # 日期取交集并排序
    all_dates = pd.Index(sorted(set(combined_index) & set(benchmark_index)))
    print(f"combined_df日期范围: {combined_index.min()} 到 {combined_index.max()}")
    print(f"benchmark_data日期范围: {benchmark_index.min()} 到 {benchmark_index.max()}")
    print(f"合并后日期范围: {all_dates.min()} 到 {all_dates.max()}")
    print(f"合并后总日期数: {len(all_dates)}")
    # 重新索引benchmark_data和combined_df到all_dates
    benchmark_data = benchmark_data.reindex(all_dates)
    combined_df = combined_df.reindex(level='datetime', labels=all_dates)

    #####################################################################################
    ######  将benchmark_data合并到combined_df中，使得每天每支股票都共享同样的基准数据  ######
    #####################################################################################
    # 重命名benchmark_data的列名，添加'bench_'前缀
    benchmark_data_renamed = benchmark_data.copy()
    benchmark_data_renamed['return'] = (benchmark_data_renamed['close'] / benchmark_data_renamed['close'].shift(1) - 1).fillna(0)
    benchmark_data_renamed.columns = ['bench_' + col for col in benchmark_data_renamed.columns]
    
    # 通过reindex将benchmark_data扩展到MultiIndex
    multi_index = pd.MultiIndex.from_product([all_dates, all_instruments], names=['datetime', 'instrument'])
    
    # 将benchmark_data扩展到MultiIndex
    benchmark_expanded = benchmark_data_renamed.reindex(multi_index.get_level_values('datetime'))
    benchmark_expanded.index = multi_index
    
    # 合并数据
    # combined_df = pd.concat([combined_df, benchmark_expanded], axis=1)
    combined_df = pd.merge(combined_df, benchmark_expanded, left_index=True, right_index=True, how='right').sort_index()
    print(f"已将基准数据合并到combined_df中，新增列: {list(benchmark_data_renamed.columns)}")
    print(f"combined_df现在的列: {list(combined_df.columns)}")
    del multi_index, benchmark_expanded
    gc.collect()

    # 获取股票行业市值等信息
    # stock_info = loader.get_stocks_info(index_code=index_code, codes=all_instruments, use_cache=use_cache)
    stock_info = api.get_stock_industry_l1(list(all_instruments)).fillna('其他')
    print(f"成功加载 {len(stock_info)} 只股票的基本信息")

    # 将行业信息添加到combined_df中
    combined_df['industry'] = combined_df.index.get_level_values('instrument').map(stock_info['l1_name'])
    print(f"已将行业信息添加到combined_df, 共有 {combined_df['industry'].nunique()} 个行业")
    print("\n\n个股数据：\n {} \n\n".format(combined_df))
    del stock_info
    # pdb.set_trace()

    # 确保 MultiIndex 已按 (datetime, instrument) 排序，避免后续使用 pd.IndexSlice 切片时报错
    combined_df = combined_df.sort_index()

    ########################
    ###  成分股掩码计算  ###
    ########################
    # 1. 使用combined_df的索引创建mask
    constituent_mask = pd.DataFrame(False, index=combined_df.index, columns=['is_constituent'], dtype=bool)
    # 同样保证掩码索引已排序
    constituent_mask.sort_index(inplace=True)
    
    # 2. 根据constituent_stock_codes填充mask
    update_dates = pd.Series(constituent_stock_codes.keys())
    update_dates.sort_values(inplace=True)
    for timestamp, stocks in constituent_stock_codes.items():
        # 找到下一个成分股更新日期
        if timestamp == update_dates.iloc[-1]:
            next_update_timestamp = backtest_end_time
        else:
            next_update_timestamp = update_dates[update_dates > timestamp].iloc[0]

        idx = pd.IndexSlice[timestamp:next_update_timestamp, stocks]
        constituent_mask.loc[idx, 'is_constituent'] = True
        print(f"timestamp: {timestamp}-{next_update_timestamp}, stocks: {len(stocks)}")
        assert constituent_mask.isna().sum().sum() == 0

    constituent_mask = constituent_mask.fillna(False).astype(bool)

    data_latest_date = combined_df.index.get_level_values('datetime').unique().to_series().max()

    print("策略起始日期: ", strategy_start_date)
    print("数据最新日期: ", data_latest_date)
    print("当前信号日期: ", date)

    if data_latest_date < date:
        print("数据最新日期小于当前信号日期，将当前信号日期设置为数据最新日期")
        date = data_latest_date
    
    strategy_start_date = pd.to_datetime(strategy_start_date)
    last_update_date = combined_df.index.get_level_values('datetime').unique().to_series().loc[strategy_start_date::update_freq].iloc[-1]

    # 根据portfolio生成信号,并加入止盈止损逻辑
    current_positions_copy = account_info.get('positions', []).copy()
    signals = []

    # import pdb; pdb.set_trace()

    # 先生成所有买入信号
    if last_update_date == date:
        print("调仓日，开始生成信号")
        ml_model = NoModel(
            industry_neutralization=None,
            cross_sectional_norm=False
        )

        # 初始化策略
        strategy = FactorStrategy(
            factor_exprs={"expr001": expr},
            base_features={},
            ml_model=ml_model,
            cache_dir='./pkl_files',
            label_forward_days=kwargs.get('label_forward_days', 4),
        )

        test_df = combined_df.loc[date-pd.Timedelta(days=365*2):date]
        pred_df = strategy._calculate_features(test_df)
        pred_df.rename(columns={pred_df.columns[0]: 'pred'}, inplace=True)

        # 生成Alpha表用于生成当期信号
        alpha_table = pred_df['pred'].mask(~constituent_mask['is_constituent'].loc[date-pd.Timedelta(days=365*2):date].ffill()).unstack()
        alpha_table = alpha_table.reindex(columns=all_instruments)
        # 对齐index与columns
        assert len(alpha_table.columns) == len(all_instruments)



        # 初始化信号生成组件
        action_manager = ActionManager(start_cash=account_info.get('market_value', 5e5), 
                                    stop_loss_rate=stop_loss_rate, 
                                    stop_profit_rate=stop_profit_rate, 
                                    position_size=position_size,
                                    max_pos_each_stock=max_pos_each_stock,
                                    update_freq=update_freq)
        portfolio_manager = AlphaGPTPortfolioManager(update_freq=update_freq, max_pos_each_stock=max_pos_each_stock)
        performance_evaluator = PerformanceEvaluator()



        # 计算上一个调仓日的portfolio
        deal_price_data = combined_df['close'].unstack()
        portfolio, _ = alpha_to_portfolio(alpha=alpha_table.loc[date], # 今日的因子表
                                    current_prices=deal_price_data.loc[date], # 今日收盘价
                                    investment=action_manager.position_size * min(account_info.get('total_asset', 5e5), 5e5), # 根据指数行情计算仓位
                                    layer_start=layer_start,
                                    layer_end=layer_end,
                                    top_k=None,
                                    max_pos_each_stock=action_manager.max_pos_each_stock,
                                    verbose=True)
        
        print("账户总资产: ", account_info.get('total_asset'))
        print("用于生成信号时的资产数额: ", min(account_info.get('total_asset', 5e5), 5e5))
        print(f"当期{last_update_date}因子表非nan值：", alpha_table.loc[last_update_date].loc[~alpha_table.loc[last_update_date].isna()])
        print(f"因子算得当期持仓：", portfolio[portfolio!=0])

        
        to_trade_portfolio = portfolio[portfolio!=0]
        # 生成买入信号
        for stock_code in to_trade_portfolio.index:
            timestamp = date.strftime("%Y-%m-%d %H:%M:%S") # 策略信号日期
            generated_time = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S") # 策略生成信号的时间，改为北京时间
            assert to_trade_portfolio[stock_code] > 0
            order_type = 23
            order_volume = to_trade_portfolio[stock_code]
            last_close_price = combined_df.xs(stock_code, level=1).loc[date, 'close'].astype(np.float64) # 使用昨日收盘价生成的信号，不能偏离太远

            signals.append({
                'strategy_name': 'ChipConcentrationBreakout_SeekAlphaStrategy001',
                'timestamp': timestamp,
                'generated_time': generated_time,
                'stock_code': stock_code,
                'order_type': order_type,
                'order_volume': order_volume,
                'last_close_price': last_close_price
            })
        
        # 再生成所有卖出信号
        for item in current_positions_copy:
            signals.append({
                'strategy_name': 'ChipConcentrationBreakout_SeekAlphaStrategy001',
                'timestamp': date.strftime("%Y-%m-%d %H:%M:%S"),
                'generated_time': (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
                'stock_code': item['stock_code'],
                'order_type': 24,
                'order_volume': item['volume'],
                'last_close_price': 0.01
            })


        # 若有股票同时存在买入卖出信号则相减，留下多的那一方
        signals_buy = [signal for signal in signals if signal['order_type'] == 23]
        signals_sell = [signal for signal in signals if signal['order_type'] == 24]
        for signal_buy in signals_buy:
            for signal_sell in signals_sell:
                if signal_buy['stock_code'] == signal_sell['stock_code']:
                    if signal_buy['order_volume'] > signal_sell['order_volume']:
                        signal_buy['order_volume'] -= signal_sell['order_volume']
                        signals_sell.remove(signal_sell)
                    elif signal_buy['order_volume'] < signal_sell['order_volume']:
                        signal_sell['order_volume'] -= signal_buy['order_volume']
                        signals_buy.remove(signal_buy)
                    else:
                        signals_buy.remove(signal_buy)
                        signals_sell.remove(signal_sell)
        signals = signals_buy + signals_sell
    
    else:
        print("非调仓日，跳过生成信号")
        # 处理止盈止损逻辑
        for item in current_positions_copy:
            if combined_df.xs(item['stock_code'], level=1).loc[date, 'close'] / combined_df.xs(item['stock_code'], level=1).loc[last_update_date, 'close'] <= 1 - stop_loss_rate:
                # 触发止损
                signals.append({
                    'strategy_name': 'ChipConcentrationBreakout_SeekAlphaStrategy001',
                    'timestamp': date.strftime("%Y-%m-%d %H:%M:%S"),
                    'generated_time': (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
                    'stock_code': item['stock_code'],
                    'order_type': 24,
                    'order_volume': item['volume']
                })
            if combined_df.xs(item['stock_code'], level=1).loc[date, 'close'] / float(item['open_price']) >= 1 + stop_profit_rate:
                # 触发止盈
                signals.append({
                    'strategy_name': 'ChipConcentrationBreakout_SeekAlphaStrategy001',
                    'timestamp': date.strftime("%Y-%m-%d %H:%M:%S"),
                    'generated_time': (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
                    'stock_code': item['stock_code'],
                    'order_type': 24,
                    'order_volume': item['volume']
                })

    # print("已止损股票去除后，因子算得当期持仓：", portfolio[portfolio!=0])
    # portfolio.index = deal_price_data.columns


    # # 将当期持仓转为交易信号
    # to_hold = np.where(action_manager.position == portfolio)[0]
    # to_buy = np.where(action_manager.position < portfolio)[0]
    # to_sell = np.where(action_manager.position > portfolio)[0]
    print("="*70)
    for signal in signals:
        print('order_type: ', signal['order_type'], '  stock_code: ', signal['stock_code'], '  order_volume: ', signal['order_volume'])
    print("="*70)
    return signals
        

if __name__ == '__main__':
    signals = asyncio.run(generate_oneday_signal(
        expr=EXPR,
        account_info={"positions": [], "market_value": 5e5},
        date="2025-09-03",
        strategy_start_date="2024-01-09",
        backtest_start_time="2023-01-01",
        lookback_window=365*2,
        use_cache=True,
        stop_loss_rate=0.04,
        stop_profit_rate=0.4,
        position_size=0.8,
        update_freq=5,
        label_forward_days=5,
        max_pos_each_stock=0.2,
        stock_pool="中证1000",
        layer_start=0.0,
        layer_end=5,
        # top_k=10, # 优先使用top_k，若为None，则使用layer_start和layer_end
        pred_score_industry_neutralization=False,
        ))
    
    print(signals)