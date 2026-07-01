'''
机器学习模型模块
包含模型训练、推理、数据预处理和评估功能
'''
import os
import pickle
import pandas as pd
import numpy as np
import lightgbm as lgb
import xgboost as xgb
from sklearn.metrics import mean_squared_error, mean_absolute_error
from typing import Dict, List, Tuple, Optional, Any
from abc import ABC, abstractmethod


class BaseMLModel(ABC):
    """
    机器学习模型基类，定义模型接口
    """
    
    def __init__(self, 
                 model_params: Dict = None,
                 industry_neutralization: str = 'zscore',
                 cross_sectional_norm: bool = True):
        """
        初始化基础ML模型
        
        参数:
            model_params: 模型参数
            industry_neutralization: 行业中性化方法 ('zscore', 'rank', 'quantile', None)
            cross_sectional_norm: 是否进行横截面标准化
        """
        self.model_params = model_params or self._get_default_params()
        self.industry_neutralization = industry_neutralization
        self.cross_sectional_norm = cross_sectional_norm
        self.model = None
        self.is_trained = False
        
    @abstractmethod
    def _get_default_params(self) -> Dict:
        """获取默认模型参数"""
        pass
        
    @abstractmethod
    def train(self, 
              train_x: pd.DataFrame, 
              train_y: pd.Series,
              val_x: pd.DataFrame = None,
              val_y: pd.Series = None) -> Dict:
        """训练模型"""
        pass
        
    @abstractmethod
    def predict(self, x: pd.DataFrame) -> np.ndarray:
        """模型推理"""
        pass
        
    @abstractmethod
    def save_model(self, filepath: str):
        """保存模型"""
        pass
        
    @abstractmethod
    def load_model(self, filepath: str):
        """加载模型"""
        pass
        
    def cross_sectional_zscore(self, 
                              df: pd.DataFrame, 
                              cols: List[str]) -> pd.DataFrame:
        """
        横截面标准化
        
        参数:
            df: 数据DataFrame (MultiIndex: date, instrument)
            cols: 需要标准化的列
            
        返回:
            标准化后的DataFrame
        """
        if not self.cross_sectional_norm:
            return df
        
            
        print("进行横截面标准化...")
        result_df = df.copy()
        result_df[cols] = df.groupby(level=0)[cols].transform(
            lambda x: (x - x.mean()) / (x.std() + 1e-8)
        )
        return result_df
    
    def industry_neutralize(self, 
                           feature_df: pd.DataFrame, 
                           feature_cols: List[str]) -> pd.DataFrame:
        """
        行业中性化处理
        
        参数:
            feature_df: 因子数据DataFrame (包含'行业'列)
            feature_cols: 需要归一化的因子列名
            
        返回:
            neutralized_df: 行业中性化后的因子数据
        """
        if self.industry_neutralization is None:
            return feature_df
            
        if 'industry' not in feature_df.columns:
            print("警告：feature_df中没有'industry'列，跳过行业中性化")
            return feature_df
            
        
        # 复制原始数据
        neutralized_df = feature_df.copy()
        
        # 直接使用feature_df中的'industry'列
        industry_series = feature_df['industry']
        
        if self.industry_neutralization:
            print(f"开始行业中性化处理，方法: Z-score")
            # 执行行业内Z-score标准化
            def industry_zscore(group):
                if group.isna().any():
                    group_dropna = group.dropna()
                    if len(group_dropna) == 0:
                        return group
                    elif len(group_dropna) == 1:
                        return (group - group.mean())
                    else:
                        return (group - group_dropna.mean()) / (group_dropna.std() + 1e-8)
                else:
                    return (group - group.mean()) / (group.std() + 1e-8)
            
            for factor in feature_cols:
                neutralized_df[factor] = (
                    feature_df.groupby([feature_df.index.get_level_values(0), industry_series])
                    [factor].transform(industry_zscore)
                )
            print("行业中性化处理完成")
        else:
            print("不执行行业中性化")
        return neutralized_df
    
    def calculate_ic_metrics(self, y_true: pd.Series, y_pred: pd.Series) -> Tuple[float, float, float, float]:
        """
        计算IC相关指标：平均IC、平均RankIC、ICIR、RankICIR
        
        参数:
            y_true: 真实值Series (MultiIndex: datetime, instrument)
            y_pred: 预测值Series (MultiIndex: datetime, instrument)
            
        返回:
            tuple: (平均IC, 平均RankIC, ICIR, RankICIR)
        """
        # 检查是否为MultiIndex格式
        if not isinstance(y_true.index, pd.MultiIndex):
            raise ValueError("calculate_ic_metrics需要MultiIndex格式的时间序列数据（date, instrument）")
        
        # 按日期分组计算每日IC
        dates = y_true.index.get_level_values(0).unique()
        ic_list = []
        rank_ic_list = []
        
        for date in dates:
            try:
                # 获取当日数据
                y_true_date = y_true.loc[date]
                y_pred_date = y_pred.loc[date]
                
                # 对齐索引
                common_idx = y_true_date.index.intersection(y_pred_date.index)
                if len(common_idx) < 5:
                    continue
                    
                y_true_aligned = y_true_date.loc[common_idx]
                y_pred_aligned = y_pred_date.loc[common_idx]
                
                # 过滤NaN值，更加稳健的处理
                if hasattr(y_true_aligned, 'isna'):
                    true_nan_mask = y_true_aligned.isna()
                else:
                    true_nan_mask = pd.isna(y_true_aligned)
                    
                if hasattr(y_pred_aligned, 'isna'):
                    pred_nan_mask = y_pred_aligned.isna()
                else:
                    pred_nan_mask = pd.isna(y_pred_aligned)
                
                valid_mask = ~(true_nan_mask | pred_nan_mask)
                
                if valid_mask.sum() < 5:
                    continue
                    
                y_true_clean = y_true_aligned[valid_mask]
                y_pred_clean = y_pred_aligned[valid_mask]
                
                # 再次检查清洗后的数据
                if len(y_true_clean) < 5 or len(y_pred_clean) < 5:
                    continue
                
                # 检查数据变异性（避免常数序列）
                if y_true_clean.std() < 1e-8 or y_pred_clean.std() < 1e-8:
                    continue
                
                # 计算当日IC
                try:
                    correlation_matrix = np.corrcoef(y_true_clean, y_pred_clean)
                    ic = correlation_matrix[0, 1]
                    
                    # 计算当日RankIC
                    rank_correlation_matrix = np.corrcoef(
                        y_true_clean.rank(), 
                        y_pred_clean.rank()
                    )
                    rank_ic = rank_correlation_matrix[0, 1]
                    
                    # 只有当IC不是NaN时才添加
                    if not (np.isnan(ic) or np.isnan(rank_ic)):
                        ic_list.append(ic)
                        rank_ic_list.append(rank_ic)
                        
                except (np.linalg.LinAlgError, ValueError):
                    # 处理线性代数错误（如奇异矩阵）
                    continue
                    
            except (KeyError, IndexError, AttributeError):
                continue
        
        # 如果没有有效数据
        if len(ic_list) == 0:
            return np.nan, np.nan, np.nan, np.nan
        
        # 过滤掉可能的异常值
        ic_array = np.array(ic_list)
        rank_ic_array = np.array(rank_ic_list)
        
        # 移除极端异常值（绝对值大于3的IC值）
        valid_ic_mask = np.abs(ic_array) <= 3
        valid_rank_ic_mask = np.abs(rank_ic_array) <= 3
        
        if valid_ic_mask.sum() == 0 or valid_rank_ic_mask.sum() == 0:
            return np.nan, np.nan, np.nan, np.nan
        
        ic_array_clean = ic_array[valid_ic_mask]
        rank_ic_array_clean = rank_ic_array[valid_rank_ic_mask]
        
        # 计算平均IC和RankIC
        avg_ic = ic_array_clean.mean()
        avg_rank_ic = rank_ic_array_clean.mean()
        
        # 计算ICIR（需要至少5个数据点）
        if len(ic_array_clean) < 5:
            icir = np.nan
        else:
            ic_std = ic_array_clean.std()
            icir = avg_ic / ic_std if ic_std > 1e-8 else np.nan
            
        if len(rank_ic_array_clean) < 5:
            rank_icir = np.nan
        else:
            rank_ic_std = rank_ic_array_clean.std()
            rank_icir = avg_rank_ic / rank_ic_std if rank_ic_std > 1e-8 else np.nan
        
        return avg_ic, avg_rank_ic, icir, rank_icir
    
    # def _calculate_simple_ic(self, y_true: np.ndarray, y_pred: np.ndarray) -> Tuple[float, float]:
    #     """
    #     计算简单IC和RankIC（用于训练时的单次计算）
        
    #     参数:
    #         y_true: 真实值数组
    #         y_pred: 预测值数组
            
    #     返回:
    #         tuple: (IC, RankIC)
    #     """
    #     # 过滤NaN值
    #     mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    #     if mask.sum() < 5:
    #         return np.nan, np.nan
            
    #     y_true_clean = y_true[mask]
    #     y_pred_clean = y_pred[mask]
        
    #     # 计算普通IC
    #     ic = np.corrcoef(y_true_clean, y_pred_clean)[0, 1]
        
    #     # 计算RankIC
    #     rank_ic = np.corrcoef(
    #         pd.Series(y_true_clean).rank(), 
    #         pd.Series(y_pred_clean).rank()
    #     )[0, 1]
        
    #     return ic, rank_ic
    
    def prepare_data(self, 
                    feature_df: pd.DataFrame, 
                    feature_cols: List[str],
                    industry_data: pd.DataFrame = None) -> pd.DataFrame:
        """
        数据预处理pipeline
        
        参数:
            feature_df: 特征数据
            feature_cols: 特征列名
            industry_data: 行业数据（如果需要行业中性化）
            
        返回:
            处理后的特征数据
        """
        
        # 横截面标准化
        processed_df = self.cross_sectional_zscore(feature_df, feature_cols)
        
        # # 行业中性化
        # if self.industry_neutralization and industry_data is not None:
        #     combined_df = pd.concat([processed_df, industry_data['行业']], axis=1)
        #     processed_df = self.industry_neutralize(combined_df, feature_cols)
        #     processed_df = processed_df.drop(columns=['行业'], errors='ignore')
        
        return processed_df




