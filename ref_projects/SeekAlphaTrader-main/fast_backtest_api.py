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

from data_manager.dataloader import BaoStockLoader, TushareLoader
from portfolio_manager.portfolio_management import AlphaGPTPortfolioManager
from evaluator.performance_evaluation import PerformanceEvaluator
from test.visualization import draw_figures, draw_figures_v2
from portfolio_manager.action_management import ActionManager
from data_manager.zip_files import zip_files
from expression_manager.expr_parser import parse_expression
from expression_manager.function_lib import *
from strategy import FactorStrategy  # 导入FactorStrategy类
from tqdm import tqdm
from ml_models import LightGBMModel, XGBoostModel, NoModel
import pdb
import gc



###########################
######  获取固定数据  ######
###########################

# backtest_start_time = pd.to_datetime("2024-01-01")
# backtest_end_time = pd.to_datetime("2025-01-01")

data_start_time = pd.to_datetime("2021-01-01")
data_end_time = pd.to_datetime("2025-06-01")
index_code = '中证500'

# 缓存路径
cached_combine_df_path = './.cache/cached_{}_combine_df_{}_{}.pkl'.format(index_code, data_start_time.strftime('%Y-%m-%d'), data_end_time.strftime('%Y-%m-%d'))
cached_constituent_mask_path = './.cache/cached_{}_constituent_mask_{}_{}.pkl'.format(index_code, data_start_time.strftime('%Y-%m-%d'), data_end_time.strftime('%Y-%m-%d'))
cached_benchmark_data_path = './.cache/cached_{}_benchmark_data_{}_{}.pkl'.format(index_code, data_start_time.strftime('%Y-%m-%d'), data_end_time.strftime('%Y-%m-%d'))

if os.path.exists(cached_combine_df_path) and os.path.exists(cached_constituent_mask_path) and os.path.exists(cached_benchmark_data_path):
    combined_df = pd.read_pickle(cached_combine_df_path)
    print(f"已加载缓存数据，路径: {cached_combine_df_path}")
    print(f"combined_df的数据: \n {combined_df}")
    print(f"combined_df的内存占用: {combined_df.memory_usage().sum()}")
    print(f"combined_df的列: {list(combined_df.columns)}")

    constituent_mask = pd.read_pickle(cached_constituent_mask_path)
    print(f"已加载缓存数据，路径: {cached_constituent_mask_path}")
    print(f"constituent_mask的数据: \n {constituent_mask}")
    print(f"constituent_mask的列: {list(constituent_mask.columns)}")
    print(f"constituent_mask的内存占用: {constituent_mask.memory_usage().sum()}")

    benchmark_data = pd.read_pickle(cached_benchmark_data_path)
    print(f"已加载缓存数据，路径: {cached_benchmark_data_path}")
    print(f"benchmark_data的数据: \n {benchmark_data}")
    print(f"benchmark_data的列: {list(benchmark_data.columns)}")
    print(f"benchmark_data的内存占用: {benchmark_data.memory_usage().sum()}")

    all_instruments = pd.unique(combined_df.index.get_level_values('instrument'))

else:
    raise ValueError("缓存数据不存在，请先获取数据")


