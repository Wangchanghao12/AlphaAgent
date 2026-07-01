#!/usr/bin/env python3
"""
A股情绪面分析脚本 - 使用Tushare数据
包含：市场情绪、涨跌停统计、板块热度
"""
import sys
import tushare as ts
import pandas as pd
from datetime import datetime

# 初始化Tushare
pro = ts.pro_api()

def analyze_market_sentiment(trade_date=None):
    """分析市场情绪"""
    print("---")
    print("😊 市场情绪分析")
    print("---")
    
    if not trade_date:
        # 获取最近交易日
        try:
            df = pro.index_daily(ts_code='000001.SH', limit=1)
            if not df.empty:
                trade_date = df.iloc[0]['trade_date']
        except:
            print("  获取日期失败")
            return
    
    try:
        # 获取当日所有股票行情
        df = pro.daily(trade_date=trade_date)
        if df.empty:
            print(f"  {trade_date} 无数据")
            return
        
        print(f"\n【{trade_date} 市场统计】")
        
        # 涨跌统计
        up_count = len(df[df['pct_chg'] > 0])
        down_count = len(df[df['pct_chg'] < 0])
        flat_count = len(df[df['pct_chg'] == 0])
        total = len(df)
        
        print(f"  上涨: {up_count}只 ({up_count/total*100:.1f}%)")
        print(f"  下跌: {down_count}只 ({down_count/total*100:.1f}%)")
        print(f"  平盘: {flat_count}只")
        
        # 涨跌停统计
        limit_up = len(df[df['pct_chg'] >= 9.9])  # 涨停
        limit_down = len(df[df['pct_chg'] <= -9.9])  # 跌停
        
        print(f"\n【涨跌停统计】")
        print(f"  涨停: {limit_up}只 🔥")
        print(f"  跌停: {limit_down}只 ❄️")
        
        # 市场情绪判断
        print(f"\n【情绪判断】")
        if up_count > down_count * 1.5 and limit_up > 50:
            sentiment = "极度乐观 🔥🔥🔥"
        elif up_count > down_count and limit_up > 30:
            sentiment = "乐观 🔥🔥"
        elif up_count > down_count:
            sentiment = "偏乐观 🔥"
        elif down_count > up_count * 1.5 and limit_down > 50:
            sentiment = "极度悲观 ❄️❄️❄️"
        elif down_count > up_count and limit_down > 30:
            sentiment = "悲观 ❄️❄️"
        elif down_count > up_count:
            sentiment = "偏悲观 ❄️"
        else:
            sentiment = "震荡整理 😐"
        print(f"  整体情绪: {sentiment}")
        
        # 涨幅榜
        print(f"\n【涨幅榜 TOP 5】")
        df_up = df.nlargest(5, 'pct_chg')
        for i, (_, row) in enumerate(df_up.iterrows(), 1):
            print(f"  {i}. {row['ts_code']} 涨幅: {row['pct_chg']:+.2f}%")
        
        # 跌幅榜
        print(f"\n【跌幅榜 TOP 5】")
        df_down = df.nsmallest(5, 'pct_chg')
        for i, (_, row) in enumerate(df_down.iterrows(), 1):
            print(f"  {i}. {row['ts_code']} 跌幅: {row['pct_chg']:+.2f}%")
        
    except Exception as e:
        print(f"  分析失败: {e}")

def analyze_sector_sentiment(trade_date=None):
    """分析板块情绪"""
    print("\n---")
    print("📊 板块情绪分析")
    print("---")
    
    if not trade_date:
        try:
            df = pro.index_daily(ts_code='000001.SH', limit=1)
            if not df.empty:
                trade_date = df.iloc[0]['trade_date']
        except:
            return
    
    try:
        # 获取行业指数涨跌
        df = pro.ths_daily(trade_date=trade_date)
        if df.empty:
            print("  暂无板块数据")
            return
        
        print(f"\n【{trade_date} 板块涨跌】")
        
        # 涨幅最大板块
        print(f"\n🔥 领涨板块:")
        df_up = df.nlargest(5, 'pct_change')
        for i, (_, row) in enumerate(df_up.iterrows(), 1):
            # 获取板块名称
            try:
                name = row.get('name', row['ts_code'])
            except:
                name = row['ts_code']
            print(f"  {i}. {name}: {row['pct_change']:+.2f}%")
        
        # 跌幅最大板块
        print(f"\n❄️ 领跌板块:")
        df_down = df.nsmallest(5, 'pct_change')
        for i, (_, row) in enumerate(df_down.iterrows(), 1):
            try:
                name = row.get('name', row['ts_code'])
            except:
                name = row['ts_code']
            print(f"  {i}. {name}: {row['pct_change']:+.2f}%")
        
    except Exception as e:
        print(f"  板块分析失败: {e}")

