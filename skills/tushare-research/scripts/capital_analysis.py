#!/usr/bin/env python3
"""
A股资金面分析脚本 - 使用Tushare数据
包含：龙虎榜、资金流向、股东结构
"""
import sys
import tushare as ts
import pandas as pd
from datetime import datetime, timedelta

# 初始化Tushare
pro = ts.pro_api()

def analyze_top_list(ts_code=None, trade_date=None):
    """分析龙虎榜数据"""
    print("---")
    print("💰 龙虎榜分析")
    print("---")
    
    if not trade_date:
        # 获取最近交易日（从上证指数日线获取）
        try:
            df = pro.index_daily(ts_code='000001.SH', limit=1)
            if not df.empty:
                trade_date = df.iloc[0]['trade_date']
        except:
            pass
    
    try:
        if ts_code:
            # 查询特定股票的龙虎榜
            df = pro.top_list(ts_code=ts_code, trade_date=trade_date)
        else:
            # 查询当日所有龙虎榜
            df = pro.top_list(trade_date=trade_date)
        
        if df.empty:
            print(f"\n  {trade_date} 无龙虎榜数据")
            return
        
        print(f"\n【{trade_date} 龙虎榜】")
        print(f"  上榜股票数: {len(df)}")
        
        # 按净买入排序
        df_sorted = df.sort_values('net_amount', ascending=False)
        
        print(f"\n【净买入 TOP 5】")
        for i, (_, row) in enumerate(df_sorted.head(5).iterrows(), 1):
            net = row['net_amount'] / 10000
            print(f"  {i}. {row['ts_code']} {row['name']}")
            print(f"     净买入: {net:+.0f}万 | 涨跌幅: {row['pct_change']:+.2f}%")
            print(f"     原因: {row['reason']}")
        
        if ts_code:
            # 查询龙虎榜机构交易明细
            try:
                inst_df = pro.top_inst(trade_date=trade_date, ts_code=ts_code)
                if not inst_df.empty:
                    print(f"\n【机构交易明细】")
                    # 合并同一营业部的买卖数据
                    inst_summary = {}
                    for _, row in inst_df.iterrows():
                        name = row['exalter']
                        buy = row['buy'] if pd.notna(row['buy']) else 0
                        sell = row['sell'] if pd.notna(row['sell']) else 0
                        
                        if name not in inst_summary:
                            inst_summary[name] = {'buy': 0, 'sell': 0}
                        inst_summary[name]['buy'] += buy
                        inst_summary[name]['sell'] += sell
                    
                    # 按净买入排序
                    sorted_insts = sorted(inst_summary.items(), 
                                         key=lambda x: x[1]['buy'] - x[1]['sell'], 
                                         reverse=True)
                    
                    for name, data in sorted_insts[:10]:  # 显示前10
                        net = (data['buy'] - data['sell']) / 10000
                        emoji = "🟢" if net > 0 else "🔴"
                        print(f"  {emoji} {name}")
                        print(f"     买入: {data['buy']/10000:.0f}万 | 卖出: {data['sell']/10000:.0f}万 | 净: {net:+.0f}万")
            except Exception as e:
                pass
                
    except Exception as e:
        print(f"  获取龙虎榜失败: {e}")