class NoModel(BaseMLModel):
    """
    无模型，直接取因子值，若多因子则求平均
    """
    def __init__(self, 
                 model_params: Dict = None,
                 industry_neutralization: str = 'zscore',
                 cross_sectional_norm: bool = True):
        """
        初始化无模型
        """
        super().__init__(model_params, industry_neutralization, cross_sectional_norm)
        self.sign_dict = {}  # 每个特征的sign
        self.is_trained = False
    
    def _get_default_params(self) -> Dict:
        """无模型无需参数，返回空字典"""
        return {}
    
    def train(self, 
              train_x: pd.DataFrame, 
              train_y: pd.Series,
              val_x: pd.DataFrame = None,
              val_y: pd.Series = None) -> Dict:
        """训练无模型，支持多特征列"""
        self.sign_dict = {}
        for col in train_x.columns:
            # avg_corr = self.calculate_ic_metrics(train_y, train_x[col])[0]
            self.sign_dict[col] = 1 # if avg_corr >= 0 else -1
        self.is_trained = True
        print(f"NoModel训练完成，sign_dict: {self.sign_dict}")
        return {"sign_dict": self.sign_dict}
    
    def predict(self, x: pd.DataFrame) -> np.ndarray:
        """
        无模型推理，对每个特征列乘以其sign后取平均
        """
        if not self.is_trained:
            raise ValueError("模型尚未训练，请先调用train方法")
        missing_cols = [col for col in x.columns if col not in self.sign_dict]
        if missing_cols:
            raise ValueError(f"特征列 {missing_cols} 未在训练阶段出现")
        pred_matrix = np.zeros_like(x.values, dtype=float)
        for idx, col in enumerate(x.columns):
            pred_matrix[:, idx] = x[col].values * self.sign_dict[col]
        return pred_matrix.mean(axis=1)
    
    def save_model(self, filepath: str):
        """保存NoModel模型"""
        if not self.is_trained:
            raise ValueError("模型尚未训练")
        model_info = {
            'sign_dict': self.sign_dict,
            'model_params': self.model_params,
            'industry_neutralization': self.industry_neutralization,
            'cross_sectional_norm': self.cross_sectional_norm,
            'model_type': 'NoModel'
        }
        with open(filepath, 'wb') as f:
            pickle.dump(model_info, f)
        print(f"NoModel模型已保存到: {filepath}")
    
    def load_model(self, filepath: str):
        """加载NoModel模型"""
        with open(filepath, 'rb') as f:
            model_info = pickle.load(f)
        if model_info.get('model_type') != 'NoModel':
            raise ValueError("模型文件不是NoModel模型")
        self.sign_dict = model_info['sign_dict']
        self.model_params = model_info['model_params']
        self.industry_neutralization = model_info['industry_neutralization']
        self.cross_sectional_norm = model_info['cross_sectional_norm']
        self.is_trained = True
        print(f"NoModel模型已从 {filepath} 加载")