def analyze_industry_stocks(ts_code):
    """分析同行业股票表现 - 优化版，限制查询数量"""
    print("\n---")
    print(f"🏭 同行业对比 - {ts_code}")
    print("---")
    
    try:
        # 获取股票所属行业
        basic = pro.stock_basic(ts_code=ts_code, fields='ts_code,name,industry')
        if basic.empty:
            return
        
        industry = basic.iloc[0]['industry']
        stock_name = basic.iloc[0]['name']
        print(f"\n【所属行业: {industry} (Tushare分类)】")
        
        # 获取同行业其他股票 - 限制数量
        peers = pro.stock_basic(industry=industry, fields='ts_code,name')
        if len(peers) <= 1:
            print("  同行业股票较少")
            return
        
        print(f"  同行业共 {len(peers)} 只股票")
        
        # 获取最近行情
        trade_date = pro.index_daily(ts_code='000001.SH', limit=1).iloc[0]['trade_date']
        
        print(f"\n【同行业表现 ({trade_date}) TOP 10】")
        performances = []
        
        # 限制查询数量，最多查20只
        for _, peer in peers.head(20).iterrows():
            try:
                daily = pro.daily(ts_code=peer['ts_code'], trade_date=trade_date)
                if not daily.empty:
                    performances.append({
                        'ts_code': peer['ts_code'],
                        'name': peer['name'],
                        'pct_chg': daily.iloc[0]['pct_chg']
                    })
            except:
                continue
        
        # 排序显示
        performances.sort(key=lambda x: x['pct_chg'], reverse=True)
        
        # 显示前5名
        for i, p in enumerate(performances[:5], 1):
            marker = " ⬅️ 目标股" if p['ts_code'] == ts_code else ""
            print(f"  {i}. {p['name']}: {p['pct_chg']:+.2f}%{marker}")
        
        # 如果目标股不在前5，显示它的位置
        target_rank = next((i for i, p in enumerate(performances) if p['ts_code'] == ts_code), None)
        if target_rank is not None and target_rank >= 5:
            p = performances[target_rank]
            print(f"  ...")
            print(f"  {target_rank+1}. {p['name']}: {p['pct_chg']:+.2f}% ⬅️ 目标股")
        
        # 计算行业平均
        if performances:
            avg_change = sum(p['pct_chg'] for p in performances) / len(performances)
            print(f"\n  行业平均涨幅: {avg_change:+.2f}%")
            
            # 找出目标股票的表现
            target_perf = next((p for p in performances if p['ts_code'] == ts_code), None)
            if target_perf:
                diff = target_perf['pct_chg'] - avg_change
                rank_info = f"  行业排名: {target_rank+1}/{len(performances)}"
                print(rank_info)
                if diff > 0:
                    print(f"  {stock_name} 跑赢行业: +{diff:.2f}% 👍")
                else:
                    print(f"  {stock_name} 跑输行业: {diff:.2f}% 👎")
        
    except Exception as e:
        print(f"  分析失败: {e}")


