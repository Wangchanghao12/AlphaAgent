"""
API客户端测试脚本
用于测试回测API接口
"""
import requests
import json
import matplotlib.pyplot as plt
import pandas as pd
from typing import Dict

# 移除中文字体设置，使用默认英文字体

def test_api_health():
    """测试API健康检查"""
    try:
        # 绕过代理，直接连接本地服务
        proxies = {
            'http': None,
            'https': None
        }
        response = requests.get("http://localhost:8001/health", proxies=proxies)
        print("健康检查结果:", response.json())
        return response.status_code == 200
    except Exception as e:
        print(f"健康检查失败: {e}")
        return False

def test_backtest_api():
    """测试回测API"""
    # 测试参数
    test_request = {
        "exprs": {
            "Dynamic_Volatility_Bands_Momentum_Stochastic_Oscillator_Factor": "(($close - TS_MIN($low, 14)) / (TS_MAX($high, 14) - TS_MIN($low, 14) + 1e-8)) * 100",
        },
        "date_split": {
            "train_start_time": "2015-01-01",
            "train_end_time": "2021-12-31",
            "val_start_time": "2022-01-01",
            "val_end_time": "2022-12-31",
            "test_start_time": "2023-01-01",
            "test_end_time": "2024-12-30"
        },
        "start_cash": 10000000.0,
        "update_freq": 5,
        "label_forward_days": 4,
        "stock_pool": "中证500",
        "stop_loss_rate": 0.5,
        "stop_profit_rate": 0.5,
        "position_size": 1.0,
        "max_pos_each_stock": 0.2,
        "use_cache": True,
        "layer_start": 0,
        "layer_end": 1,
        "pred_score_industry_neutralization": True
    }
    
    try:
        print("发送回测请求...请求参数：")
        print(test_request)
        # 绕过代理，直接连接本地服务
        proxies = {
            'http': None,
            'https': None
        }
        response = requests.post(
            "http://localhost:8001/backtest",
            json=test_request,
            timeout=600,  # 5分钟超时
            proxies=proxies
        )
        
        if response.status_code == 200:
            result = response.json()
            print("回测成功!")
            print(f"Success: {result['success']}")
            print(f"Message: {result['message']}")
            
            if result['data']:
                # 打印主要结果指标
                data = result['data']['metrics']
                print("\n主要回测指标:")
                for key in ['IC', 'ICIR', 'RankIC', 'RankICIR', '1day.excess_return_with_cost.information_ratio', '1day.excess_return_with_cost.annualized_return']:
                    if key in data:
                        print(f"{key}: {data[key]:.4f}")

                # 可视化回测结果
                if 'chart' in result['data']:
                    print("\n📈 正在生成可视化图表...")
                    visualize_backtest_results(result['data']['chart'])
                else:
                    print("⚠️ 未找到图表数据，跳过可视化")

            
            
            return True
        else:
            print(f"请求失败，状态码: {response.status_code}")
            try:
                error_detail = response.json()
                if isinstance(error_detail, dict) and 'detail' in error_detail:
                    detail = error_detail['detail']
                    if isinstance(detail, dict):
                        print(f"错误消息: {detail.get('message', '未知错误')}")
                        print(f"错误详情: {detail.get('error', '无详细信息')}")
                    else:
                        print(f"错误信息: {detail}")
                else:
                    print(f"错误信息: {error_detail}")
            except:
                print(f"错误信息: {response.text}")
            return False
            
    except Exception as e:
        print(f"请求异常: {e}")
        return False

