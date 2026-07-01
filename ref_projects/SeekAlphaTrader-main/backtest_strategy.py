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
import xgboost as xgb
import lightgbm as lgb

from data_manager.dataloader import BaoStockLoader
from portfolio_manager.portfolio_management import AlphaGPTPortfolioManager
from evaluator.performance_evaluation import PerformanceEvaluator
from test.visualization import draw_figures, draw_figures_v2
from portfolio_manager.action_management import ActionManager
from data_manager.zip_files import zip_files
from expr_parser import parse_expression
from function_lib import *
from strategy import FactorStrategy  # 导入FactorStrategy类
from tqdm import tqdm
from ml_models import LightGBMModel, XGBoostModel, NoModel
import pdb


def backtest(exprs:Dict[str, str]=None, date_split:Dict[str, str]=None, use_cache=False, **kwargs) -> dict:
    '''
    回测函数，输入参数为策略参数，输出为回测结果
    '''
    train_start_time = date_split['train_start_time']
    train_end_time = date_split['train_end_time']
    val_start_time = date_split['val_start_time']
    val_end_time = date_split['val_end_time']
    test_start_time = date_split['test_start_time']
    test_end_time = date_split['test_end_time']

    assert test_end_time <= datetime.datetime.now().strftime('%Y-%m-%d'), '测试结束时间不能大于当前时间'

    # 加载策略参数，根据用户选择的股票池获取对应股票指数的数据集ID
    action_manager = ActionManager(**kwargs)

    try:
        backtest_start_time = pd.to_datetime(train_start_time)
        backtest_end_time = pd.to_datetime(test_end_time)

        train_start_time = pd.to_datetime(train_start_time)
        train_end_time = pd.to_datetime(train_end_time)
        val_start_time = pd.to_datetime(val_start_time)
        val_end_time = pd.to_datetime(val_end_time)
        test_start_time = pd.to_datetime(test_start_time)
        test_end_time = pd.to_datetime(test_end_time)

        stockpool_to_indexcode = {
            '上证50': 'sh.000016',
            '中证500': 'sh.000905',
            '沪深300': 'sh.000300',
            '中证1000': 'sh.000852',
            '上证能源': '000032',
            '上证材料': '000033',
            '上证工业': '000034',
            '上证消费': '000036',
            '上证医药': '000037',
            '上证金融': '000038',
            '上证信息': '000039',
            '上证电信': '000040',
            '上证公用': '000041',
            '上证央企': '000042',
            '上证中盘': '000044',
            '上证小盘': '000045',
            '上证中小': '000046',
            '上证全指': '000047',
            '上证国企': '000056',
            '全指成长': '000057',
            '全指价值': '000058',
            # '中证能源': '000928',
            # '中证材料': '000929', 
            # '中证工业': '000930',
            # '中证可选': '000931',
            # '中证消费': '000932',
            # '中证医药': '000933',
            # '中证金融': '000934',
            # '中证信息': '000935',
            # '中证电信': '000936',
            # '中证公用': '000937',
            # '中证民企': '000938',

        }

        index_code = stockpool_to_indexcode[kwargs.get('stock_pool', '中证500')]
        # index_code = 

        ########################
        ######  获取数据  ######
        ########################

        # loader = QMTDataLoader(
        #     data_dir='./data_qmt',
        #     simulate_client=True,
        # )
        loader = BaoStockLoader(
            data_dir='./data_baostock',
        )


        # 获取指数成分股
        constituent_stock_codes = loader.load_index_stocklist_timerange(index_code, backtest_start_time, backtest_end_time, use_cache=use_cache)
        # 获取指数数据
        benchmark_data = loader.load_stock_data(code=index_code if '.' in index_code else f'{index_code}.SH', start_date=backtest_start_time, end_date=backtest_end_time)
        benchmark_data.index = pd.to_datetime(benchmark_data.index)
        print("\n\n指数数据：\n {} \n\n".format(benchmark_data))

        # 获取个股数据
        # pdb.set_trace()
        combined_df = loader.load_stock_price_timerange(index_code, constituent_stock_codes, backtest_start_time, backtest_end_time, use_cache=use_cache)
        all_instruments = pd.unique(combined_df.index.get_level_values('instrument'))

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
        combined_df = pd.concat([combined_df, benchmark_expanded], axis=1)
        
        print(f"已将基准数据合并到combined_df中，新增列: {list(benchmark_data_renamed.columns)}")
        print(f"combined_df现在的列: {list(combined_df.columns)}")


        # 获取股票行业市值等信息
        stock_info = loader.get_stocks_info(index_code=index_code, codes=all_instruments, use_cache=use_cache)
        print(f"成功加载 {len(stock_info)} 只股票的基本信息")

        # 将行业信息添加到combined_df中
        combined_df['industry'] = combined_df.index.get_level_values('instrument').map(stock_info['行业'])
        print(f"已将行业信息添加到combined_df, 共有 {combined_df['industry'].nunique()} 个行业")
        print("\n\n个股数据：\n {} \n\n".format(combined_df))
        # pdb.set_trace()
        ########################
        ###  成分股掩码计算  ###
        ########################
        # 1. 使用combined_df的索引创建mask
        constituent_mask = pd.DataFrame(False, index=combined_df.index, columns=['is_constituent'], dtype=np.bool)
        
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

        constituent_mask = constituent_mask.fillna(False).astype(np.bool)

        ###############################
        ###  使用FactorStrategy类  ###
        ###############################
        
        # ml_model = XGBoostModel(
        #     model_params={
        #     'objective': 'reg:squarederror',  # 目标函数：使用均方误差(MSE)作为回归问题的损失函数
        #     'eval_metric': 'rmse',            # 评估指标：使用均方根误差(RMSE)来评估模型性能
        #     'booster': 'gbtree',              # 基学习器类型：使用决策树作为基学习器
        #     'max_depth': 5,                   # 决策树最大深度：控制树的复杂度
        #     'learning_rate': 0.1,             # 学习率：控制每棵树的权重缩减
        #     'subsample': 0.8,                 # 样本采样比例：训练每棵树时随机使用80%的训练数据
        #     'colsample_bytree': 0.5,          # 特征采样比例：训练每棵树时随机使用50%的特征
        #     'min_child_weight': 1,            # 叶子节点最小样本权重：控制叶子节点的生成条件
        #     'verbosity': 0,                   # 输出信息详细程度：0表示不输出训练过程信息
        #     'random_state': 10,                # 随机种子：确保结果可复现
        #     'n_estimators': 200,              # 树的数量：默认训练100棵树
        # },
        #     industry_neutralization=kwargs.get('pred_score_industry_neutralization', None),
        #     cross_sectional_norm=True
        # )
        ml_model = NoModel(
            industry_neutralization=kwargs.get('pred_score_industry_neutralization', None),
            cross_sectional_norm=True
        )
        
        # ml_model = LightGBMModel(
        #     model_params={'learning_rate': 0.05},
        #     industry_neutralization='zscore',
        #     cross_sectional_norm=True
        # )

        # 初始化策略
        strategy = FactorStrategy(
            factor_exprs=exprs or {},
            base_features={
                # "intraday_return": "($close-$open)/$open", 
                # "return_1d": "$close/DELAY($close, 1)-1", 
                # "relative_volume": "$volume/TS_MEAN($volume, 20)-1", 
                # "amplitude": "($high-$low)/DELAY($close, 1)",
            },
            ml_model=ml_model,
            cache_dir='./pkl_files',
            label_forward_days=kwargs.get('label_forward_days', 4),
        )

        # 准备训练数据
        train_df = combined_df.loc[train_start_time:train_end_time].mask(~constituent_mask['is_constituent'].loc[train_start_time:train_end_time])  
        val_df = combined_df.loc[val_start_time:val_end_time].mask(~constituent_mask['is_constituent'].loc[val_start_time:val_end_time])
        test_df = combined_df.loc[test_start_time:test_end_time].mask(~constituent_mask['is_constituent'].loc[test_start_time:test_end_time])
        # pdb.set_trace()
        
        # 训练模型
        print("="*60)
        print("开始模型训练...")
        print("="*60)
        training_results = strategy.train(train_df, val_df)

       
        
        # 打印特征重要性
        if 'feature_importance' in training_results:
            print("\nTop 10 Important Features:")
            print(training_results['feature_importance'].head(10))

        # 模型推理
        print("="*60)
        print("开始模型推理...")
        print("="*60)
        # 应用成分股掩码后，再进行推理
        pred_df, inference_results = strategy.inference(test_df)
        
        # 打印结果表格
        if 'train_mse' in training_results:
            print("\n" + "="*80)
            print("结果汇总")
            print("="*80)
            
            # 手动格式化转置表格以确保对齐
            print(f"{'数据集':<8} {'MSE':<12} {'IC':<10} {'ICIR':<10} {'RankIC':<10} {'RankICIR':<10}")
            print("-" * 65)
            print(f"{'训练集':<8} {training_results['train_mse']:<12.6f} {training_results['train_ic']:<10.4f} {training_results.get('train_icir', np.nan):<10.4f} {training_results['train_rankic']:<10.4f} {training_results.get('train_rankicir', np.nan):<10.4f}")
            print(f"{'验证集':<8} {training_results['val_mse']:<12.6f} {training_results['val_ic']:<10.4f} {training_results.get('val_icir', np.nan):<10.4f} {training_results['val_rankic']:<10.4f} {training_results.get('val_rankicir', np.nan):<10.4f}")
            print(f"{'测试集':<8} {inference_results['mse']:<12.6f} {inference_results['ic']:<10.4f} {inference_results.get('icir', np.nan):<10.4f} {inference_results['rankic']:<10.4f} {inference_results.get('rankicir', np.nan):<10.4f}")
            print("="*80)


        
        # 生成Alpha表用于回测
        alpha_table = pred_df['pred'].mask(~constituent_mask['is_constituent'].loc[test_start_time:test_end_time]).unstack()
        
        # 对齐index与columns
        alpha_table = alpha_table.reindex(columns=all_instruments)
        
        # 取时间交集，确保alpha_table和benchmark_data的时间对齐
        common_index = alpha_table.index.intersection(benchmark_data.loc[test_start_time:test_end_time].index)
        alpha_table = alpha_table.loc[common_index]
        benchmark_data = benchmark_data.loc[common_index]

        ####################
        ##### 回测部分  #####
        ####################
        # 获取测试区间的未复权数据用于交易，默认是开盘价
        # pdb.set_trace()
        deal_price_data = combined_df['close'].unstack().loc[common_index, alpha_table.columns] # pd.DataFrame({code: combined_df.xs(code, level=1)['close'] for code in all_instruments}).set_index(benchmark_data.index).loc[common_index, alpha_table.columns]
        # 获取测试区间的后复权价格数据，用于计算收益
        postadj_close = combined_df['close_backadj'].unstack().loc[common_index, alpha_table.columns] # pd.DataFrame({code: combined_df.xs(code, level=1)['close_backadj'] for code in all_instruments}).set_index(benchmark_data.index).loc[test_start_time:test_end_time, alpha_table.columns]
        # 获取测试区间的基准指数数据
        benchmark_data = benchmark_data.loc[test_start_time:test_end_time]
        # 对价格实施掩码，以在回测时，不交易非成分股
        deal_price_data = deal_price_data.mask(~constituent_mask['is_constituent'].loc[test_start_time:test_end_time].unstack())
        postadj_close = postadj_close.mask(~constituent_mask['is_constituent'].loc[test_start_time:test_end_time].unstack())
        # 初始化回测组件
        action_manager = ActionManager(**kwargs)
        portfolio_manager = AlphaGPTPortfolioManager(update_freq=kwargs.get('update_freq', 'M'), max_pos_each_stock=kwargs.get('max_pos_each_stock', 0.1))
        performance_evaluator = PerformanceEvaluator()
        # 核心回测函数
        results = performance_evaluator.backtest_factor_table(alpha_table, deal_price_data, postadj_close, portfolio_manager, action_manager, layer_start=kwargs.get('layer_start', 0), layer_end=kwargs.get('layer_end', 1))

        results.update({
            'expr': kwargs.get('expr', ''),
            'BENCHMARKINDEX': benchmark_data['close'],
            'PRICE': postadj_close,
            'start_cash': action_manager.start_cash,
        })

        # 计算评估指标
        results_to_save = performance_evaluator.get_eval_metrics(results)

        # action参数也保存，以供复现
        results_to_save.update({k: v for k, v in action_manager.__dict__.items() if not isinstance(v, pd.Series)})
        
        # 添加训练结果到最终结果中
        results_to_save['metrics'].update({
            'IC': inference_results['ic'],
            'ICIR': inference_results['icir'],
            'RankIC': inference_results['rankic'],
            'RankICIR': inference_results['rankicir'],
        })
        return results_to_save

        
        
        # # 中间结果导出到zip
        # path_alphatable = './outputs'
        # zip_dir = '因子明细'
        # os.makedirs(os.path.join(path_alphatable, zip_dir), exist_ok=True)
        # path_alphatable_csv = os.path.join(path_alphatable,zip_dir ,'因子表.csv')
        # path_trade_signals_csv = os.path.join(path_alphatable,zip_dir, '交易信号.csv')
        # path_position_csv = os.path.join(path_alphatable,zip_dir, '持仓明细.csv')
        # # path_industry_exposure_csv = os.path.join(path_alphatable, zip_dir, '行业暴露分析.csv')
        
        # # 保存Alpha表
        # alpha_table.to_csv(path_alphatable_csv)
        # results['trade_signals'].to_csv(path_trade_signals_csv)
        # results['total_portfolios'].to_csv(path_position_csv)
        
        # csv_paths = [path_alphatable_csv, path_trade_signals_csv, path_position_csv]
        # csv_zipfile_path = os.path.join(path_alphatable, '因子明细.zip')
        # # zip_files(csv_paths, csv_zipfile_path)
        
        # results_to_save.update({"csv_zipfile_path": csv_zipfile_path})


        # filename = 'results_' + datetime.datetime.today().strftime('%m-%d_%H-%M-%S')
        # draw_figures(results_to_save, filename)
        # return results_to_save
    finally:
        pass