def backtest(exprs:Dict[str, str], backtest_start_time:str, backtest_end_time:str, **kwargs) -> dict:
    '''
    回测函数，输入参数为策略参数，输出为回测结果
    '''
    global combined_df, constituent_mask, benchmark_data, all_instruments

    combined_df_copy = combined_df.copy()
    constituent_mask_copy = constituent_mask.copy()
    benchmark_data_copy = benchmark_data.copy()
    all_instruments_copy = all_instruments.copy()

    try:
        backtest_start_time = pd.to_datetime(backtest_start_time)
        backtest_end_time = pd.to_datetime(backtest_end_time)
    except:
        raise ValueError("backtest_start_time和backtest_end_time格式错误，请输入YYYY-MM-DD格式")

    # 加载策略参数，根据用户选择的股票池获取对应股票指数的数据集ID
    action_manager = ActionManager(**kwargs)

    try:
        ###############################
        ###  使用FactorStrategy类  ###
        ###############################
        ml_model = NoModel(
            industry_neutralization=kwargs.get('pred_score_industry_neutralization', None),
            cross_sectional_norm=False
        )

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
        # train_df = combined_df_copy.loc[train_start_time:train_end_time].mask(~constituent_mask_copy['is_constituent'].loc[train_start_time:train_end_time])  
        # val_df = combined_df_copy.loc[val_start_time:val_end_time].mask(~constituent_mask_copy['is_constituent'].loc[val_start_time:val_end_time])
        test_df = combined_df_copy.loc[backtest_start_time-pd.Timedelta(days=400):backtest_end_time].mask(~constituent_mask_copy['is_constituent'].loc[backtest_start_time-pd.Timedelta(days=400):backtest_end_time])
        # 测试集多加100天用于冷启动

        # # 训练模型
        # print("="*60)
        # print("开始模型训练...")
        # print("="*60)
        # training_results = strategy.train(train_df, val_df)
        # del train_df, val_df
        # gc.collect()

       
        
        # # 打印特征重要性
        # if 'feature_importance' in training_results:
        #     print("\nTop 10 Important Features:")
        #     print(training_results['feature_importance'].head(10))

        # 模型推理
        print("="*60)
        print("开始模型推理...")
        print("="*60)
        # 应用成分股掩码后，再进行推理
        pred_df, inference_results = strategy.inference(test_df)
        pred_df = pred_df.loc[backtest_start_time:backtest_end_time]

        
        # # 打印结果表格
        # if 'train_mse' in training_results:
        #     print("\n" + "="*80)
        #     print("结果汇总")
        #     print("="*80)
            
        #     # 手动格式化转置表格以确保对齐
        #     print(f"{'数据集':<8} {'MSE':<12} {'IC':<10} {'ICIR':<10} {'RankIC':<10} {'RankICIR':<10}")
        #     print("-" * 65)
        #     print(f"{'训练集':<8} {training_results['train_mse']:<12.6f} {training_results['train_ic']:<10.4f} {training_results.get('train_icir', np.nan):<10.4f} {training_results['train_rankic']:<10.4f} {training_results.get('train_rankicir', np.nan):<10.4f}")
        #     print(f"{'验证集':<8} {training_results['val_mse']:<12.6f} {training_results['val_ic']:<10.4f} {training_results.get('val_icir', np.nan):<10.4f} {training_results['val_rankic']:<10.4f} {training_results.get('val_rankicir', np.nan):<10.4f}")
        #     print(f"{'测试集':<8} {inference_results['mse']:<12.6f} {inference_results['ic']:<10.4f} {inference_results.get('icir', np.nan):<10.4f} {inference_results['rankic']:<10.4f} {inference_results.get('rankicir', np.nan):<10.4f}")
        #     print("="*80)


        
        # 生成Alpha表用于回测
        alpha_table = pred_df['pred'].mask(~constituent_mask_copy['is_constituent'].loc[backtest_start_time:backtest_end_time]).unstack()
        
        # 对齐index与columns
        alpha_table = alpha_table.reindex(columns=all_instruments_copy)
        
        # 取时间交集，确保alpha_table和benchmark_data的时间对齐
        common_index = alpha_table.index.intersection(benchmark_data_copy.loc[backtest_start_time:backtest_end_time].index)
        alpha_table = alpha_table.loc[common_index]
        benchmark_data_copy = benchmark_data_copy.loc[common_index]
        benchmark_data_copy = benchmark_data_copy.loc[backtest_start_time:backtest_end_time]
        bench_close = benchmark_data_copy['close'].copy()

        ####################
        ##### 回测部分  #####
        ####################
        # 获取测试区间的未复权数据用于交易，默认是开盘价
        deal_price_data = combined_df_copy['close'].unstack().loc[common_index, alpha_table.columns] 
        # 获取测试区间的后复权价格数据，用于计算收益
        postadj_close = combined_df_copy['adj_close'].unstack().loc[common_index, alpha_table.columns] 
        # 获取测试区间的基准指数数据
        
        # 对价格实施掩码，以在回测时，不交易非成分股
        deal_price_data = deal_price_data.mask(~constituent_mask_copy['is_constituent'].loc[backtest_start_time:backtest_end_time].unstack())
        postadj_close = postadj_close.mask(~constituent_mask_copy['is_constituent'].loc[backtest_start_time:backtest_end_time].unstack())
        # 初始化回测组件
        action_manager = ActionManager(**kwargs)
        portfolio_manager = AlphaGPTPortfolioManager(update_freq=kwargs.get('update_freq', 'M'), max_pos_each_stock=kwargs.get('max_pos_each_stock', 0.1))
        performance_evaluator = PerformanceEvaluator()
        # 核心回测函数
        results = performance_evaluator.backtest_factor_table(alpha_table, deal_price_data, postadj_close, combined_df_copy, portfolio_manager, action_manager, layer_start=kwargs.get('layer_start', 0), layer_end=kwargs.get('layer_end', 1), top_k=kwargs.get('top_k', None), verbose=False)

        results.update({
            'expr': kwargs.get('expr', ''),
            'BENCHMARKINDEX': bench_close,
            'PRICE': postadj_close,
            'start_cash': action_manager.start_cash,
        })

        # 计算评估指标
        results_to_save = performance_evaluator.get_eval_metrics(results)

        # action参数也保存，以供复现
        results_to_save.update({k: v for k, v in action_manager.__dict__.items() if not isinstance(v, pd.Series)})
        
        # 添加训练结果到最终结果中
        # results_to_save['metrics'].update({
        #     'IC': inference_results['ic'],
        #     'ICIR': inference_results['icir'],
        #     'RankIC': inference_results['rankic'],
        #     'RankICIR': inference_results['rankicir'],
        # })
        print(results_to_save['metrics'])
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
            "示例因子": "((TS_PCTCHANGE($close,30) > 0.05) & (TS_STD($return,30) > 0.03)) ? RANK(TS_STD($return,30)) : nan"
            },
        use_cache=False,
        stop_loss_rate=0.1,
        stop_profit_rate=0.4,
        start_cash=1e6,
        position_size=1.0,
        update_freq=5,
        label_forward_days=5,
        max_pos_each_stock=0.1,
        layer_start=0,
        layer_end=1,
        # top_k=5, # 优先使用top_k，若为None，则使用layer_start和layer_end
        pred_score_industry_neutralization=False,
        )
    
    # pdb.set_trace()

    # filename = 'results_' + datetime.datetime.today().strftime('%m-%d_%H-%M-%S')
    # draw_figures_v2(results_to_save, filename)
    # text = {k: str(v) for k, v in results_to_save.items() if isinstance(v, float)}
    # print("="*60)
    # print("最终回测结果:")
    # print("="*60)
    # for k, v in text.items():
    #     print(f"{k}: {v}")
    # print("="*60)
    