def analyze_money_flow(ts_code, days=10):
    """分析资金流向"""
    print("\n---")
    print(f"💸 资金流向分析 - {ts_code}")
    print("---")
    
    try:
        df = pro.moneyflow(ts_code=ts_code, limit=days)
        if df.empty:
            print("  获取数据失败")
            return
        
        df = df.sort_values('trade_date', ascending=False)
        
        print(f"\n【近{days}日资金流向】")
        total_net = 0
        
        for _, row in df.iterrows():
            # net_mf_amount 单位是万元
            net = row.get('net_mf_amount', 0)
            total_net += net
            
            emoji = "🟢" if net > 0 else "🔴"
            print(f"  {row['trade_date']} {emoji} 净流入: {net:+.0f}万")
            
            # 显示大单和特大单流向
            buy_lg = row.get('buy_lg_amount', 0)
            sell_lg = row.get('sell_lg_amount', 0)
            buy_elg = row.get('buy_elg_amount', 0)
            sell_elg = row.get('sell_elg_amount', 0)
            
            big_buy = buy_lg + buy_elg
            big_sell = sell_lg + sell_elg
            big_net = big_buy - big_sell
            
            if abs(big_net) > 1000:  # 只显示大额流向
                direction = "流入" if big_net > 0 else "流出"
                print(f"           大单{direction}: {abs(big_net):.0f}万")
        
        # 汇总
        print(f"\n【{days}日汇总】")
        print(f"  净流入: {total_net:+.0f}万")
        avg_daily = total_net / days
        trend = "流入" if avg_daily > 0 else "流出"
        print(f"  日均{trend}: {abs(avg_daily):.0f}万")
        
        # 资金分析结论
        print(f"\n【资金结论】")
        positive_days = len([n for n in df['net_mf_amount'] if n > 0])
        negative_days = len([n for n in df['net_mf_amount'] if n < 0])
        
        if total_net > 100000:  # 10亿以上流入
            print(f"  ✓✓ 资金大幅净流入，主力积极建仓")
            print(f"  ✓✓ 上涨天数:{positive_days}天，资金认可度较高")
        elif total_net > 50000:
            print(f"  ✓ 资金净流入，主力态度偏多")
            print(f"  ✓ 流入天数:{positive_days}天，流出天数:{negative_days}天")
        elif total_net < -100000:
            print(f"  ✗✗ 资金大幅净流出，主力撤退明显")
            print(f"  ✗✗ 下跌天数:{negative_days}天，资金持续离场")
        elif total_net < -50000:
            print(f"  ✗ 资金净流出，主力态度偏空")
            print(f"  ✗ 流出天数:{negative_days}天，流入天数:{positive_days}天")
        else:
            print(f"  → 资金流向平稳，多空分歧不大")
            print(f"  → 流入天数:{positive_days}天，流出天数:{negative_days}天")
        
        # 大单动向
        big_flow_days = sum(1 for _, row in df.iterrows() 
                          if abs(row.get('buy_lg_amount', 0) + row.get('buy_elg_amount', 0) 
                                - row.get('sell_lg_amount', 0) - row.get('sell_elg_amount', 0)) > 1000)
        if big_flow_days >= days * 0.6:
            print(f"  大单动向: 机构参与度较高({big_flow_days}/{days}天)")
        else:
            print(f"  大单动向: 机构参与度一般({big_flow_days}/{days}天)")
        
    except Exception as e:
        print(f"  获取资金流向失败: {e}")

def analyze_holders(ts_code):
    """分析股东结构"""
    print("\n---")
    print(f"👥 股东结构分析 - {ts_code}")
    print("---")
    
    try:
        # 十大流通股东
        df = pro.top10_floatholders(ts_code=ts_code, limit=10)
        if not df.empty:
            print(f"\n【最新十大流通股东】")
            for _, row in df.head(5).iterrows():
                print(f"  {row['holder_name']}")
                print(f"    持股: {row['hold_amount']/10000:.2f}万股 ({row['hold_ratio']:.2f}%)")
    except:
        pass
    
    try:
        # 股东户数 - 去重
        df = pro.stk_holdernumber(ts_code=ts_code, limit=10)
        if not df.empty:
            # 按日期去重，保留最新
            df = df.drop_duplicates(subset=['end_date'], keep='first')
            print(f"\n【股东户数变化】")
            for _, row in df.head(4).iterrows():
                print(f"  {row['end_date']}: {row['holder_num']/10000:.2f}万户")
            
            if len(df) >= 2:
                latest = df.iloc[0]['holder_num']
                prev = df.iloc[1]['holder_num']
                change = (latest - prev) / prev * 100
                if change > 5:
                    print(f"  趋势: 筹码分散（散户增加 {change:.1f}%）⚠️")
                    print(f"  结论: 散户涌入，主力可能派发，短期承压")
                elif change < -5:
                    print(f"  趋势: 筹码集中（主力吸筹 {abs(change):.1f}%）✓")
                    print(f"  结论: 主力收集筹码，关注后续拉升")
                else:
                    print(f"  趋势: 筹码稳定（变化 {change:.1f}%）→")
                    print(f"  结论: 筹码分布均衡，等待方向选择")
    except:
        pass
    
    # 资金综合结论
    print(f"\n【资金综合评估】")
    print(f"  资金面和股东结构反映市场参与者的态度")
    print(f"  • 持续净流入 + 筹码集中 = 看好")
    print(f"  • 持续净流出 + 筹码分散 = 看空")
    print(f"  • 其他组合 = 观望")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 capital_analysis.py <股票代码> [日期YYYYMMDD]")
        print("示例: python3 capital_analysis.py 000001.SZ")
        print("      python3 capital_analysis.py 600519.SH 20260302")
        sys.exit(1)
    
    ts_code = sys.argv[1]
    trade_date = sys.argv[2] if len(sys.argv) > 2 else None
    
    # 分析龙虎榜
    analyze_top_list(ts_code, trade_date)
    
    # 分析资金流向
    analyze_money_flow(ts_code)
    
    # 分析股东结构
    analyze_holders(ts_code)