if __name__ == '__main__':
    # parser = argparse.ArgumentParser(description="Trading strategy backtester")
    # parser.add_argument('--expr', 
    #                     default="TS_STD($return, 20)",
    #                     type=str)
    # args = parser.parse_args()
    
    results_to_save = backtest(
        exprs={
            # "Smart_Volume_Cluster_Composite": "(TS_STD($close,5)/(TS_STD($close,20)+1e-8)) * ($volume > TS_QUANTILE($volume,20,0.9))",
            # "RangeVolume_SlopeProduct_5D": "COUNT((($high - $low) < TS_MEAN(($high - $low),5)) && ($volume < TS_MEAN($volume,5)),5)",
            # "Dynamic_Volatility_Bands_Momentum_Stochastic_Oscillator_Factor": "(($close - TS_MIN($low, 14)) / (TS_MAX($high, 14) - TS_MIN($low, 14) + 1e-8)) * 100",
            # "Moving_Average_Window_Optimization_Factor": "($close > DELAY($close, 1)) ? (EMA($close, 2) + EMA($close, 5)) : (EMA($close, 10) - EMA($close, 15))",
            # "Adjusted_Normalization_Factor_10D": "RANK(SQRT(TS_VAR(DELAY($close, 5), 10))) * ZSCORE(DELTA($close, 7))",
            # "EMA_Volume_Rank_STD_Factor": "ZSCORE( EMA($close, 3) * RANK(TS_STD($close, 15)) + EMA($high - $low, 3) * RANK(TS_STD($high - $low, 15)) + EMA($volume, 3) * RANK(TS_STD($volume, 15)) )",
            # "bench_corr": "ZSCORE(0.5 * ((TS_STD($close, 10) > TS_STD($close, 30)) ? EMA(TS_STD($close, 10), 3) : EMA(TS_STD($close, 30), 7)) + 0.3 * ((TS_STD($high - $low, 10) > TS_STD($high - $low, 30)) ? EMA(TS_STD($high - $low, 10), 3) : EMA(TS_STD($high - $low, 30), 7)) + 0.2 * EMA(TS_STD($volume, 10), 3))",
            
            "Volume_Rank_STD_Factor": "ZSCORE((($volume > TS_MEDIAN($volume, 10)) ? EMA(TS_STD($return, 10), 3) : EMA(TS_STD($return, 10), 7)))"
            },
        date_split={
            "train_start_time": "2015-01-01",
            "train_end_time": "2021-12-31",
            "val_start_time": "2022-01-01",
            "val_end_time": "2022-12-31",
            "test_start_time": "2023-01-01",
            "test_end_time": "2024-12-30"
            # 'test_end_time': '2025-06-06'
            },
        use_cache=True,
        stop_loss_rate=0.5,
        stop_profit_rate=0.4,
        start_cash=1e8,
        position_size=1.0,
        update_freq=7,
        label_forward_days=7,
        max_pos_each_stock=0.2,
        stock_pool="中证500",
        layer_start=0,
        layer_end=1,
        pred_score_industry_neutralization=True,
        )
    
    # pdb.set_trace()

    filename = 'results_' + datetime.datetime.today().strftime('%m-%d_%H-%M-%S')
    draw_figures_v2(results_to_save, filename)
    # text = {k: str(v) for k, v in results_to_save.items() if isinstance(v, float)}
    # print("="*60)
    # print("最终回测结果:")
    # print("="*60)
    # for k, v in text.items():
    #     print(f"{k}: {v}")
    # print("="*60)
    
