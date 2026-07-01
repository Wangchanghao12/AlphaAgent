'''
使用示例：展示如何使用模块化的策略和ML模型
'''
import pandas as pd
import numpy as np
from strategy import FactorStrategy
from ml_models import LightGBMModel, XGBoostModel, create_model

def main():
    """主函数示例"""
    
    # 1. 定义因子表达式
    factor_exprs = {
        "momentum_1m": "TS_MEAN($return, 20)",
        "volatility": "TS_STD($return, 20)", 
        "price_position": "($close - TS_MIN($close, 20)) / (TS_MAX($close, 20) - TS_MIN($close, 20))",
        "volume_ratio": "$volume / TS_MEAN($volume, 20)",
    }
    
    # 2. 创建ML模型实例
    # 方法1: 直接创建LightGBM模型
    ml_model = LightGBMModel(
        model_params={
            'objective': 'regression',
            'metric': 'rmse',
            'num_leaves': 64,
            'max_depth': 4,
            'learning_rate': 0.05,
            'feature_fraction': 0.8,
            'bagging_fraction': 0.8,
            'random_state': 42,
        },
        industry_neutralization='zscore',  # 行业中性化方法
        cross_sectional_norm=True  # 横截面标准化
    )
    
    # 方法2: 使用工厂函数创建模型
    # ml_model = create_model(
    #     model_type='lightgbm',
    #     model_params={'learning_rate': 0.03},
    #     industry_neutralization='rank'
    # )
    
    # 3. 创建策略实例
    strategy = FactorStrategy(
        factor_exprs=factor_exprs,
        ml_model=ml_model,
        label_forward_days=5
    )
    
    # 4. 准备数据 (这里用模拟数据示例)
    # 实际使用时替换为真实数据
    dates = pd.date_range('2023-01-01', '2023-12-31', freq='D')
    instruments = [f'stock_{i:03d}' for i in range(100)]
    
    # 创建模拟数据
    def create_mock_data(dates, instruments):
        np.random.seed(42)
        data = []
        for date in dates:
            for instrument in instruments:
                data.append({
                    'date': date,
                    'instrument': instrument,
                    'open': 100 + np.random.randn() * 5,
                    'high': 105 + np.random.randn() * 5,
                    'low': 95 + np.random.randn() * 5,
                    'close': 100 + np.random.randn() * 5,
                    'close_backadj': 100 + np.random.randn() * 5,
                    'volume': 1000000 + np.random.randn() * 100000,
                    '行业': np.random.choice(['科技', '金融', '医药', '消费'], 1)[0]
                })
        
        df = pd.DataFrame(data)
        df = df.set_index(['date', 'instrument'])
        return df
    
    # 创建训练、验证、测试数据
    full_data = create_mock_data(dates, instruments)
    
    # 数据分割
    train_end = pd.Timestamp('2023-08-31')
    val_end = pd.Timestamp('2023-10-31')
    
    train_data = full_data[full_data.index.get_level_values(0) <= train_end]
    val_data = full_data[
        (full_data.index.get_level_values(0) > train_end) & 
        (full_data.index.get_level_values(0) <= val_end)
    ]
    test_data = full_data[full_data.index.get_level_values(0) > val_end]
    
    print(f"训练集: {len(train_data)} 样本")
    print(f"验证集: {len(val_data)} 样本") 
    print(f"测试集: {len(test_data)} 样本")
    
    # 5. 训练策略
    print("\n=== 开始训练 ===")
    training_results = strategy.train(train_data, val_data)
    
    print("\n=== 训练结果 ===")
    print(f"训练集 IC: {training_results['train_ic']:.4f}")
    print(f"验证集 IC: {training_results['val_ic']:.4f}")
    print(f"训练集 RankIC: {training_results['train_rankic']:.4f}")
    print(f"验证集 RankIC: {training_results['val_rankic']:.4f}")
    
    # 显示特征重要性
    print("\n=== 特征重要性 ===")
    print(training_results['feature_importance'].head(10))
    
    # 6. 模型推理
    print("\n=== 开始推理 ===")
    predictions, inference_results = strategy.inference(test_data)
    
    print("\n=== 推理结果 ===")
    print(f"测试集 IC: {inference_results['ic']:.4f}")
    print(f"测试集 RankIC: {inference_results['rankic']:.4f}")
    print(f"预测样本数: {len(predictions)}")
    
    # 7. 保存和加载策略
    print("\n=== 保存策略 ===")
    strategy.save_strategy('./saved_strategy.pkl')
    
    # 加载策略示例
    print("\n=== 加载策略 ===")
    new_strategy = FactorStrategy()
    new_strategy.load_strategy('./saved_strategy.pkl')
    
    # 使用加载的策略进行推理
    new_predictions, new_inference_results = new_strategy.inference(test_data.iloc[:1000])
    print(f"加载的策略推理结果 IC: {new_inference_results['ic']:.4f}")
    
    print("\n=== 示例完成 ===")

