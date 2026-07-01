'''
Main file for backtesting a strategy on historical stock data.
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
from sklearn.metrics import mean_squared_error
from sklearn.preprocessing import Normalizer

from data_manager.dataloader import BaoStockLoader, QMTDataLoader
from portfolio_manager.portfolio_management import AlphaGPTPortfolioManager
from evaluator.performance_evaluation import PerformanceEvaluator
from test.visualization import draw_figures
from portfolio_manager.action_management import ActionManager
from data_manager.zip_files import zip_files
from expr_parser import parse_expression
from function_lib import *
from tqdm import tqdm
import pdb

def calculate_ic(y_true, y_pred):
    """
    计算IC、ICIR和RankIC
    
    参数:
        y_true: 真实值序列
        y_pred: 预测值序列
    
    返回:
        tuple: (IC, ICIR, RankIC)
    """
    # 计算普通IC
    ic = np.corrcoef(y_true, y_pred)[0,1]
    
    # 计算RankIC (使用秩相关系数)
    rank_ic = np.corrcoef(pd.Series(y_true).rank(), pd.Series(y_pred).rank())[0,1]
    
    # # 计算ICIR (假设使用过去20个周期的IC计算)
    # window = min(20, len(y_true))
    # if window > 1:
    #     rolling_ic = pd.Series(y_true).rolling(window).corr(pd.Series(y_pred))
    #     icir = np.mean(rolling_ic.dropna()) / np.std(rolling_ic.dropna())
    # else:
    #     icir = np.nan
        
    return ic, rank_ic

def analyze_industry_exposure(feature_df, stock_info, feature_cols):
    """
    分析行业因子暴露
    
    参数:
        feature_df: 因子数据DataFrame，MultiIndex (date, instrument)
        stock_info: 股票基本信息DataFrame，包含行业信息
        feature_cols: 因子列名列表
    
    返回:
        dict: 包含行业暴露分析结果
    """
    print("开始分析行业因子暴露...")
    
    # 确保stock_info的index与feature_df的instrument level对齐
    stock_info_aligned = stock_info.reindex(feature_df.index.get_level_values('instrument').unique())
    
    # 为每个时间点计算行业暴露
    exposure_results = {}
    
    # 获取所有日期
    dates = feature_df.index.get_level_values(0).unique()
    industries = stock_info_aligned['行业'].dropna().unique()
    
    print(f"共有 {len(industries)} 个行业: {list(industries)}")
    
    # 为每个因子计算行业暴露度
    for factor in feature_cols:
        factor_exposures = []
        
        for date in dates:
            try:
                # 获取当日数据
                daily_data = feature_df.loc[date]
                
                # 合并行业信息
                daily_merged = daily_data.merge(
                    stock_info_aligned[['行业']], 
                    left_index=True, 
                    right_index=True, 
                    how='left'
                )
                
                # 计算各行业在该因子上的平均值（行业暴露度）
                industry_exposure = daily_merged.groupby('行业')[factor].mean()
                industry_exposure.name = date
                factor_exposures.append(industry_exposure)
                
            except Exception as e:
                print(f"处理日期 {date} 时出错: {e}")
                continue
        
        if factor_exposures:
            # 合并所有日期的行业暴露度
            exposure_df = pd.concat(factor_exposures, axis=1).T
            exposure_results[factor] = exposure_df
    
    return exposure_results

def industry_neutralize(feature_df, stock_info, feature_cols, method='zscore'):
    """
    行业归一化处理
    
    参数:
        feature_df: 因子数据DataFrame
        stock_info: 股票基本信息DataFrame
        feature_cols: 需要归一化的因子列名
        method: 归一化方法 ('zscore', 'rank', 'quantile')
    
    返回:
        DataFrame: 行业归一化后的因子数据
    """
    print(f"开始行业归一化处理，方法: {method}")
    # 复制原始数据
    neutralized_df = feature_df.copy()
    
    # 确保stock_info的index与feature_df的instrument level对齐
    stock_info_aligned = stock_info.reindex(feature_df.index.get_level_values('instrument').unique())
    
    # 为feature_df添加行业信息
    feature_with_industry = feature_df.copy()
    
    # 使用向量化操作提高效率
    instruments = feature_df.index.get_level_values('instrument')
    industry_map = stock_info_aligned['行业'].to_dict()
    
    # 创建行业映射Series
    industry_series = pd.Series([industry_map.get(inst, '未知') for inst in instruments], 
                               index=feature_df.index, name='industry')
    
    if method == 'zscore':
        # 行业内Z-score标准化
        def industry_zscore(group):
            return group - group.mean()
        
        pbar = tqdm(enumerate(feature_cols), total=len(feature_cols), desc="正在进行行业标准化")
        for i, factor in pbar:
            pbar.set_postfix(当前因子=factor)
            # 按日期和行业分组进行标准化
            neutralized_df[factor] = (feature_df.groupby([feature_df.index.get_level_values(0), industry_series])
                                    [factor].transform(industry_zscore))
    
    elif method == 'rank':
        # 行业内排名标准化
        def industry_rank(group):
            return group.rank(pct=True) - 0.5  # 转换为[-0.5, 0.5]区间
        
        for factor in feature_cols:
            neutralized_df[factor] = (feature_df.groupby([feature_df.index.get_level_values(0), industry_series])
                                    [factor].transform(industry_rank))
    
    elif method == 'quantile':
        # 行业内分位数标准化
        def industry_quantile(group):
            return group.rank(pct=True)
        
        for factor in feature_cols:
            neutralized_df[factor] = (feature_df.groupby([feature_df.index.get_level_values(0), industry_series])
                                    [factor].transform(industry_quantile))
    
    print("行业归一化处理完成")
    return neutralized_df

def calculate_industry_ic(feature_df, stock_info, feature_cols):
    """
    计算行业内IC
    
    参数:
        feature_df: 包含因子和标签的DataFrame
        stock_info: 股票基本信息
        feature_cols: 因子列名
    
    返回:
        dict: 各行业的IC统计
    """
    print("开始计算行业内IC...")
    
    # 添加行业信息 - 参考industry_neutralize的处理方式
    stock_info_aligned = stock_info.reindex(feature_df.index.get_level_values('instrument').unique())
    instruments = feature_df.index.get_level_values('instrument')
    industry_map = stock_info_aligned['行业'].to_dict()
    industry_series = pd.Series([industry_map.get(inst, '未知') for inst in instruments], 
                               index=feature_df.index, name='industry')
    
    industry_ic_results = {}
    
    # 获取所有日期
    dates = feature_df.index.get_level_values(0).unique()
    industries = stock_info_aligned['行业'].dropna().unique()
    
    print(f"共有 {len(dates)} 个时间点, {len(industries)} 个行业")
    
    for factor in feature_cols:
        print(f"正在计算因子 {factor} 的行业内IC...")
        
        # 存储每个行业每个时间点的IC值
        industry_ic_series = {}
        
        for industry in industries:
            ic_values = []
            
            # 按时间点计算该行业的IC
            for date in dates:
                try:
                    # 获取当日该行业的数据
                    date_mask = feature_df.index.get_level_values(0) == date
                    industry_mask = industry_series == industry
                    combined_mask = date_mask & industry_mask
                    
                    if combined_mask.sum() < 5:  # 样本数太少跳过
                        continue
                    
                    # 获取当日该行业的因子值和标签值
                    factor_values = feature_df.loc[combined_mask, factor].values
                    label_values = feature_df.loc[combined_mask, 'label'].values
                    
                    # 过滤掉NaN值
                    valid_mask = ~(np.isnan(factor_values) | np.isnan(label_values))
                    if valid_mask.sum() < 5:  # 有效样本数太少跳过
                        continue
                    
                    factor_clean = factor_values[valid_mask]
                    label_clean = label_values[valid_mask]
                    
                    # 计算IC
                    if len(factor_clean) >= 5 and np.std(factor_clean) > 1e-8 and np.std(label_clean) > 1e-8:
                        ic, rank_ic = calculate_ic(label_clean, factor_clean)
                        if not np.isnan(ic):
                            ic_values.append(ic)
                    
                except Exception as e:
                    continue
            
            # 如果该行业有足够的IC值，计算统计指标
            if len(ic_values) >= 5:
                industry_ic_series[industry] = {
                    'IC_mean': np.mean(ic_values),
                    'IC_std': np.std(ic_values),
                    'IC_values': ic_values,
                    'IC_count': len(ic_values),
                    'ICIR': np.mean(ic_values) / (np.std(ic_values) + 1e-8)
                }
        
        industry_ic_results[factor] = industry_ic_series
    
    return industry_ic_results

def backtest(exprs:Dict[str, str]=None, date_split:Dict[str, str]=None, **kwargs) -> dict:
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
        index_code = 'sh.000905'
        # index_code = 'sh.000015'
        

        # loader = BaoStockLoader(
        #     data_dir='./data_baostock', 
        # )

        loader = QMTDataLoader(
            data_dir='./data_qmt',
            simulate_client=True,
        )

        # 获取指数成分股
        constituent_stock_codes = loader.load_index_stocklist_timerange(index_code, backtest_start_time, backtest_end_time)


        # 获取指数数据
        benchmark_data = loader.load_stock_data(code=index_code, start_date=backtest_start_time, end_date=backtest_end_time)
        benchmark_data.index = pd.to_datetime(benchmark_data.index)

        

        ########################
        ###  获取个股行情数据  ###
        ########################
        combined_df = loader.load_stock_price_timerange(index_code, constituent_stock_codes, backtest_start_time, backtest_end_time, use_cache=True)
        # pdb.set_trace()
        all_instruments = pd.unique(combined_df.index.get_level_values('instrument'))


        # 获取股票行业市值等信息
        stock_info = loader.get_stocks_info(index_code=index_code, codes=all_instruments, use_cache=True)
        print(f"成功加载 {len(stock_info)} 只股票的基本信息")
        # print(f"行业分布: {stock_info['行业'].value_counts().head(10)}")

        # 将行业信息添加到combined_df中
        combined_df['行业'] = combined_df.index.get_level_values('instrument').map(stock_info['行业'])
        print(f"已将行业信息添加到combined_df, 共有 {combined_df['行业'].nunique()} 个行业")

        ########################
        ###  成分股掩码计算  ###
        ########################
        # 1. 使用combined_df的索引创建mask
        constituent_mask = pd.DataFrame(False, index=combined_df.index, columns=['is_constituent'])
        
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


        #####################
        ###  因子计算部分  ###
        #####################
        # 计算其他字段
        combined_df.loc[:, 'return'] = combined_df.loc[:, 'close'].groupby('instrument').shift(0) / combined_df.loc[:, 'close'].groupby('instrument').shift(1) - 1
        
        # 计算因子
        for i, (name, expr) in enumerate(exprs.items()):
            expr = parse_expression(expr)
            for col in combined_df.columns:
                expr = expr.replace('$'+col, f"combined_df[\'{col}\']")

            pkl_path = f'./pkl_files/{name}_{index_code}_{train_start_time.strftime("%Y-%m-%d")}_{test_end_time.strftime("%Y-%m-%d")}.pkl'
            if os.path.exists(pkl_path):
                combined_df[name] = pd.read_pickle(pkl_path)
            else:
                combined_df[name] = eval(expr)
                os.makedirs(os.path.dirname(pkl_path), exist_ok=True)
                combined_df[name].to_pickle(pkl_path)

        # 计算基础feature
        base_feature = {
            "intraday_return": "($close-$open)/$open-1", 
            "return_1d": "$close/DELAY($close, 1)-1", 
            "relative_volume": "$volume/TS_MEAN($volume, 20)-1", 
            "amplitude": "($high-$low)/DELAY($close, 1)",
            # "return_3d": "$close/DELAY($close, 3)-1", 
        }

        for feature, expr in base_feature.items():
            expr = parse_expression(expr)
            for col in combined_df.columns:
                expr = expr.replace('$'+col, f"combined_df[\'{col}\']")
            
            pkl_path = f'./data_qmt/pickle/{feature}_{index_code}_{train_start_time.strftime("%Y-%m-%d")}_{test_end_time.strftime("%Y-%m-%d")}.pkl'
            if os.path.exists(pkl_path):
                combined_df[feature] = pd.read_pickle(pkl_path)
            else:
                combined_df[feature] = eval(expr)
                os.makedirs(os.path.dirname(pkl_path), exist_ok=True)
                combined_df[feature].to_pickle(pkl_path)

        #######################
        ###  ML模型训练推理部分  ###
        #######################
        # 构建训练feature
        feature_cols = list(exprs.keys()) + list(base_feature.keys())
        feature_df = combined_df[feature_cols]
        feature_df = feature_df.fillna(0)

        # 构建label: 5天后的收益
        feature_df.loc[:, 'label'] = combined_df.loc[:, 'close'].groupby('instrument').shift(-4) / combined_df.loc[:, 'close'].groupby('instrument').shift(0) - 1
        
        # 对特征进行横截面标准化
        def cross_sectional_zscore(df, cols):
            # 按日期分组，对每个时间点进行标准化
            return df.groupby(level=0)[cols].transform(lambda x: (x - x.mean()) / x.std())
        
        # 对特征进行横截面标准化
        feature_df.loc[:, feature_cols] = cross_sectional_zscore(feature_df, feature_cols)
        feature_df.loc[:, 'label'] = cross_sectional_zscore(feature_df, ['label'])


        # 计算相关性矩阵
        corr_matrix = feature_df.corr()
        print("\n相关性矩阵: ")
        print(corr_matrix)

        # 划分训练集和测试集
        train_df = feature_df.loc[train_start_time:train_end_time]
        val_df = feature_df.loc[val_start_time:val_end_time]
        test_df = feature_df.loc[test_start_time:test_end_time]

        # 准备训练数据
        feature_cols = [col for col in train_df.columns if col != 'label']
        
        # 不再需要全局标准化，因为已经进行了横截面标准化
        train_x = train_df[feature_cols]
        train_y = train_df['label']
        
        val_x = val_df[feature_cols]
        val_y = val_df['label']
        
        test_x = test_df[feature_cols]
        test_y = test_df['label']

        # 使用fillna填充缺失值，保持维度一致
        train_x = train_x.fillna(0)  # 使用0填充特征缺失值
        train_y = train_y.fillna(0)  # 使用0填充标签缺失值
        
        val_x = val_x.fillna(0)
        val_y = val_y.fillna(0)
        
        test_x = test_x.fillna(0)
        test_y = test_y.fillna(0)
        
        # LightGBM参数配置
        lgb_params = {
            'objective': 'regression',        # 修正：之前的'loss'参数名不正确
            'metric': 'rmse',                 # 添加评估指标
            'boosting_type': 'gbdt',          # 添加提升类型
            'num_leaves': 15,                 # 修正：之前210太大，在max_depth=4时应该<=16
            'max_depth': 3,                   # 保持树的深度
            'learning_rate': 0.1,             # 学习率
            'feature_fraction': 0.8,          # 修正：LightGBM中应该用feature_fraction而不是colsample_bytree
            'bagging_fraction': 0.8,          # 修正：LightGBM中应该用bagging_fraction而不是subsample
            'bagging_freq': 5,                # 添加bagging频率
            'min_child_samples': 20,          # 叶子节点最小样本数
            'lambda_l1': 0.1,                 # 修正：降低L1正则化强度，之前205.6999太强
            'lambda_l2': 0.1,                 # 修正：降低L2正则化强度，之前580.9768太强
            'verbosity': -1,                  # 减少输出信息
            'random_state': 42,               # 添加随机种子确保可复现
            'force_col_wise': True,           # 添加：强制列式多线程，避免警告
            'num_threads': -1,                # 修正：使用所有可用线程
        }
        
        print("使用LightGBM模型进行训练...")
        
        # 创建LightGBM数据集
        train_data = lgb.Dataset(train_x, label=train_y)
        val_data = lgb.Dataset(val_x, label=val_y, reference=train_data)
        
        # 训练LightGBM模型
        model = lgb.train(
            lgb_params,
            train_data,
            num_boost_round=100,
            valid_sets=[train_data, val_data],
            valid_names=['train', 'val'],
            callbacks=[lgb.early_stopping(stopping_rounds=10), lgb.log_evaluation(period=0)]
        )
        
        # 模型推理
        train_pred = model.predict(train_x, num_iteration=model.best_iteration)
        val_pred = model.predict(val_x, num_iteration=model.best_iteration)
        test_pred = model.predict(test_x, num_iteration=model.best_iteration)
        
        # 特征重要性
        importance_dict = dict(zip(feature_cols, model.feature_importance(importance_type='gain')))

        # 计算各个集合的MSE
        train_mse = mean_squared_error(train_y, train_pred)
        val_mse = mean_squared_error(val_y, val_pred)
        test_mse = mean_squared_error(test_y, test_pred)
        
        print(f"Train MSE: {train_mse:.6f}")
        print(f"Validation MSE: {val_mse:.6f}")
        print(f"Test MSE: {test_mse:.6f}")

        # 格式化特征重要性
        feature_importance = pd.DataFrame({
            'feature': feature_cols,
            'importance': [importance_dict.get(f, 0) for f in feature_cols]
        })
        feature_importance = feature_importance.sort_values('importance', ascending=False)
        print("\nTop 10 Important Features:")
        print(feature_importance.head(10))

        # 计算IC
        train_ic, train_rankic = calculate_ic(train_y, train_pred)
        val_ic, val_rankic = calculate_ic(val_y, val_pred)
        test_ic, test_rankic = calculate_ic(test_y, test_pred)

        print(f"\nTrain IC: {train_ic:.4f}  Train RankIC: {train_rankic:.4f}")
        print(f"Validation IC: {val_ic:.4f}  Validation RankIC: {val_rankic:.4f}")
        print(f"Test IC: {test_ic:.4f}  Test RankIC: {test_rankic:.4f}")

        # 将预测结果存储为新的DataFrame
        pred_df = pd.DataFrame(index=feature_df.index, columns=['pred'])
        pred_df.loc[train_df.index, 'pred'] = train_pred
        pred_df.loc[val_df.index, 'pred'] = val_pred
        pred_df.loc[test_df.index, 'pred'] = test_pred

        # 生成的预测值用于回测（只使用测试集时间段的预测结果）
        alpha_table = pred_df.loc[test_start_time:test_end_time]
        # 行业中性化
        alpha_table = industry_neutralize(alpha_table, stock_info, ['pred'], method='zscore')['pred']
        # 掩码
        alpha_table = alpha_table.unstack().mask(~constituent_mask['is_constituent'].unstack().loc[test_start_time:test_end_time])
        # 对齐index与columns
        all_instruments = pred_df.index.get_level_values('instrument').unique()
        alpha_table = alpha_table.reindex(columns=all_instruments)
        alpha_table.index = benchmark_data.loc[test_start_time:test_end_time].index

        ####################
        ##### 回测部分  #####
        ####################
        # 获取测试区间的未复权数据用于交易，默认是开盘价
        deal_price_data = pd.DataFrame({code: combined_df.xs(code, level=1)['close'] for code in all_instruments}).set_index(benchmark_data.index).loc[test_start_time:test_end_time, alpha_table.columns]
        # 获取测试区间的后复权价格数据，用于计算收益
        postadj_close = pd.DataFrame({code: combined_df.xs(code, level=1)['close'] for code in all_instruments}).set_index(benchmark_data.index).loc[test_start_time:test_end_time, alpha_table.columns]
        # 获取测试区间的基准指数数据
        benchmark_data = benchmark_data.loc[test_start_time:test_end_time]
        # 对价格实施掩码，以在回测时，不交易非成分股
        deal_price_data = deal_price_data.mask(~constituent_mask['is_constituent'].unstack().loc[test_start_time:test_end_time])
        postadj_close = postadj_close.mask(~constituent_mask['is_constituent'].unstack().loc[test_start_time:test_end_time])
        # 初始化回测组件
        action_manager = ActionManager(**kwargs)
        portfolio_manager = AlphaGPTPortfolioManager(update_freq=kwargs.get('update_freq', 'M'), max_pos_each_stock=kwargs.get('max_pos_each_stock', 0.1))
        performance_evaluator = PerformanceEvaluator()
        # 核心回测函数
        results = performance_evaluator.backtest_factor_table(alpha_table, deal_price_data, postadj_close, portfolio_manager, action_manager, factor_layer=1)

        results.update({
            'expr': kwargs.get('expr', ''),
            'BENCHMARKINDEX': benchmark_data['close'],
            'PRICE': postadj_close,
            'start_cash': action_manager.start_cash,
        })

        # 计算评估指标
        results_to_save = performance_evaluator.calculate_evaluation_metrics(results)
        # action参数也保存，以供复现
        results_to_save.update({k: v for k, v in action_manager.__dict__.items() if not isinstance(v, pd.Series)})
        
        # 中间结果导出到zip
        path_alphatable = './outputs'
        zip_dir = '因子明细'
        os.makedirs(os.path.join(path_alphatable, zip_dir), exist_ok=True)
        path_alphatable_csv = os.path.join(path_alphatable,zip_dir ,'因子表.csv')
        path_trade_signals_csv = os.path.join(path_alphatable,zip_dir, '交易信号.csv')
        path_position_csv = os.path.join(path_alphatable,zip_dir, '持仓明细.csv')
        path_industry_exposure_csv = os.path.join(path_alphatable, zip_dir, '行业暴露分析.csv')
        
        results['trade_signals'].to_csv(path_trade_signals_csv)
        results['total_portfolios'].to_csv(path_position_csv)
        
        csv_paths = [path_alphatable_csv, path_trade_signals_csv, path_position_csv]
        csv_zipfile_path = os.path.join(path_alphatable, '因子明细.zip')
        # zip_files(csv_paths, csv_zipfile_path)
        
        results_to_save.update({"csv_zipfile_path": csv_zipfile_path})
        return results_to_save
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
            # "Combined-Price-Volume-Dynamics-Factor-V2":"RANK(TS_CORR($close, $volume, 20)) * RANK(TS_SUM($close, 30))",
            # "Smart_Volume_Cluster_Composite": "(TS_STD($close,5)/(TS_STD($close,20)+1e-8)) * ($volume > TS_QUANTILE($volume,20,0.9))",
            # "RangeVolume_SlopeProduct_5D": "COUNT((($high - $low) < TS_MEAN(($high - $low),5)) && ($volume < TS_MEAN($volume,5)),5)",
            # "Dynamic_Volatility_Bands_Momentum_Stochastic_Oscillator_Factor": "(($close - TS_MIN($low, 14)) / (TS_MAX($high, 14) - TS_MIN($low, 14) + 1e-8)) * 100",
            # "Adjusted_Normalization_Factor_10D_v3": "RANK(TS_ZSCORE(TS_VAR(DELAY($close, 5), 10))) * TS_ZSCORE(DELTA($close, 10))",
            # "Trend_Following_Mean_Reversion_Factor_5D_10D": "TS_RANK(SMA($close - $open, 5, 1), 10) - TS_RANK(SMA(DELTA($close, 1), 5, 1), 10)",
            # "factor_1": "(( $close/DELAY($close,10) - 1 ) * ( POW(TS_MEAN($high - $low, 15) + 1, 0.3333) / (TS_STD($return, 15) + 1e-8) )) * RANK(LOG(TS_MEAN($volume*$close,10) + 1))",


            
            # "Drawdown-Minimization-Factor_20D": "1 - ($high / TS_MAX($high, 20) + 1e-8)",
            # "Price_Volume_Trend_Factor_V2": "(EMA($close, 5) - EMA($close, 20)) * LOG(EMA($volume, 5))",
            # "BollBand_Width_Factor": "(BB_UPPER($close, 20) - BB_LOWER($close, 20)) / (EMA($high - $low, 15) + 1e-8)",
            # "Volume_Price_Volatility_Factor": "ABS(TS_CORR($volume, $return, 10)) * SQRT(TS_STD($close - $open, 20) + 1e-8)",
            # "Fine_Tuned_Mean_Reversion_Factor_7D": "TS_RANK(ABS(DELTA($close, 1)), 5) + TS_RANK(ZSCORE(DELAY($close, 3)), 5)",
            # "Moving_Average_Window_Optimization_Factor": "($close > DELAY($close, 1)) ? (EMA($close, 2) + EMA($close, 5)) : (EMA($close, 10) - EMA($close, 15))",
            # "Adjusted_Normalization_Factor_10D": "RANK(SQRT(TS_VAR(DELAY($close, 5), 10))) * ZSCORE(DELTA($close, 7))",
            # "PV_rel": "ABS(($close - $open) / $open) * RANK(TS_STD($volume, 5) + 1e-8)",
            },
        date_split={
            'train_start_time': '2018-01-01',
            'train_end_time': '2023-12-31',
            'val_start_time': '2024-01-01',
            'val_end_time': '2024-05-31',
            'test_start_time': '2024-06-01',
            'test_end_time': '2025-06-06'
            },
        stop_loss_rate=0.5,
        stop_profit_rate=0.4,
        start_cash=1e7,
        position_size=1.0,
        update_freq=5,
        max_pos_each_stock=0.2,
        stock_pool='中证500',
        industry_neutralization='zscore',  # 行业归一化方法: 'zscore', 'rank', 'quantile'
        )
    
    # 如果要使用LightGBM模型，可以这样调用：
    # results_to_save = backtest(
    #     exprs={...},
    #     date_split={...},
    #     # 其他参数...
    #     model_type='lightgbm'  # 指定使用LightGBM
    # )

    filename = 'results_' + datetime.datetime.today().strftime('%m-%d_%H-%M-%S')
    draw_figures(results_to_save, filename)
    text = {k: str(v) for k, v in results_to_save.items() if isinstance(v, float)}
    print("="*60)
    print("最终回测结果:")
    print("="*60)
    for k, v in text.items():
        print(f"{k}: {v}")
    print("="*60)
    
