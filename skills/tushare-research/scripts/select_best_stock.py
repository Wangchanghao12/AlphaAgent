#!/usr/bin/env python3
"""
智能选股脚本 - 综合财务+技术面评分
权重：技术面70% + 财务30%
"""
import os
import sys
import json
from datetime import datetime
from typing import List, Tuple, Dict

import pandas as pd  # 顶部导入

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def get_tushare_token():
    """获取Tushare Token"""
    token = os.environ.get('TUSHARE_TOKEN', '').strip()
    if token:
        return token
    # 从~/.bashrc读取
    try:
        with open(os.path.expanduser('~/.bashrc'), 'r') as f:
            for line in f:
                if 'TUSHARE_TOKEN' in line and 'export' in line:
                    parts = line.split('=')
                    if len(parts) >= 2:
                        return parts[1].strip().strip('"').strip("'")
    except:
        pass
    return None

def get_fundamental_data(ts_code: str) -> Dict:
    """获取财务指标数据"""
    try:
        import tushare as ts
        token = get_tushare_token()
        if not token:
            return {}
        pro = ts.pro_api(token)
        
        # 获取最新财务指标（2025年三季报）
        df = pro.fina_indicator(ts_code=ts_code, period='20250930', fields='ts_code,roe_dt,netprofit_yoy,grossprofit_margin,or_yoy,debt_to_assets')
        if df is not None and not df.empty:
            row = df.iloc[0]
            return {
                'roe': float(row['roe_dt']) if pd.notna(row['roe_dt']) else 0,
                'profit_growth': float(row['netprofit_yoy']) if pd.notna(row['netprofit_yoy']) else 0,
                'gross_margin': float(row['grossprofit_margin']) if pd.notna(row['grossprofit_margin']) else 0,
                'revenue_growth': float(row['or_yoy']) if pd.notna(row['or_yoy']) else 0,
                'debt_ratio': float(row['debt_to_assets']) if pd.notna(row['debt_to_assets']) else 0
            }
    except Exception as e:
        print(f"  ⚠️ 获取财务数据失败: {e}")
    return {}

def calculate_fundamental_score(data: Dict) -> float:
    """计算财务评分（满分30分）"""
    if not data:
        return 0
    
    score = 0
    # ROE评分（6分）
    roe = data.get('roe', 0)
    if roe > 15: score += 6
    elif roe > 10: score += 3
    
    # 净利润增速（6分）
    profit_growth = data.get('profit_growth', 0)
    if profit_growth > 30: score += 6
    elif profit_growth > 10: score += 3
    
    # 毛利率（6分）
    gross_margin = data.get('gross_margin', 0)
    if gross_margin > 30: score += 6
    elif gross_margin > 20: score += 3
    
    # 营收增速（6分）
    revenue_growth = data.get('revenue_growth', 0)
    if revenue_growth > 20: score += 6
    elif revenue_growth > 10: score += 3
    
    # 资产负债率（6分）
    debt_ratio = data.get('debt_ratio', 0)
    if debt_ratio < 50: score += 6
    elif debt_ratio < 70: score += 3
    
    return score

def get_technical_score(ts_code: str) -> float:
    """获取技术面评分（满分70分）"""
    try:
        from technical_analysis import analyze_technical
        result = analyze_technical(ts_code, days=60)
        if result and 'factors' in result:
            factors = result['factors']
            avg_score = sum(factors.values()) / len(factors)
            return avg_score * 0.7  # 转换为70分制
    except Exception as e:
        print(f"  ⚠️ 获取技术面数据失败: {e}")
    return 35  # 默认中等分数

def get_market_cap(ts_code: str) -> float:
    """获取市值（用于同分排序）"""
    try:
        import tushare as ts
        token = get_tushare_token()
        if not token:
            return 0
        pro = ts.pro_api(token)
        df = pro.daily_basic(ts_code=ts_code, trade_date='20260313', fields='ts_code,total_mv')
        if df is not None and not df.empty:
            return float(df.iloc[0]['total_mv'])
    except:
        pass
    return 0

def select_best_stock(candidates: List[str]) -> Tuple[str, float, Dict]:
    """从候选股中选出评分最高的股票"""
    print("\n开始综合评分（财务30% + 技术面70%）...")
    print("-" * 60)
    
    scores = []
    for code in candidates:
        print(f"\n分析 {code}:")
        
        # 财务评分
        fund_data = get_fundamental_data(code)
        fund_score = calculate_fundamental_score(fund_data)
        print(f"  财务得分: {fund_score:.1f}/30")
        
        # 技术面评分
        tech_score = get_technical_score(code)
        print(f"  技术面得分: {tech_score:.1f}/70")
        
        # 总分
        total_score = fund_score + tech_score
        market_cap = get_market_cap(code)
        
        print(f"  综合得分: {total_score:.1f}/100")
        
        scores.append({
            'code': code,
            'total_score': total_score,
            'fund_score': fund_score,
            'tech_score': tech_score,
            'market_cap': market_cap,
            'fund_data': fund_data
        })
    
    # 按总分排序，同分按市值排序
    scores.sort(key=lambda x: (-x['total_score'], -x['market_cap']))
    
    print("\n" + "=" * 60)
    print("评分排名:")
    for i, s in enumerate(scores, 1):
        print(f"{i}. {s['code']} - 总分: {s['total_score']:.1f} (财务{s['fund_score']:.1f} + 技术面{s['tech_score']:.1f})")
    
    best = scores[0]
    print(f"\n✅ 选中股票: {best['code']} (得分: {best['total_score']:.1f})")
    
    return best['code'], best['total_score'], best

def main():
    """主函数 - 从候选股中选出最佳股票"""
    # 读取候选股票
    candidates_file = "/root/.openclaw/workspace/skills/tushare-research/data/current_candidates.json"
    
    if len(sys.argv) > 1:
        # 从命令行参数获取候选股
        candidates = sys.argv[1:]
    elif os.path.exists(candidates_file):
        with open(candidates_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            candidates = data.get('candidates', [])
    else:
        print("❌ 未找到候选股票列表")
        sys.exit(1)
    
    if not candidates:
        print("❌ 候选股票列表为空")
        sys.exit(1)
    
    print(f"候选股票 ({len(candidates)}只): {', '.join(candidates)}")
    
    # 选股
    best_code, score, details = select_best_stock(candidates)
    
    # 输出结果（供调用方解析）
    result = {
        'selected': best_code,
        'score': score,
        'fund_score': details['fund_score'],
        'tech_score': details['tech_score'],
        'market_cap': details['market_cap'],
        'candidates_count': len(candidates),
        'timestamp': datetime.now().isoformat()
    }
    
    print(f"\n📊 选股结果: {best_code}")
    print(f"💯 综合得分: {score:.1f}/100")
    
    return best_code

if __name__ == "__main__":
    selected = main()
    print(f"\n{selected}")  # 最后输出股票代码