def analyze_institution_sentiment(ts_code):
    """分析机构情绪 - 基于研报数据"""
    print("\n---")
    print("🏛️ 机构情绪分析")
    print("---")
    
    try:
        # 获取研报数据 - 使用正确的接口名 report_rc
        reports = pro.query('report_rc', ts_code=ts_code)
        if reports.empty:
            print("  暂无机构研报覆盖")
            return
        
        # 只取最近6个月的研报
        from datetime import datetime, timedelta
        six_months_ago = (datetime.now() - timedelta(days=180)).strftime('%Y%m%d')
        reports = reports[reports['report_date'] >= six_months_ago]
        
        # 去重：同一机构同一日期只保留一条
        reports = reports.drop_duplicates(subset=['org_name', 'report_date'], keep='first')
        
        if reports.empty:
            print("  近6个月暂无机构研报覆盖")
            return
        
        print(f"\n【研报覆盖情况】")
        print(f"  近6个月研报数量: {len(reports)} 份")
        
        # 统计评级分布
        rating_map = {
            '买入': 0, '增持': 0, '中性': 0, 
            '减持': 0, '卖出': 0, '推荐': 0, '无': 0, '其他': 0
        }
        
        for _, row in reports.iterrows():
            rating = str(row.get('rating', ''))
            if '买入' in rating:
                rating_map['买入'] += 1
            elif '增持' in rating or '推荐' in rating:
                rating_map['推荐'] += 1
            elif '中性' in rating or '持有' in rating:
                rating_map['中性'] += 1
            elif '减持' in rating:
                rating_map['减持'] += 1
            elif '卖出' in rating:
                rating_map['卖出'] += 1
            elif rating == '无' or rating == '':
                rating_map['无'] += 1
            else:
                rating_map['其他'] += 1
        
        print(f"\n【评级分布】")
        for rating, count in rating_map.items():
            if count > 0:
                pct = count / len(reports) * 100
                print(f"  {rating}: {count}份 ({pct:.1f}%)")
        
        # 判断机构情绪
        positive = rating_map['买入'] + rating_map['推荐']
        neutral = rating_map['中性']
        negative = rating_map['减持'] + rating_map['卖出']
        no_rating = rating_map['无'] + rating_map['其他']
        
        print(f"\n【机构情绪判断】")
        if positive > neutral + negative and rating_map['买入'] >= 2:
            sentiment = "强烈看好 🔥🔥🔥"
        elif positive > neutral + negative:
            sentiment = "看好 🔥🔥"
        elif positive > negative:
            sentiment = "偏乐观 🔥"
        elif negative > positive:
            sentiment = "偏谨慎 ❄️"
        else:
            sentiment = "中性 😐"
        print(f"  整体情绪: {sentiment}")
        
        # 显示最新研报
        print(f"\n【最新研报 TOP 3】")
        latest = reports.head(3)
        for i, (_, row) in enumerate(latest.iterrows(), 1):
            org = row.get('org_name', '未知机构')
            author = row.get('author_name', '未知分析师')
            rating = row.get('rating', '无评级')
            title = row.get('report_title', '无标题')[:30] if pd.notna(row.get('report_title')) else '无标题'
            report_date = row.get('report_date', '')
            print(f"  {i}. [{org}] {rating} - {title}...")
            print(f"     分析师: {author} | 日期: {report_date}")
        
        # 目标价一致性（如果有数据）
        if 'max_price' in reports.columns:
            targets = reports[reports['max_price'].notna()]['max_price'].astype(float)
            if len(targets) >= 2:
                avg_target = targets.mean()
                std_target = targets.std()
                cv = std_target / avg_target if avg_target > 0 else 0  # 变异系数
                
                print(f"\n【目标价分析】")
                print(f"  平均目标价: {avg_target:.2f} 元")
                print(f"  目标价区间: {targets.min():.2f} - {targets.max():.2f} 元")
                if cv < 0.1:
                    consistency = "高度一致 ✅"
                elif cv < 0.2:
                    consistency = "较为一致 ✓"
                else:
                    consistency = "分歧较大 ⚠️"
                print(f"  一致性: {consistency}")
        
    except Exception as e:
        print(f"  机构情绪分析失败: {e}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 sentiment_analysis.py <股票代码> [日期YYYYMMDD]")
        print("示例: python3 sentiment_analysis.py 000001.SZ")
        print("      python3 sentiment_analysis.py 600519.SH 20260302")
        sys.exit(1)
    
    ts_code = sys.argv[1]
    trade_date = sys.argv[2] if len(sys.argv) > 2 else None
    
    # 分析市场情绪
    analyze_market_sentiment(trade_date)
    
    # 分析板块情绪
    analyze_sector_sentiment(trade_date)
    
    # 分析同行业对比
    analyze_industry_stocks(ts_code)
    
    # 分析机构情绪
    analyze_institution_sentiment(ts_code)