def test_expression_api(name="WR", expr="WR($high, $low, $close, 10)"):
    """测试表达式接口"""
    # 测试表达式
    test_request = {
        "name": name,
        "expr": expr
    }
    
    try:
        print("发送表达式测试请求...")
        print(f"因子名: {test_request['name']}")
        print(f"表达式: {test_request['expr']}")
        
        # 绕过代理，直接连接本地服务
        proxies = {
            'http': None,
            'https': None
        }
        response = requests.post(
            "http://localhost:8001/test_expr",
            json=test_request,
            timeout=30,
            proxies=proxies
        )
        # print(response.json())

        if response.status_code == 200:
            result = response.json()
            print("表达式测试结果:")
            print(f"Success: {result['success']}")
            print(f"Message: {result['message']}")
            
            if result['exe_feedback'] is None:
                print("✅ 表达式执行成功!")
                # print(f"执行代码: {result['code']}")
            else:
                print("❌ 表达式执行失败!")
                print(f"错误详情:")
                print(result['exe_feedback'])
                # if result['code']:
                #     print(f"尝试执行的代码: {result['code']}")
            
            return result['exe_feedback'] is None
        else:
            print(f"请求失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            return False
            
    except Exception as e:
        print(f"请求异常: {e}")
        return False

def test_multiple_expressions():
    """测试多个表达式"""
    test_expressions = {
        "WR": "WR($high, $low, $close, 10)",
        "RSI": "RSI($close, 14)",
        "MACD": "MACD($close, 12, 26, 9)",
        "Simple_MA": "TS_MEAN($close, 20)",
        "Volatility": "TS_STD($close, 10)"
    }
    
    print("=" * 50)
    print("测试多个表达式")
    print("=" * 50)
    
    results = {}
    for name, expr in test_expressions.items():
        print(f"\n📊 测试表达式: {name}")
        print("-" * 30)
        success = test_expression_api(name, expr)
        results[name] = success
        print()
    
    # 总结结果
    print("=" * 50)
    print("多表达式测试结果总结:")
    print("=" * 50)
    for name, success in results.items():
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{name}: {status}")
    
    success_count = sum(results.values())
    total_count = len(results)
    print(f"\n总计: {success_count}/{total_count} 个表达式测试通过")
    
    return success_count == total_count

def get_example_request():
    """获取示例请求参数"""
    try:
        # 绕过代理，直接连接本地服务
        proxies = {
            'http': None,
            'https': None
        }
        response = requests.get("http://localhost:8000/example", proxies=proxies)
        if response.status_code == 200:
            example = response.json()
            print("示例请求参数:")
            print(json.dumps(example, indent=2, ensure_ascii=False))
            return example
        else:
            print(f"获取示例失败，状态码: {response.status_code}")
            return None
    except Exception as e:
        print(f"获取示例异常: {e}")
        return None

def visualize_backtest_results(chart_data: Dict):
    """可视化回测结果"""
    try:
        # 创建图表
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('Quantitative Backtest Results Analysis', fontsize=16, fontweight='bold')
        
        # 准备数据
        dates = pd.to_datetime(chart_data['dates'])
        bench_returns = chart_data['bench']
        strategy_returns = chart_data['return']
        costs = chart_data['cost']
        turnover = chart_data['turnover']
        
        # 1. 累计收益率对比图
        ax1 = axes[0, 0]
        ax1.plot(dates, bench_returns, label='Benchmark', linewidth=2, color='blue', alpha=0.7)
        ax1.plot(dates, strategy_returns, label='Strategy', linewidth=2, color='red', alpha=0.7)
        ax1.set_title('Cumulative Returns Comparison')
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Cumulative Returns')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        ax1.tick_params(axis='x', rotation=45)
        
        # 2. 超额收益率图
        ax2 = axes[0, 1]
        excess_returns = [s - b for s, b in zip(strategy_returns, bench_returns)]
        ax2.plot(dates, excess_returns, label='Excess Returns', linewidth=2, color='green', alpha=0.7)
        ax2.axhline(y=0, color='black', linestyle='--', alpha=0.5)
        ax2.set_title('Excess Returns')
        ax2.set_xlabel('Date')
        ax2.set_ylabel('Excess Returns')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        ax2.tick_params(axis='x', rotation=45)
        
        # 3. 交易成本图
        ax3 = axes[1, 0]
        ax3.bar(dates, costs, alpha=0.6, color='orange', width=1)
        ax3.set_title('Daily Trading Costs')
        ax3.set_xlabel('Date')
        ax3.set_ylabel('Trading Costs')
        ax3.grid(True, alpha=0.3)
        ax3.tick_params(axis='x', rotation=45)
        
        # 4. 换手率图
        ax4 = axes[1, 1]
        ax4.bar(dates, turnover, alpha=0.6, color='purple', width=1)
        ax4.set_title('Daily Turnover Rate')
        ax4.set_xlabel('Date')
        ax4.set_ylabel('Turnover Rate')
        ax4.grid(True, alpha=0.3)
        ax4.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        plt.savefig('./test.png', dpi=300, bbox_inches='tight')
        plt.close()  # 关闭图表以释放内存
        print("📊 Chart saved as ./test.png")
        
        # 打印统计信息
        print("\n📊 Backtest Statistics:")
        print(f"Backtest Period: {dates[0].strftime('%Y-%m-%d')} to {dates[-1].strftime('%Y-%m-%d')}")
        print(f"Total Trading Days: {len(dates)}")
        print(f"Strategy Final Return: {strategy_returns[-1]:.4f} ({strategy_returns[-1]*100:.2f}%)")
        print(f"Benchmark Final Return: {bench_returns[-1]:.4f} ({bench_returns[-1]*100:.2f}%)")
        print(f"Cumulative Excess Return: {excess_returns[-1]:.4f} ({excess_returns[-1]*100:.2f}%)")
        print(f"Average Daily Turnover: {sum(turnover)/len(turnover):.4f}")
        print(f"Total Trading Costs: {sum(costs):.6f}")
        
    except Exception as e:
        print(f"Visualization failed: {e}")

def run_expression_test_only():
    """只运行表达式测试"""
    print("="*60)
    print("表达式测试模式")
    print("="*60)
    
    # 健康检查
    if not test_api_health():
        print("API服务不可用，请先启动服务器")
        return False
    
    # 测试表达式
    print("\n📊 测试 WR 表达式...")
    success = test_expression_api("Ff", "$net_mf_amount")
    
    if success:
        print("\n✅ 表达式测试通过!")
    else:
        print("\n❌ 表达式测试失败!")
    
    print("="*60)
    return success

if __name__ == "__main__":
    print("="*60)
    print("量化回测API测试工具")
    print("="*60)
    print("选择测试模式:")
    print("1. 完整测试 (健康检查 + 表达式测试 + 回测)")
    print("2. 仅测试表达式")
    print("3. 测试多个表达式")
    
    try:
        choice = input("请选择 (1/2/3, 默认为 2): ").strip()
        
        if choice == "1":
            # 完整测试
            print("\n" + "="*60)
            print("完整测试模式")
            print("="*60)
            
            # 1. 测试健康检查
            print("1. 测试健康检查...")
            if not test_api_health():
                print("API服务不可用，请先启动服务器")
                exit(1)
            
            # 2. 测试表达式接口
            print("\n2. 测试表达式接口...")
            expr_success = test_expression_api()
            
            # 3. 获取示例参数
            print("\n3. 获取示例参数...")
            example = get_example_request()
            
            # 4. 测试回测接口
            print("\n4. 测试回测接口...")
            print("注意：这可能需要几分钟时间...")
            backtest_success = test_backtest_api()
            
            # 总结测试结果
            print("\n" + "="*60)
            print("测试结果总结:")
            print(f"✅ 健康检查: 通过")
            print(f"{'✅' if expr_success else '❌'} 表达式测试: {'通过' if expr_success else '失败'}")
            print(f"{'✅' if backtest_success else '❌'} 回测接口: {'通过' if backtest_success else '失败'}")
            
            if expr_success and backtest_success:
                print("\n🎉 所有测试通过!")
            else:
                print("\n⚠️  部分测试失败!")
            
        elif choice == "3":
            # 测试多个表达式
            test_multiple_expressions()
            
        else:
            # 仅测试表达式 (默认)
            run_expression_test_only()
            
    except KeyboardInterrupt:
        print("\n用户中断，退出...")
    except Exception as e:
        print(f"出现错误: {e}")
    
    print("="*60) 