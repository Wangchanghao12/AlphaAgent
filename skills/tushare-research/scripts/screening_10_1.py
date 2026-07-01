#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
财务指标初筛脚本 - 10选1
"""

import os
import tushare as ts

# 初始化Tushare
_token = (os.environ.get('TUSHARE_TOKEN') or '').strip()
pro = ts.pro_api(_token) if _token else ts.pro_api()

def get_stock_name(ts_code):
    """获取股票名称"""
    try:
        df = pro.stock_basic(ts_code=ts_code, fields='name')
        if df is not None and len(df) > 0:
            return df.iloc[0]['name']
    except:
        pass
    return ts_code

def get_financial_indicators(ts_code):
    """获取关键财务指标"""
    # 获取最新财务指标
    try:
        df = pro.fina_indicator(ts_code=ts_code, limit=1, fields='ts_code,end_date,roe_dt,profit_dedt_yoy,grossprofit_margin,tr_yoy,debt_to_assets')
        if df is not None and len(df) > 0:
            row = df.iloc[0]
            return {
                'roe': float(row.get('roe_dt', 0) or 0),
                'profit_yoy': float(row.get('profit_dedt_yoy', 0) or 0),
                'gross_margin': float(row.get('grossprofit_margin', 0) or 0),
                'revenue_yoy': float(row.get('tr_yoy', 0) or 0),
                'debt_ratio': float(row.get('debt_to_assets', 0) or 0),
                'report_date': row.get('end_date', '')
            }
    except Exception as e:
        print(f"获取财务指标失败 {ts_code}: {e}")
    return None

def calculate_score(indicators):
    """计算财务评分"""
    if not indicators:
        return 0
    
    score = 0
    
    # ROE评分
    roe = indicators['roe']
    if roe > 15:
        score += 20
    elif roe >= 10:
        score += 10
    
    # 净利润增速评分
    profit_yoy = indicators['profit_yoy']
    if profit_yoy > 30:
        score += 20
    elif profit_yoy >= 10:
        score += 10
    
    # 毛利率评分
    gross = indicators['gross_margin']
    if gross > 30:
        score += 15
    elif gross >= 20:
        score += 8
    
    # 营收增速评分
    revenue = indicators['revenue_yoy']
    if revenue > 20:
        score += 15
    elif revenue >= 10:
        score += 8
    
    # 资产负债率评分
    debt = indicators['debt_ratio']
    if debt < 50:
        score += 10
    elif debt <= 70:
        score += 5
    
    return score

def get_market_cap(ts_code):
    """获取市值（亿元）"""
    try:
        df = pro.daily_basic(ts_code=ts_code, limit=1, fields='total_mv')
        if df is not None and len(df) > 0:
            return float(df.iloc[0]['total_mv']) / 10000  # 万元转亿元
    except:
        pass
    return 0

def main():
    # 候选股票池
    stocks = [
        '603267.SH', '688612.SH', '300188.SZ',
        '600517.SH', '002243.SZ', '688363.SH',
        '000423.SZ', '003022.SZ', '000513.SZ',
        '300296.SZ', '601187.SH', '002126.SZ'
    ]
    
    results = []
    
    print("=" * 80)
    print("财务指标初筛 - 10选1")
    print("=" * 80)
    
    for ts_code in stocks:
        name = get_stock_name(ts_code)
        indicators = get_financial_indicators(ts_code)
        market_cap = get_market_cap(ts_code)
        
        if indicators:
            score = calculate_score(indicators)
            results.append({
                'ts_code': ts_code,
                'name': name,
                'score': score,
                'market_cap': market_cap,
                'indicators': indicators
            })
            
            print(f"\n【{name} - {ts_code}】")
            print(f"  市值: {market_cap:.2f}亿")
            print(f"  ROE: {indicators['roe']:.2f}%")
            print(f"  净利润增速: {indicators['profit_yoy']:.2f}%")
            print(f"  毛利率: {indicators['gross_margin']:.2f}%")
            print(f"  营收增速: {indicators['revenue_yoy']:.2f}%")
            print(f"  资产负债率: {indicators['debt_ratio']:.2f}%")
            print(f"  财务评分: {score}/100")
            print(f"  报告期: {indicators['report_date']}")
    
    # 排序：先按分数降序，同分按市值降序
    results.sort(key=lambda x: (-x['score'], -x['market_cap']))
    
    print("\n" + "=" * 80)
    print("排名结果")
    print("=" * 80)
    
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['name']}({r['ts_code']}) - 评分:{r['score']} - 市值:{r['market_cap']:.2f}亿")
    
    if results:
        winner = results[0]
        print(f"\n🏆 选中股票: {winner['name']}({winner['ts_code']})")
        print(f"   财务评分: {winner['score']}/100")
        print(f"   市值: {winner['market_cap']:.2f}亿")
        return winner['ts_code']
    
    return None

if __name__ == '__main__':
    selected = main()
    if selected:
        with open('/tmp/selected_stock.txt', 'w') as f:
            f.write(selected)
        print(f"\n股票代码已保存: {selected}")
