'''
基于因子表达式的量化策略类
'''
import os
import pickle
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from expression_manager.expr_parser import parse_expression
from expression_manager.function_lib import *
import datetime
from ml_models import BaseMLModel
import pdb
from sklearn.metrics import mean_squared_error, mean_absolute_error

class FactorStrategy:
    """
    基于因子表达式的量化策略类
    
    主要功能：
    1. 因子表达式解析和计算
    2. 与ML模型配合进行训练和推理
    """
    
    def __init__(self, 
                 factor_exprs: Dict[str, str] = None,
                 base_features: Dict[str, str] = {},
                 ml_model: BaseMLModel = None,
                 cache_dir: str = './pkl_files',
                 label_forward_days: int = 4):
        """
        初始化策略类
        
        参数:
            factor_exprs: 因子表达式字典 {因子名: 表达式}
            base_features: 基础特征表达式字典
            ml_model: ML模型实例 (来自ml_models模块)
            cache_dir: 缓存目录
            label_forward_days: 标签前瞻天数
        """
        self.factor_exprs = factor_exprs or {}
        self.base_features = base_features # or self._get_default_base_features()
        self.ml_model = ml_model
        self.cache_dir = cache_dir
        self.label_forward_days = label_forward_days
        
        # 因子相关属性
        self.feature_cols = []
        
        # 创建缓存目录
        os.makedirs(self.cache_dir, exist_ok=True)
        
    def _get_default_base_features(self) -> Dict[str, str]:
        """获取默认基础特征"""
        return {
            "intraday_return": "($close-$open)/$open",
            "return_1d": "$close/DELAY($close, 1)-1", 
            "relative_volume": "$volume/TS_MEAN($volume, 20)-1", 
            "amplitude": "($high-$low)/DELAY($close, 1)",
        }
    
    def _calculate_features(self, 
                          combined_df: pd.DataFrame, 
                          start_date: str = None, 
                          end_date: str = None,
                          use_cache: bool = False) -> pd.DataFrame:
        """
        计算因子和特征
        
        参数:
            combined_df: 原始数据DataFrame (MultiIndex: date, instrument)
            start_date: 开始日期
            end_date: 结束日期
            
        返回:
            feature_df: 包含所有因子的DataFrame
        """
        print("开始计算因子和特征...")
        
        # 复制数据避免修改原始数据
        df = combined_df.copy()
        
        # 计算return字段（如果不存在）
        if 'return' not in df.columns:
            df.loc[:, 'return'] = df.loc[:, 'close'].groupby('instrument').shift(0) / df.loc[:, 'close'].groupby('instrument').shift(1) - 1
        
        
        # 合并所有表达式
        all_exprs = {**self.factor_exprs, **self.base_features}
        
        # 计算每个因子
        for name, expr in all_exprs.items():
            print(f"正在计算因子: {name}")
            
            # 检查缓存
            # cache_key = f"{name}_{start_date}_{end_date}"
            # pkl_path = os.path.join(self.cache_dir, f'{cache_key}.pkl')
            
            # if os.path.exists(pkl_path) and use_cache:
            #     print(f"从缓存加载因子 {name}")
            #     df[name] = pd.read_pickle(pkl_path)
            # else:
            # 解析表达式
            parsed_expr = parse_expression(expr)
            
            # 替换变量名
            for col in df.columns:
                parsed_expr = parsed_expr.replace('$'+col, f"df['{col}']")

            # 替换nan为np.nan
            parsed_expr = parsed_expr.replace("nan", "np.nan")
            print(f"解析后的因子表达式: {parsed_expr}")
            # 计算因子值
            try:
                df[name] = eval(parsed_expr)
                # assert df[name].dtype == np.float64, f"因子 {name} 计算结果类型错误"
                # assert (~df[name].isna()).sum() / (~df['open'].isna()).sum() > 0.9, f"因子 {name} 计算结果有{(~df[name].isna()).sum() / (~df['open'].isna()).sum():.4%}空值"
                # 保存到缓存
                # df[name].to_pickle(pkl_path)
                # print(f"因子 {name} 计算完成并缓存")
            except Exception as e:
                print(f"计算因子 {name} 时出错: {e}")
                raise e
                # df[name] = np.nan
        
        # 提取特征列
        self.feature_cols = list(all_exprs.keys())
        feature_df = df[self.feature_cols].copy()
        
        print(f"因子计算完成，共 {len(self.feature_cols)} 个因子")
        return feature_df
    
    def train(self, 
              train_df: pd.DataFrame, 
              val_df: pd.DataFrame) -> Dict:
        """
        训练模型
        
        参数:
            train_df: 训练集数据 (MultiIndex: date, instrument)
            val_df: 验证集数据 (MultiIndex: date, instrument)
            
        返回:
            训练结果字典
        """
        if self.ml_model is None:
            raise ValueError("ML模型未设置，请在初始化时传入ml_model参数")

        
        # 获取时间范围
        train_start = train_df.index.get_level_values(0).min().strftime('%Y-%m-%d')
        train_end = train_df.index.get_level_values(0).max().strftime('%Y-%m-%d')
        val_start = val_df.index.get_level_values(0).min().strftime('%Y-%m-%d')
        val_end = val_df.index.get_level_values(0).max().strftime('%Y-%m-%d')
        # assert datetime.timedelta(days=1) < (pd.to_datetime(val_start) - pd.to_datetime(train_end)), "验证集开始日期必须晚于训练集结束日期"
        
        # 合并训练集和验证集用于因子计算
        combined_df = pd.concat([train_df, val_df])
        
        # 计算因子
        feature_df = self._calculate_features(combined_df, train_start, val_end)
        

        # 构建标签：未来收益
        print(f"构建标签，前瞻{self.label_forward_days}天...")
        feature_df.loc[:, 'label'] = (
            combined_df.loc[:, 'close_backadj'].groupby('instrument').shift(-self.label_forward_days) / 
            combined_df.loc[:, 'close_backadj'].groupby('instrument').shift(0) - 1
        )
        
        # 分离训练集和验证集，保留非空值
        train_feature_df = feature_df.loc[train_df.index].dropna()
        val_feature_df = feature_df.loc[val_df.index].dropna()

        print("\n\n训练集因子值数据：\n {} \n\n".format(train_feature_df))
        
        # 使用ML模型进行数据预处理
        print("ML模型数据预处理...")
        industry_data = pd.concat([train_df, val_df])[['行业']] if '行业' in pd.concat([train_df, val_df]).columns else None
        
        # 截面归一化、行业中心化
        processed_train_df = self.ml_model.prepare_data(
            train_feature_df[self.feature_cols + ['label']], 
            self.feature_cols,
            industry_data.loc[train_df.index] if industry_data is not None else None
        )
        
        # 处理验证数据  
        processed_val_df = self.ml_model.prepare_data(
            val_feature_df[self.feature_cols + ['label']], 
            self.feature_cols,
            industry_data.loc[val_df.index] if industry_data is not None else None
        )
        
        # 准备训练数据
        train_x = processed_train_df[self.feature_cols]
        train_y = processed_train_df['label']
        val_x = processed_val_df[self.feature_cols]
        val_y = processed_val_df['label']
        
        print(f"训练集大小: {len(train_x)}, 验证集大小: {len(val_x)}")
        print(f"特征数量: {len(self.feature_cols)}")
        
        # 使用ML模型训练
        training_results = self.ml_model.train(
            train_x=train_x,
            train_y=train_y,
            val_x=val_x,
            val_y=val_y
        )
        train_pred = pd.Series(self.ml_model.predict(train_x), index=train_x.index)
        val_pred = pd.Series(self.ml_model.predict(val_x), index=val_x.index)

        train_ic, train_rankic, train_icir, train_rankicir = self.ml_model.calculate_ic_metrics(train_y, train_pred)
        val_ic, val_rankic, val_icir, val_rankicir = self.ml_model.calculate_ic_metrics(val_y, val_pred)

        training_results.update({
            'train_ic': train_ic,
            'train_rankic': train_rankic,
            'train_icir': train_icir,
            'train_rankicir': train_rankicir,
            'val_ic': val_ic,
            'val_rankic': val_rankic,
            'val_icir': val_icir,
            'val_rankicir': val_rankicir,
        })
        
        # 添加策略相关信息
        training_results.update({
            'factor_exprs': self.factor_exprs,
            'base_features': self.base_features,
            'feature_cols': self.feature_cols,
        })
        
        print("策略训练完成!")
        return training_results
    
    # def inference(self, 
    #               test_df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
    #     """
    #     模型推理
        
    #     参数:
    #         test_df: 测试集数据 (MultiIndex: date, instrument)
            
    #     返回:
    #         tuple: (预测结果DataFrame, 推理结果字典)
    #     """
    #     if self.ml_model is None:
    #         raise ValueError("ML模型未设置")
    #     if not self.ml_model.is_trained:
    #         raise ValueError("模型尚未训练，请先调用train方法")
            
    #     print("开始模型推理...")
        
    #     # 获取时间范围
    #     test_start = test_df.index.get_level_values(0).min().strftime('%Y-%m-%d')
    #     test_end = test_df.index.get_level_values(0).max().strftime('%Y-%m-%d')

    #     # 计算因子
    #     feature_df = self._calculate_features(test_df, test_start, test_end)
        
    #     # 使用ML模型进行数据预处理
    #     industry_data = test_df[['industry']] if 'industry' in test_df.columns else None

    #     # 截面归一化、行业中心化
    #     processed_df = self.ml_model.prepare_data(
    #         feature_df, 
    #         self.feature_cols,
    #         industry_data
    #     )
        
    #     # 准备推理数据
    #     test_x = processed_df[self.feature_cols]

    #     # ML模型推理
    #     test_pred = self.ml_model.predict(test_x)

    #     # 构建结果DataFrame
    #     pred_df = pd.DataFrame(
    #         test_pred, 
    #         index=test_df.index, 
    #         columns=['pred']
    #     )

    #     if 'label' not in test_df.columns:
    #         # 计算推理的IC和RankIC
    #         test_df.loc[:, 'label'] = (
    #             test_df.loc[:, 'close_backadj'].groupby('instrument').shift(-self.label_forward_days) / 
    #             test_df.loc[:, 'close_backadj'].groupby('instrument').shift(0) - 1
    #         )

    #         test_df.loc[:, 'pred'] = test_pred
    #         label_pred = test_df[['label', 'pred']].dropna()
            
    #         try:
    #             mse = mean_squared_error(label_pred['label'], label_pred['pred'])
    #             mae = mean_absolute_error(label_pred['label'], label_pred['pred'])
    #         except Exception as e:
    #             print(f"计算MSE和MAE时出错: {e}")
    #             mse = np.nan
    #             mae = np.nan
                
    #         ic, rankic, icir, rankicir = self.ml_model.calculate_ic_metrics(label_pred['label'], label_pred['pred'])
            
    #         inference_results = {
    #             'mse': mse,
    #             'mae': mae,
    #             'ic': ic,
    #             'rankic': rankic,
    #             'icir': icir,
    #             'rankicir': rankicir,
    #         }

        
    #     # 对预测结果进行行业中性化
    #     if self.ml_model.industry_neutralization is not None:
    #         pred_df = self.ml_model.industry_neutralize(pd.concat([pred_df, industry_data], axis=1), ['pred'])[['pred']]

        
    #     print(f"推理完成，预测了 {len(pred_df)} 个样本")
    #     # print(f"Inference IC: {ic:.4f}, RankIC: {rankic:.4f}")
    #     return pred_df, inference_results
    

    def inference(self, 
                  test_df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """
        模型推理
        
        参数:
            test_df: 测试集数据 (MultiIndex: date, instrument)
            
        返回:
            tuple: (预测结果DataFrame, 推理结果字典)
        """
        if self.ml_model is None:
            raise ValueError("ML模型未设置")
        # if not self.ml_model.is_trained:
        #     raise ValueError("模型尚未训练，请先调用train方法")
            
        print("开始模型推理...")
        
        # 获取时间范围
        test_start = test_df.index.get_level_values(0).min().strftime('%Y-%m-%d')
        test_end = test_df.index.get_level_values(0).max().strftime('%Y-%m-%d')

        # 计算因子
        feature_df = self._calculate_features(test_df, test_start, test_end)
        
        # 使用ML模型进行数据预处理
        industry_data = test_df[['industry']] if 'industry' in test_df.columns else None

        # 截面归一化、行业中心化
        processed_df = self.ml_model.prepare_data(
            feature_df, 
            self.feature_cols,
            industry_data
        )
        
        # 准备推理数据
        test_x = processed_df[self.feature_cols]

        # ML模型推理
        test_pred = test_x.values.mean(axis=1)

        # 构建结果DataFrame
        pred_df = pd.DataFrame(
            test_pred, 
            index=test_df.index, 
            columns=['pred']
        )

        if 'label' not in test_df.columns:
            # 计算推理的IC和RankIC
            test_df.loc[:, 'label'] = (
                test_df.loc[:, 'close_backadj'].groupby('instrument').shift(-self.label_forward_days) / 
                test_df.loc[:, 'close_backadj'].groupby('instrument').shift(0) - 1
            )

            test_df.loc[:, 'pred'] = test_pred
            label_pred = test_df[['label', 'pred']].dropna()
            
            # try:
            #     mse = mean_squared_error(label_pred['label'], label_pred['pred'])
            #     mae = mean_absolute_error(label_pred['label'], label_pred['pred'])
            # except Exception as e:
            #     print(f"计算MSE和MAE时出错: {e}")
            #     mse = np.nan
            #     mae = np.nan
                
            # ic, rankic, icir, rankicir = self.ml_model.calculate_ic_metrics(label_pred['label'], label_pred['pred'])
            
            # inference_results = {
            #     'ic': ic,
            #     'rankic': rankic,
            #     'icir': icir,
            #     'rankicir': rankicir,
            # }
            inference_results = {}
        # 对预测结果进行行业中性化
        if self.ml_model.industry_neutralization is not None:
            pred_df = self.ml_model.industry_neutralize(pd.concat([pred_df, industry_data], axis=1), ['pred'])[['pred']]

        
        print(f"推理完成，预测了 {len(pred_df)} 个样本")
        # print(f"Inference IC: {ic:.4f}, RankIC: {rankic:.4f}")
        return pred_df, inference_results

    def save_strategy(self, filepath: str):
        """保存策略（包括ML模型）"""
        if self.ml_model is None:
            raise ValueError("ML模型未设置")
        if not self.ml_model.is_trained:
            raise ValueError("模型尚未训练")
            
        strategy_info = {
            'factor_exprs': self.factor_exprs,
            'base_features': self.base_features,
            'feature_cols': self.feature_cols,
            'label_forward_days': self.label_forward_days,
            'ml_model': self.ml_model,
        }
        
        with open(filepath, 'wb') as f:
            pickle.dump(strategy_info, f)
        print(f"策略已保存到: {filepath}")
    
    def load_strategy(self, filepath: str):
        """加载策略（包括ML模型）"""
        with open(filepath, 'rb') as f:
            strategy_info = pickle.load(f)
        
        self.factor_exprs = strategy_info['factor_exprs']
        self.base_features = strategy_info['base_features']
        self.feature_cols = strategy_info['feature_cols']
        self.label_forward_days = strategy_info['label_forward_days']
        self.ml_model = strategy_info['ml_model']
        
        print(f"策略已从 {filepath} 加载")