def advanced_usage_example():
    """高级用法示例"""
    print("\n=== 高级用法示例 ===")
    
    # 使用不同的ML模型配置
    models_config = [
        {
            'name': 'LightGBM_默认',
            'model': create_model('lightgbm')
        },
        {
            'name': 'LightGBM_深度',
            'model': create_model(
                'lightgbm',
                model_params={
                    'num_leaves': 128,
                    'max_depth': 6,
                    'learning_rate': 0.03
                },
                industry_neutralization='rank'
            )
        },
        {
            'name': 'LightGBM_保守',
            'model': create_model(
                'lightgbm', 
                model_params={
                    'num_leaves': 16,
                    'max_depth': 2,
                    'learning_rate': 0.1
                },
                industry_neutralization=None
            )
        },
        {
            'name': 'XGBoost_默认',
            'model': create_model('xgboost')
        },
        {
            'name': 'XGBoost_深度',
            'model': create_model(
                'xgboost',
                model_params={
                    'max_depth': 8,
                    'learning_rate': 0.05,
                    'n_estimators': 200,
                    'subsample': 0.9,
                    'colsample_bytree': 0.8
                },
                industry_neutralization='quantile'
            )
        },
        {
            'name': 'XGBoost_保守',
            'model': XGBoostModel(
                model_params={
                    'max_depth': 3,
                    'learning_rate': 0.2,
                    'n_estimators': 50,
                    'subsample': 0.7,
                    'colsample_bytree': 0.6
                },
                industry_neutralization=None,
                cross_sectional_norm=False
            )
        }
    ]
    
    # 对比不同模型的效果
    for config in models_config:
        print(f"\n测试模型: {config['name']}")
        
        strategy = FactorStrategy(
            factor_exprs={
                "simple_momentum": "TS_MEAN($return, 10)",
                "volatility": "TS_STD($return, 20)"
            },
            ml_model=config['model']
        )
        
        # 这里可以添加训练和评估代码
        print(f"模型类型: {type(config['model']).__name__}")
        print(f"行业中性化: {config['model'].industry_neutralization}")
        print(f"横截面标准化: {config['model'].cross_sectional_norm}")
        
        # 显示模型参数
        if isinstance(config['model'], XGBoostModel):
            print("XGBoost特有参数:")
            print(f"  max_depth: {config['model'].model_params.get('max_depth')}")
            print(f"  learning_rate: {config['model'].model_params.get('learning_rate')}")
            print(f"  n_estimators: {config['model'].model_params.get('n_estimators')}")

def xgboost_detailed_example():
    """XGBoost详细使用示例"""
    print("\n=== XGBoost详细使用示例 ===")
    
    # 创建自定义XGBoost模型
    xgb_model = XGBoostModel(
        model_params={
            'objective': 'reg:squarederror',
            'eval_metric': 'rmse',
            'max_depth': 6,
            'learning_rate': 0.08,
            'n_estimators': 150,
            'subsample': 0.85,
            'colsample_bytree': 0.7,
            'min_child_weight': 3,
            'random_state': 42,
            'verbosity': 0
        },
        industry_neutralization='zscore',
        cross_sectional_norm=True
    )
    
    # 定义更复杂的因子表达式
    complex_factors = {
        "momentum_short": "TS_MEAN($return, 5)",
        "momentum_medium": "TS_MEAN($return, 20)",  
        "momentum_long": "TS_MEAN($return, 60)",
        "volatility_short": "TS_STD($return, 10)",
        "volatility_long": "TS_STD($return, 30)",
        "price_trend": "($close - TS_MEAN($close, 20)) / TS_MEAN($close, 20)",
        "volume_trend": "($volume - TS_MEAN($volume, 20)) / TS_MEAN($volume, 20)",
        "high_low_ratio": "($high - $low) / $close"
    }
    
    # 创建策略
    xgb_strategy = FactorStrategy(
        factor_exprs=complex_factors,
        ml_model=xgb_model,
        label_forward_days=3
    )
    
    print("XGBoost策略配置:")
    print(f"因子数量: {len(complex_factors)}")
    print(f"标签前瞻天数: {xgb_strategy.label_forward_days}")
    print(f"模型参数: {xgb_model.model_params}")

if __name__ == "__main__":
    main()
    advanced_usage_example()
    xgboost_detailed_example() 