class LightGBMModel(BaseMLModel):
    """
    LightGBM模型实现
    """
    
    def __init__(self, 
                 model_params: Dict = None,
                 industry_neutralization: str = 'zscore',
                 cross_sectional_norm: bool = True):
        """
        初始化LightGBM模型
        """
        super().__init__(model_params, industry_neutralization, cross_sectional_norm)
        
    def _get_default_params(self) -> Dict:
        """获取默认LightGBM参数"""
        return {
            'objective': 'regression',
            'metric': 'rmse',
            'boosting_type': 'gbdt',
            'num_leaves': 32,
            'max_depth': 3,
            'learning_rate': 0.05,
            'feature_fraction': 0.8,
            'bagging_fraction': 0.8,
            'bagging_freq': 5,
            'min_child_samples': 20,
            'lambda_l1': 0.1,
            'lambda_l2': 0.1,
            'verbosity': -1,
            'random_state': 0,
            'force_col_wise': True,
            'num_threads': -1,
        }
    
    def train(self, 
              train_x: pd.DataFrame, 
              train_y: pd.Series,
              val_x: pd.DataFrame = None,
              val_y: pd.Series = None) -> Dict:
        """训练LightGBM模型"""
        print("开始LightGBM模型训练...")
        
        # 创建LightGBM数据集
        train_data = lgb.Dataset(train_x, label=train_y)
        valid_sets = [train_data]
        valid_names = ['train']
        
        if val_x is not None and val_y is not None:
            val_data = lgb.Dataset(val_x, label=val_y, reference=train_data)
            valid_sets.append(val_data)
            valid_names.append('val')
        
        # 训练模型
        callbacks = [lgb.log_evaluation(period=0)]
        if len(valid_sets) > 1:
            callbacks.append(lgb.early_stopping(stopping_rounds=10))
        
        self.model = lgb.train(
            self.model_params,
            train_data,
            num_boost_round=100,
            valid_sets=valid_sets,
            valid_names=valid_names,
            callbacks=callbacks
        )
        
        self.is_trained = True
        
        # 模型推理
        train_pred = self.model.predict(train_x, num_iteration=self.model.best_iteration)
        
        # 计算评估指标
        train_mse = mean_squared_error(train_y, train_pred)
        train_mae = mean_absolute_error(train_y, train_pred)
        # 计算IC（训练时使用简单IC计算，因为不是时间序列数据）
        # train_ic, train_rankic = self._calculate_simple_ic(train_y.values, train_pred)
        
        # 特征重要性
        feature_cols = list(train_x.columns)
        importance_dict = dict(zip(feature_cols, 
                                 self.model.feature_importance(importance_type='gain')))
        feature_importance = pd.DataFrame({
            'feature': feature_cols,
            'importance': [importance_dict.get(f, 0) for f in feature_cols]
        }).sort_values('importance', ascending=False)
        
        # 训练结果
        training_results = {
            'train_mse': train_mse,
            'train_mae': train_mae,
            'feature_importance': feature_importance,
            'model_params': self.model_params,
            'feature_cols': feature_cols,
            'best_iteration': self.model.best_iteration,
        }
        
        # 如果有验证集，计算验证集指标
        if val_x is not None and val_y is not None:
            val_pred = self.model.predict(val_x, num_iteration=self.model.best_iteration)
            val_mse = mean_squared_error(val_y, val_pred)
            val_mae = mean_absolute_error(val_y, val_pred)
            training_results.update({
                'val_mse': val_mse,
                'val_mae': val_mae
            })

        
        print("LightGBM模型训练完成!")
        return training_results
    
    def predict(self, x: pd.DataFrame) -> np.ndarray:
        """
        LightGBM模型推理
        
        参数:
            x: 输入特征
            
        返回:
            预测结果
        """
        if not self.is_trained:
            raise ValueError("模型尚未训练，请先调用train方法")
            
        return self.model.predict(x, num_iteration=self.model.best_iteration)
    
    def save_model(self, filepath: str):
        """保存LightGBM模型"""
        if not self.is_trained:
            raise ValueError("模型尚未训练")
            
        model_info = {
            'model': self.model,
            'model_params': self.model_params,
            'industry_neutralization': self.industry_neutralization,
            'cross_sectional_norm': self.cross_sectional_norm,
            'model_type': 'LightGBM'
        }
        
        with open(filepath, 'wb') as f:
            pickle.dump(model_info, f)
        print(f"LightGBM模型已保存到: {filepath}")
    
    def load_model(self, filepath: str):
        """加载LightGBM模型"""
        with open(filepath, 'rb') as f:
            model_info = pickle.load(f)
        
        if model_info.get('model_type') != 'LightGBM':
            raise ValueError("模型文件不是LightGBM模型")
            
        self.model = model_info['model']
        self.model_params = model_info['model_params']
        self.industry_neutralization = model_info['industry_neutralization']
        self.cross_sectional_norm = model_info['cross_sectional_norm']
        self.is_trained = True
        
        print(f"LightGBM模型已从 {filepath} 加载")


class XGBoostModel(BaseMLModel):
    """
    XGBoost模型实现
    """
    
    def __init__(self, 
                 model_params: Dict = None,
                 industry_neutralization: str = 'zscore',
                 cross_sectional_norm: bool = True):
        """
        初始化XGBoost模型
        """
        super().__init__(model_params, industry_neutralization, cross_sectional_norm)
    
    def _get_default_params(self) -> Dict:
        """获取默认XGBoost参数"""
        return {
            'objective': 'reg:squarederror',  # 目标函数：使用均方误差(MSE)作为回归问题的损失函数
            'eval_metric': 'rmse',            # 评估指标：使用均方根误差(RMSE)来评估模型性能
            'booster': 'gbtree',              # 基学习器类型：使用决策树作为基学习器
            'max_depth': 5,                   # 决策树最大深度：控制树的复杂度
            'learning_rate': 0.1,             # 学习率：控制每棵树的权重缩减
            'subsample': 0.8,                 # 样本采样比例：训练每棵树时随机使用80%的训练数据
            'colsample_bytree': 0.5,          # 特征采样比例：训练每棵树时随机使用50%的特征
            'min_child_weight': 1,            # 叶子节点最小样本权重：控制叶子节点的生成条件
            'verbosity': 0,                   # 输出信息详细程度：0表示不输出训练过程信息
            'random_state': 2,               # 随机种子：确保结果可复现
            'n_estimators': 100,              # 树的数量：默认训练100棵树
        }
    
    def train(self, 
              train_x: pd.DataFrame, 
              train_y: pd.Series,
              val_x: pd.DataFrame = None,
              val_y: pd.Series = None,
              early_stopping_rounds: int = 10) -> Dict:
        """
        训练XGBoost模型
        
        参数:
            train_x: 训练特征
            train_y: 训练标签
            val_x: 验证特征 (可选)
            val_y: 验证标签 (可选)
            early_stopping_rounds: 早停轮数
            
        返回:
            训练结果字典
        """
        print("开始XGBoost模型训练...")
        
        # 创建XGBoost模型
        self.model = xgb.XGBRegressor(**self.model_params)
        
        # 准备验证集
        eval_set = None
        if val_x is not None and val_y is not None:
            eval_set = [(train_x, train_y), (val_x, val_y)]
        else:
            eval_set = [(train_x, train_y)]
        
        # 训练模型
        self.model.fit(
            train_x, 
            train_y,
            eval_set=eval_set,
            verbose=False
        )
        
        self.is_trained = True
        
        # 模型推理
        train_pred = self.model.predict(train_x)
        
        # 计算评估指标
        train_mse = mean_squared_error(train_y, train_pred)
        train_mae = mean_absolute_error(train_y, train_pred)
        
        # 特征重要性
        feature_cols = list(train_x.columns)
        feature_importance = pd.DataFrame({
            'feature': feature_cols,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        # 训练结果
        training_results = {
            'train_mse': train_mse,
            'train_mae': train_mae,
            'feature_importance': feature_importance,
            'model_params': self.model_params,
            'feature_cols': feature_cols,
            'best_iteration': self.model.best_iteration if hasattr(self.model, 'best_iteration') else None,
        }
        
        # 如果有验证集，计算验证集指标
        if val_x is not None and val_y is not None:
            val_pred = self.model.predict(val_x)
            val_mse = mean_squared_error(val_y, val_pred)
            val_mae = mean_absolute_error(val_y, val_pred)
            
            training_results.update({
                'val_mse': val_mse,
                'val_mae': val_mae
            })
        
        print("XGBoost模型训练完成!")
        return training_results
    
    def predict(self, x: pd.DataFrame) -> np.ndarray:
        """
        XGBoost模型推理
        
        参数:
            x: 输入特征
            
        返回:
            预测结果
        """
        if not self.is_trained:
            raise ValueError("模型尚未训练，请先调用train方法")
            
        return self.model.predict(x)
    
    def save_model(self, filepath: str):
        """保存XGBoost模型"""
        if not self.is_trained:
            raise ValueError("模型尚未训练")
            
        model_info = {
            'model': self.model,
            'model_params': self.model_params,
            'industry_neutralization': self.industry_neutralization,
            'cross_sectional_norm': self.cross_sectional_norm,
            'model_type': 'XGBoost'
        }
        
        with open(filepath, 'wb') as f:
            pickle.dump(model_info, f)
        print(f"XGBoost模型已保存到: {filepath}")
    
    def load_model(self, filepath: str):
        """加载XGBoost模型"""
        with open(filepath, 'rb') as f:
            model_info = pickle.load(f)
        
        if model_info.get('model_type') != 'XGBoost':
            raise ValueError("模型文件不是XGBoost模型")
            
        self.model = model_info['model']
        self.model_params = model_info['model_params']
        self.industry_neutralization = model_info['industry_neutralization']
        self.cross_sectional_norm = model_info['cross_sectional_norm']
        self.is_trained = True
        
        print(f"XGBoost模型已从 {filepath} 加载")


# 模型工厂函数
def create_model(model_type: str = 'lightgbm', **kwargs) -> BaseMLModel:
    """
    创建ML模型实例
    
    参数:
        model_type: 模型类型 ('lightgbm', 'xgboost')
        **kwargs: 模型参数
        
    返回:
        模型实例
    """
    if model_type.lower() == 'lightgbm':
        return LightGBMModel(**kwargs)
    elif model_type.lower() == 'xgboost':
        return XGBoostModel(**kwargs)
    else:
        raise ValueError(f"不支持的模型类型: {model_type}")
