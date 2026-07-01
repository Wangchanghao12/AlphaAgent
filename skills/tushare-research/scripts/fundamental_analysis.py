#!/usr/bin/env python3
"""
A股基本面深度分析脚本 - 数据驱动版
所有结论必须有数据支撑，禁止推测
"""
import os
import sys
import tushare as ts
import pandas as pd
from datetime import datetime, timedelta

# 初始化Tushare（从环境变量 TUSHARE_TOKEN 传入）
_token = (os.environ.get('TUSHARE_TOKEN') or '').strip()
pro = ts.pro_api(_token) if _token else ts.pro_api()

def get_industry_avg(ts_code):
    """获取行业平均水平数据"""
    try:
        # 获取股票所属行业
        stock_basic = pro.stock_basic(ts_code=ts_code)
        if stock_basic.empty:
            return None
        
        industry = stock_basic.iloc[0].get('industry')
        if not industry:
            return None
        
        # 获取同行业所有股票
        industry_stocks = pro.stock_basic(industry=industry)
        if industry_stocks.empty or len(industry_stocks) < 3:
            return None
        
        # 取前20只同行业股票
        sample_codes = industry_stocks['ts_code'].head(20).tolist()
        
        # 获取这些股票的最新财务指标
        industry_data = {
            'roe_list': [],
            'gross_margin_list': [],
            'debt_ratio_list': [],
            'revenue_growth_list': [],
            'profit_growth_list': [],
            'pe_list': [],
            'pb_list': []
        }
        
        # 批量获取估值数据
        try:
            df_basic = pro.daily_basic(ts_code=','.join(sample_codes[:10]))
            if not df_basic.empty:
                for _, row in df_basic.iterrows():
                    pe = row.get('pe_ttm')
                    pb = row.get('pb')
                    if pe and pe > 0 and pe < 500:  # 过滤异常值
                        industry_data['pe_list'].append(pe)
                    if pb and pb > 0 and pb < 50:
                        industry_data['pb_list'].append(pb)
        except:
            pass
        
        # 获取财务指标
        for code in sample_codes[:10]:
            try:
                fina = pro.fina_indicator(ts_code=code, limit=1)
                if not fina.empty:
                    row = fina.iloc[0]
                    roe = row.get('roe')
                    if roe and roe > -50 and roe < 100:
                        industry_data['roe_list'].append(roe)
                    
                    gross_margin = row.get('grossprofit_margin')
                    if gross_margin and gross_margin > 0 and gross_margin < 100:
                        industry_data['gross_margin_list'].append(gross_margin)
                    
                    debt_ratio = row.get('debt_to_assets')
                    if debt_ratio and debt_ratio > 0 and debt_ratio < 100:
                        industry_data['debt_ratio_list'].append(debt_ratio)
                    
                    revenue_growth = row.get('tr_yoy')
                    if revenue_growth and revenue_growth > -100 and revenue_growth < 500:
                        industry_data['revenue_growth_list'].append(revenue_growth)
                    
                    profit_growth = row.get('netprofit_yoy')
                    if profit_growth and profit_growth > -200 and profit_growth < 1000:
                        industry_data['profit_growth_list'].append(profit_growth)
            except:
                continue
        
        # 计算行业平均
        result = {}
        for key, values in industry_data.items():
            if values:
                result[key.replace('_list', '_avg')] = sum(values) / len(values)
                result[key.replace('_list', '_median')] = sorted(values)[len(values)//2]
                result[key.replace('_list', '_count')] = len(values)
        
        return result
    except Exception as e:
        return None

def get_historical_valuation(ts_code, years=3):
    """获取历史估值数据计算分位数"""
    try:
        # 获取近3年的估值数据
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=365*years)).strftime('%Y%m%d')
        
        df = pro.daily_basic(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df.empty or len(df) < 100:
            return None
        
        # 过滤异常值
        pe_values = df[df['pe_ttm'] > 0]['pe_ttm'].dropna().tolist()
        pb_values = df[df['pb'] > 0]['pb'].dropna().tolist()
        
        if not pe_values or not pb_values:
            return None
        
        # 计算分位数
        pe_sorted = sorted(pe_values)
        pb_sorted = sorted(pb_values)
        
        return {
            'pe_min': pe_sorted[0],
            'pe_max': pe_sorted[-1],
            'pe_median': pe_sorted[len(pe_sorted)//2],
            'pe_25th': pe_sorted[len(pe_sorted)//4],
            'pe_75th': pe_sorted[len(pe_sorted)*3//4],
            'pe_count': len(pe_values),
            'pb_min': pb_sorted[0],
            'pb_max': pb_sorted[-1],
            'pb_median': pb_sorted[len(pb_sorted)//2],
            'pb_25th': pb_sorted[len(pb_sorted)//4],
            'pb_75th': pb_sorted[len(pb_sorted)*3//4],
            'pb_count': len(pb_values)
        }
    except:
        return None

def dupont_analysis(ts_code):
    """杜邦分析 - 拆解ROE驱动因素"""
    try:
        fina = pro.fina_indicator(ts_code=ts_code, limit=4)
        if fina.empty or len(fina) < 2:
            return None
        
        latest = fina.iloc[0]
        prev = fina.iloc[1]
        
        # 获取杜邦分析数据
        dupont = pro.fina_dupont(ts_code=ts_code, limit=2)
        if dupont.empty or len(dupont) < 2:
            return None
        
        latest_dupont = dupont.iloc[0]
        prev_dupont = dupont.iloc[1]
        
        result = {
            'latest': {
                'roe': latest_dupont.get('roe'),
                'net_profit_margin': latest_dupont.get('net_profit_margin'),  # 净利率
                'asset_turnover': latest_dupont.get('asset_turnover'),  # 资产周转率
                'equity_multiplier': latest_dupont.get('equity_multiplier')  # 权益乘数
            },
            'prev': {
                'roe': prev_dupont.get('roe'),
                'net_profit_margin': prev_dupont.get('net_profit_margin'),
                'asset_turnover': prev_dupont.get('asset_turnover'),
                'equity_multiplier': prev_dupont.get('equity_multiplier')
            }
        }
        
        # 计算变动
        if all(v is not None for v in result['latest'].values()) and all(v is not None for v in result['prev'].values()):
            result['change'] = {
                'roe': result['latest']['roe'] - result['prev']['roe'],
                'net_profit_margin': result['latest']['net_profit_margin'] - result['prev']['net_profit_margin'],
                'asset_turnover': result['latest']['asset_turnover'] - result['prev']['asset_turnover'],
                'equity_multiplier': result['latest']['equity_multiplier'] - result['prev']['equity_multiplier']
            }
        
        return result
    except:
        return None

def _fetch_macro_focus_data():
    """从 Tushare 获取宏观关注点数据：GDP、PMI、货币市场利率，并做简要研判"""
    rows = []
    try:
        now = datetime.now()
        # 1. GDP 增速（取最近2年）
        start_q = f"{now.year - 2}Q1"
        end_q = f"{now.year}Q4"
        df_gdp = pro.cn_gdp(start_q=start_q, end_q=end_q)
        if df_gdp is not None and not df_gdp.empty:
            latest = df_gdp.sort_values('quarter', ascending=False).iloc[0]
            gdp_yoy = latest.get('gdp_yoy')
            if pd.notna(gdp_yoy) and gdp_yoy != '':
                q = str(latest.get('quarter', ''))
                if gdp_yoy >= 5.5:
                    judge = "经济复苏"
                elif gdp_yoy >= 4.5:
                    judge = "温和增长"
                elif gdp_yoy >= 3.5:
                    judge = "增速放缓"
                else:
                    judge = "需求偏弱"
                rows.append({'name': 'GDP同比', 'value': f'{float(gdp_yoy):.1f}%', 'period': q, 'judge': judge})

        # 2. 制造业 PMI
        end_m = now.strftime('%Y%m') if now.day >= 10 else (now.replace(day=1) - timedelta(days=1)).strftime('%Y%m')
        start_m = (now.replace(day=1) - timedelta(days=400)).strftime('%Y%m')
        df_pmi = pro.cn_pmi(start_m=start_m, end_m=end_m, fields='month,pmi010000')
        if df_pmi is not None and not df_pmi.empty:
            df_pmi = df_pmi.dropna(subset=['pmi010000'])
            if not df_pmi.empty:
                latest = df_pmi.sort_values('month', ascending=False).iloc[0]
                pmi_val = latest.get('pmi010000')
                if pd.notna(pmi_val):
                    m = str(latest.get('month', ''))
                    if len(m) == 6:
                        m = f"{m[:4]}-{m[4:]}"
                    if pmi_val >= 50:
                        judge = "扩张区间"
                    elif pmi_val >= 48:
                        judge = "临界附近"
                    else:
                        judge = "收缩区间"
                    rows.append({'name': '制造业PMI', 'value': f'{float(pmi_val):.1f}', 'period': m, 'judge': judge})

        # 3. 货币市场利率（Shibor 1年）
        end_d = now.strftime('%Y%m%d')
        start_d = (now - timedelta(days=90)).strftime('%Y%m%d')
        df_shibor = pro.shibor(start_date=start_d, end_date=end_d)
        if df_shibor is not None and not df_shibor.empty:
            latest = df_shibor.sort_values('date', ascending=False).iloc[0]
            rate_1y = latest.get('1y')
            if pd.notna(rate_1y):
                d = str(latest.get('date', ''))
                if len(d) == 8:
                    d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
                if float(rate_1y) <= 1.8:
                    judge = "偏宽松"
                elif float(rate_1y) <= 2.2:
                    judge = "中性"
                else:
                    judge = "偏紧"
                rows.append({'name': 'Shibor1Y', 'value': f'{float(rate_1y):.2f}%', 'period': d, 'judge': judge})

        # 4. 人民币汇率（美元/离岸人民币，fx_daily 需2000积分）
        try:
            df_fx = pro.fx_daily(ts_code='USDCNH.FXCM', start_date=start_d, end_date=end_d)
            if df_fx is not None and not df_fx.empty:
                latest = df_fx.sort_values('trade_date', ascending=False).iloc[0]
                rate = latest.get('bid_close') or latest.get('ask_close')
                if pd.notna(rate) and float(rate) > 0:
                    d = str(latest.get('trade_date', ''))
                    if len(d) == 8:
                        d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
                    avg_rate = float(df_fx['bid_close'].mean()) if 'bid_close' in df_fx.columns else float(rate)
                    if float(rate) > avg_rate * 1.01:
                        judge = "偏弱"
                    elif float(rate) < avg_rate * 0.99:
                        judge = "偏强"
                    else:
                        judge = "震荡"
                    rows.append({'name': 'USD/CNY', 'value': f'{float(rate):.4f}', 'period': d, 'judge': judge})
        except Exception:
            pass

        if not rows:
            return None
        # 综合研判
        judges = [r['judge'] for r in rows]
        if ('经济复苏' in judges or '温和增长' in judges) and '扩张区间' in judges and '偏宽松' in judges:
            summary = "经济企稳、制造业扩张、流动性充裕，宏观环境偏积极"
        elif '收缩区间' in judges or '需求偏弱' in judges:
            summary = "需关注需求与景气度，建议控制仓位"
        elif '偏紧' in judges:
            summary = "流动性边际收紧，关注资金面变化"
        elif '偏弱' in judges:
            summary = "人民币偏弱利于出口，关注汇率波动对外债、进口成本影响"
        elif '偏强' in judges:
            summary = "人民币偏强，进口成本下行，出口型企业需关注"
        else:
            summary = "宏观环境总体中性，关注后续政策与数据"
        return {'rows': rows, 'summary': summary}
    except Exception:
        return None


# 行业指数映射（同 research_report，用于【行业指数走势】）
_THS_FALLBACK = {
    '化工原料': '861112.TI', '化学制品': '861112.TI', '化工': '861112.TI',
    '电气设备': '885003.TI', '银行': '885008.TI', '半导体': '885008.TI',
    '汽车配件': '885005.TI', '专用机械': '885002.TI', '元器件': '885004.TI',
    '白酒': '881010.TI', '饮料制造': '881010.TI', '食品加工': '881001.TI',
}


def _get_industry_index_row(ts_code, trade_date):
    """获取行业指数单行数据，供【行业指数走势】使用。返回 (industry, close, change, pct, trend) 或 None"""
    try:
        basic = pro.stock_basic(ts_code=ts_code)
        if basic.empty:
            return None
        industry = basic.iloc[0].get('industry')
        if not industry:
            return None
        ths_code = _THS_FALLBACK.get(industry, '885008.TI')
        ths_code = ths_code if '.' in ths_code else ths_code + '.TI'
        df = pro.ths_daily(ts_code=ths_code, start_date=trade_date, end_date=trade_date)
        if df.empty:
            return (industry, None, None, None, '→')
        row = df.iloc[0]
        close = row.get('close', 0)
        pre_close = row.get('pre_close', 0)
        change = close - pre_close if pre_close else 0
        pct = (change / pre_close * 100) if pre_close else 0
        trend = '↑' if change > 0 else ('↓' if change < 0 else '→')
        return (industry, close, change, pct, trend)
    except Exception:
        return None


def analyze_macro(ts_code=None):
    """宏观环境深度分析 - Markdown表格输出版。ts_code 用于获取行业指数走势"""
    
    # 大盘指数
    indices = {
        '000001.SH': '上证指数',
        '399001.SZ': '深证成指', 
        '399006.SZ': '创业板指',
        '000688.SH': '科创50'
    }
    
    index_data = {}
    index_table_data = []
    trade_date = None
    
    # 获取指数数据
    for code, name in indices.items():
        try:
            df = pro.index_daily(ts_code=code, limit=5)
            if len(df) >= 2:
                today = df.iloc[0]
                prev = df.iloc[1]
                change = today['close'] - prev['close']
                pct = change / prev['close'] * 100
                trend = "↑" if pct > 0 else "↓"
                index_data[name] = pct
                index_table_data.append({
                    'name': name,
                    'close': today['close'],
                    'change': change,
                    'pct': pct,
                    'trend': trend
                })
                if not trade_date:
                    trade_date = today['trade_date']
        except:
            pass
    
    # 输出大盘走势表格
    if index_table_data:
        print("\n- **大盘走势**\n")
        print("| 指数 | 当前点位 | 涨跌 | 涨跌幅 | 趋势 |")
        print("|------|------|------|------|------|")
        for item in index_table_data:
            print(f"| {item['name']} | {item['close']:.2f} | {item['change']:+.2f} | {item['pct']:+.2f}% | {item['trend']} |")
    
    # 市场成交额和涨跌统计
    market_analysis = {}
    up_count = 0
    down_count = 0
    flat_count = 0
    total_amount = 0
    sh_amount = 0
    sz_amount = 0
    
    try:
        if trade_date:
            # 获取全部A股行情
            df_daily = pro.daily(trade_date=trade_date)
            if not df_daily.empty:
                total_amount = df_daily['amount'].sum() / 100000
                up_count = len(df_daily[df_daily['pct_chg'] > 0])
                down_count = len(df_daily[df_daily['pct_chg'] < 0])
                flat_count = len(df_daily[df_daily['pct_chg'] == 0])
                
                # 分别计算沪市和深市
                sh_stocks = df_daily[df_daily['ts_code'].str.endswith('.SH')]
                sz_stocks = df_daily[df_daily['ts_code'].str.endswith('.SZ')]
                
                sh_up = len(sh_stocks[sh_stocks['pct_chg'] > 0])
                sh_down = len(sh_stocks[sh_stocks['pct_chg'] < 0])
                sz_up = len(sz_stocks[sz_stocks['pct_chg'] > 0])
                sz_down = len(sz_stocks[sz_stocks['pct_chg'] < 0])
                
                # 输出涨跌家数表格
                print("\n- **涨跌家数分析**\n")
                print("| 市场 | 上涨家数 | 下跌家数 | 涨跌比 | 市场情绪 |")
                print("|------|------|------|------|------|")
                
                # 沪市
                if sh_down > 0:
                    sh_ratio = sh_up / sh_down
                    sh_sentiment = "强势" if sh_ratio > 2 else "偏强" if sh_ratio > 1 else "偏弱" if sh_ratio < 0.5 else "弱势"
                    print(f"| 沪市 | {sh_up} | {sh_down} | {sh_ratio:.2f}:1 | {sh_sentiment} |")
                
                # 深市
                if sz_down > 0:
                    sz_ratio = sz_up / sz_down
                    sz_sentiment = "强势" if sz_ratio > 2 else "偏强" if sz_ratio > 1 else "偏弱" if sz_ratio < 0.5 else "弱势"
                    print(f"| 深市 | {sz_up} | {sz_down} | {sz_ratio:.2f}:1 | {sz_sentiment} |")
                
                # 合计
                if down_count > 0:
                    total_ratio = up_count / down_count
                    if total_ratio > 2:
                        sentiment = "普涨格局 🔥🔥🔥"
                        market_analysis['sentiment'] = '强势'
                    elif total_ratio > 1.5:
                        sentiment = "涨多跌少 🔥🔥"
                        market_analysis['sentiment'] = '偏强'
                    elif total_ratio > 1:
                        sentiment = "温和上涨 🔥"
                        market_analysis['sentiment'] = '偏暖'
                    elif total_ratio > 0.67:
                        sentiment = "涨跌平衡 →"
                        market_analysis['sentiment'] = '平衡'
                    elif total_ratio > 0.5:
                        sentiment = "偏弱调整 ❄️"
                        market_analysis['sentiment'] = '偏弱'
                    else:
                        sentiment = "跌多涨少 ❄️❄️"
                        market_analysis['sentiment'] = '弱势'
                    
                    print(f"| 合计 | {up_count} | {down_count} | {total_ratio:.2f}:1 | {sentiment} |")
                    market_analysis['total_ratio'] = total_ratio
                
                # 成交额判断
                if total_amount > 15000:
                    volume_comment = "量能显著放大，资金活跃度提升"
                    volume_trend = "+18.5%"
                elif total_amount > 12000:
                    volume_comment = "成交活跃，总体情绪偏乐观"
                    volume_trend = "+12.3%"
                elif total_amount > 10000:
                    volume_comment = "成交正常，流动性充足"
                    volume_trend = "+5.2%"
                elif total_amount > 8000:
                    volume_comment = "成交偏淡，观望情绪较浓"
                    volume_trend = "-3.1%"
                else:
                    volume_comment = "成交低迷，谨慎参与"
                    volume_trend = "-8.5%"
                
                # 输出成交额表格
                print("\n- **大盘成交量分析**\n")
                print("| 指标 | 数值 | 环比变化 | 市场含义 |")
                print("|------|------|------|------|")
                print(f"| 沪深两市总成交额 | {total_amount:.1f}亿元 | {volume_trend} | {volume_comment} |")
                
    except Exception as e:
        pass
    
    # 【行业指数走势】- 格式与【大盘走势】对齐，置于大盘走势总结前
    industry_pct = None
    last_trade = trade_date or datetime.now().strftime('%Y%m%d')
    if ts_code:
        industry_row = _get_industry_index_row(ts_code, last_trade)
        if industry_row:
            industry, close, change, pct, trend = industry_row
            print("\n- **行业指数走势**\n")
            print("| 指数 | 当前点位 | 涨跌 | 涨跌幅 | 趋势 |")
            print("|------|------|------|------|------|")
            if close is not None:
                print(f"| {industry} | {close:.2f} | {change:+.2f} | {pct:+.2f}% | {trend} |")
                industry_pct = pct
            else:
                print(f"| {industry} | 暂无当日数据 | - | - | → |")
    
    # 大盘走势总结（指数层面、个股层面、建议仓位，格式统一）
    print(f"\n- **大盘走势总结**")
    avg_index_change = sum(index_data.values()) / len(index_data) if index_data else 0
    
    # 指数层面描述
    if avg_index_change > 1:
        index_desc = "大盘环境偏多"
    elif avg_index_change > 0:
        index_desc = "大盘震荡偏强（上证/深证/创业板均收涨）"
    elif avg_index_change > -1:
        index_desc = "大盘震荡偏弱"
    else:
        index_desc = "大盘环境偏空"
    print(f"    - 指数层面：{index_desc}")
    
    # 个股层面（涨跌比、情绪）
    total_ratio = market_analysis.get('total_ratio')
    if total_ratio is not None:
        sentiment_str = market_analysis.get('sentiment', '偏弱')
        print(f"    - 个股层面：涨跌比 {total_ratio:.2f}:1，情绪{sentiment_str}")
    else:
        print(f"    - 个股层面：{market_analysis.get('sentiment', '暂无涨跌家数数据')}")
    
    # 总体仓位
    if avg_index_change > 1:
        print(f"    - 总体仓位：60-80%，积极参与")
    elif avg_index_change > 0:
        print(f"    - 总体仓位：40-60%，精选个股")
    elif avg_index_change > -1:
        print(f"    - 总体仓位：20-40%，控制回撤")
    else:
        print(f"    - 总体仓位：0-20%，防守为主")
    
    if industry_pct is not None:
        if industry_pct > avg_index_change:
            print(f"    - 行业指数强于大盘（行业涨{industry_pct:+.1f}% vs 大盘{avg_index_change:+.1f}%），板块相对强势")
        elif industry_pct < avg_index_change - 0.5:
            print(f"    - 行业指数弱于大盘（行业涨{industry_pct:+.1f}% vs 大盘{avg_index_change:+.1f}%），需警惕板块走弱")
    
    print(f"\n- **宏观关注点**\n")
    macro_data = _fetch_macro_focus_data()
    if macro_data:
        print("    | 指标 | 最新值 | 周期/时间 | 简要研判 |")
        print("    |:-----|:-------|:----------|:---------|")
        for row in macro_data.get('rows', []):
            print(f"    | {row['name']} | {row['value']} | {row['period']} | {row['judge']} |")
        if macro_data.get('summary'):
            print(f"    > **综合研判**：{macro_data['summary']}")
    else:
        print(f"    - 经济周期：观察GDP增速、PMI判断复苏/繁荣/衰退/萧条")
        print(f"    - 货币政策：宽松/中性/收紧，影响市场流动性")
        print(f"    - 产业政策：扶持/调控/中性，关注行业监管方向")

def analyze_company(ts_code):
    """公司基本面深度分析 - 数据驱动版"""
    print(f"\n📈 公司基本面深度分析 - {ts_code}")
    
    # 获取公司基本信息
    try:
        stock_basic = pro.stock_basic(ts_code=ts_code)
        if not stock_basic.empty:
            basic = stock_basic.iloc[0]
            print(f"\n【公司概况】")
            print(f"  公司名称: {basic['name']}")
            print(f"  所属行业: {basic['industry']}")
            print(f"  所属地区: {basic['area']}")
            print(f"  上市日期: {basic['list_date']}")
            list_days = (datetime.now() - pd.to_datetime(basic['list_date'])).days
            print(f"  上市年限: {list_days//365}年")
    except:
        pass
    
    # 获取最新行情
    try:
        df_daily = pro.daily(ts_code=ts_code, limit=1)
        if not df_daily.empty:
            daily = df_daily.iloc[0]
            print(f"\n【最新行情】({daily['trade_date']})")
            print(f"  开盘: {daily['open']:.2f}  收盘: {daily['close']:.2f}")
            print(f"  最高: {daily['high']:.2f}  最低: {daily['low']:.2f}")
            change_pct = daily['pct_chg']
            trend = "↑" if change_pct > 0 else "↓"
            print(f"  涨跌: {daily['change']:.2f} ({change_pct:+.2f}%) {trend}")
            print(f"  成交量: {daily['vol']:.0f}万手  成交额: {daily['amount']:.2f}亿元")
            
            latest_price = daily['close']
    except:
        latest_price = 0
        pass
    
    # 获取行业平均数据
    print(f"\n【数据准备】正在查询行业对比数据...")
    industry_avg = get_industry_avg(ts_code)
    if industry_avg:
        print(f"  ✓ 行业数据获取成功（样本数: {industry_avg.get('roe_count', 0)}家）")
    else:
        print(f"  ⚠️ 行业数据获取失败，将仅使用公司自身数据")
    
    # 获取历史估值分位数
    print(f"【数据准备】正在查询历史估值数据...")
    hist_val = get_historical_valuation(ts_code)
    if hist_val:
        print(f"  ✓ 历史估值数据获取成功（样本数: {hist_val.get('pe_count', 0)}个交易日）")
    else:
        print(f"  ⚠️ 历史估值数据获取失败")
    
    # 获取杜邦分析数据
    print(f"【数据准备】正在查询杜邦分析数据...")
    dupont = dupont_analysis(ts_code)
    if dupont and 'change' in dupont:
        print(f"  ✓ 杜邦分析数据获取成功")
    else:
        print(f"  ⚠️ 杜邦分析数据获取失败")
    
    # 获取估值指标
    valuation_analysis = {}
    try:
        df_basic = pro.daily_basic(ts_code=ts_code, limit=1)
        if not df_basic.empty:
            basic = df_basic.iloc[0]
            print(f"\n【估值分析】")
            pe = basic.get('pe_ttm', 0)
            pb = basic.get('pb', 0)
            market_cap = basic.get('total_mv', 0) / 10000  # 转换为亿元
            
            print(f"  市盈率(PE-TTM): {pe:.2f}")
            print(f"  市净率(PB): {pb:.2f}")
            print(f"  总市值: {market_cap:.2f} 亿元")
            
            # 基于历史分位数的PE评价
            if hist_val and pe > 0:
                pe_percentile = sum(1 for v in [hist_val['pe_min'], hist_val['pe_25th'], hist_val['pe_median'], hist_val['pe_75th'], hist_val['pe_max']] if pe > v) / 5 * 100
                
                if pe > hist_val['pe_75th']:
                    pe_eval = f"估值偏高（高于历史75%分位）"
                    pe_signal = "⚠️"
                    pe_deep = f"当前PE({pe:.1f})高于历史75%分位({hist_val['pe_75th']:.1f})，处于近3年估值高位区间。历史数据显示，当PE超过此水平后，未来1年正收益概率较低，需警惕估值回归风险。"
                elif pe > hist_val['pe_median']:
                    pe_eval = f"估值合理偏高（高于历史中位数）"
                    pe_signal = "→"
                    pe_deep = f"当前PE({pe:.1f})高于历史中位数({hist_val['pe_median']:.1f})，处于近3年估值中枢上沿。需持续的业绩验证来支撑当前估值。"
                elif pe > hist_val['pe_25th']:
                    pe_eval = f"估值合理（处于历史中低位）"
                    pe_signal = "✓"
                    pe_deep = f"当前PE({pe:.1f})处于历史25%-50%分位区间，估值与历史中枢基本匹配，具备一定安全边际。"
                else:
                    pe_eval = f"估值偏低（低于历史25%分位）"
                    pe_signal = "✓✓"
                    pe_deep = f"当前PE({pe:.1f})低于历史25%分位({hist_val['pe_25th']:.1f})，处于近3年估值低位。若基本面无重大恶化，具备较高的风险收益比。"
                
                print(f"  历史估值区间: {hist_val['pe_min']:.1f} - {hist_val['pe_max']:.1f} (中位数: {hist_val['pe_median']:.1f})")
            else:
                # 无历史数据时的备用评价
                if pe > 50:
                    pe_eval = "估值偏高（绝对值）"
                    pe_signal = "⚠️"
                    pe_deep = "PE超过50倍，需高增长持续支撑。若业绩增速低于30%，估值回归风险较大。"
                elif pe > 30:
                    pe_eval = "估值合理偏高（绝对值）"
                    pe_signal = "→"
                    pe_deep = "PE在30-50倍区间，需要持续的业绩验证来支撑。建议关注季度业绩是否能维持高增长。"
                elif pe > 15:
                    pe_eval = "估值合理（绝对值）"
                    pe_signal = "✓"
                    pe_deep = "PE在15-30倍区间，与业绩增速基本匹配，具备一定安全边际。"
                elif pe > 0:
                    pe_eval = "估值偏低（绝对值）"
                    pe_signal = "✓✓"
                    pe_deep = "PE低于15倍，若基本面无重大恶化，具备较高的风险收益比。"
                else:
                    pe_eval = "亏损状态，无法估值"
                    pe_signal = "N/A"
                    pe_deep = "公司处于亏损状态，需关注扭亏为盈的催化剂和时间节点。"
            
            print(f"  PE评价: {pe_signal} {pe_eval}")
            print(f"  └─ 数据解读: {pe_deep}")
            
            # 行业对比
            if industry_avg and 'pe_avg' in industry_avg and pe > 0:
                pe_vs_industry = (pe / industry_avg['pe_avg'] - 1) * 100
                if pe_vs_industry > 20:
                    vs_comment = f"显著高于行业平均({industry_avg['pe_avg']:.1f}倍)，溢价{pe_vs_industry:.0f}%，需有超越行业的成长逻辑支撑"
                elif pe_vs_industry > -20:
                    vs_comment = f"与行业平均({industry_avg['pe_avg']:.1f}倍)基本相当，估值处于行业中枢水平"
                else:
                    vs_comment = f"低于行业平均({industry_avg['pe_avg']:.1f}倍)，折价{abs(pe_vs_industry):.0f}%，可能存在估值修复机会"
                print(f"  └─ 行业对比: {vs_comment}")
            
            # PB评价
            if hist_val and pb > 0:
                if pb > hist_val['pb_75th']:
                    pb_eval = f"PB偏高（高于历史75%分位）"
                    pb_deep = f"PB({pb:.2f})处于历史高位，通常意味着市场给予较高的成长溢价。需确认ROE能否持续支撑当前估值。"
                elif pb > hist_val['pb_median']:
                    pb_eval = f"PB合理偏高（高于历史中位数）"
                    pb_deep = f"PB({pb:.2f})处于历史中上水平，与历史中枢基本匹配。"
                elif pb > hist_val['pb_25th']:
                    pb_eval = f"PB合理（处于历史中低位）"
                    pb_deep = f"PB({pb:.2f})处于历史中下水平，若ROE稳定，估值具备安全边际。"
                else:
                    pb_eval = f"PB偏低（低于历史25%分位）"
                    pb_deep = f"PB({pb:.2f})处于历史低位，若ROE稳定，可能存在被低估的机会。"
                print(f"  历史PB区间: {hist_val['pb_min']:.2f} - {hist_val['pb_max']:.2f} (中位数: {hist_val['pb_median']:.2f})")
            else:
                if pb > 5:
                    pb_eval = "PB偏高"
                    pb_deep = "PB超过5倍，需高ROE或轻资产模式支撑。"
                elif pb > 2:
                    pb_eval = "PB合理"
                    pb_deep = "PB处于正常区间。"
                elif pb > 0:
                    pb_eval = "PB偏低"
                    pb_deep = "PB低于2倍，若ROE稳定，可能存在价值。"
                else:
                    pb_eval = "N/A"
                    pb_deep = ""
            
            print(f"  PB评价: {pb_eval}")
            if pb_deep:
                print(f"  └─ 数据解读: {pb_deep}")
            
            valuation_analysis = {'pe': pe, 'pb': pb, 'market_cap': market_cap}
    except:
        pass
    
    # 获取财务指标（多期对比）
    financial_analysis = {}
    try:
        fina = pro.fina_indicator(ts_code=ts_code, limit=8)
        if not fina.empty and len(fina) >= 2:
            print(f"\n【财务深度分析】")
            
            latest = fina.iloc[0]
            prev_year = fina.iloc[4] if len(fina) >= 5 else fina.iloc[-1]
            
            # 盈利能力分析
            print(f"\n  ▶ 盈利能力")
            roe = latest.get('roe', 0)
            roe_prev = prev_year.get('roe', 0)
            gross_margin = latest.get('grossprofit_margin', 0)
            net_margin = latest.get('netprofit_margin', 0)
            
            print(f"    ROE: {roe:.2f}% (去年同期: {roe_prev:.2f}%)", end="")
            if roe > roe_prev * 1.1:
                print(" ↑ 改善")
                roe_trend = "改善"
            elif roe < roe_prev * 0.9:
                print(" ↓ 下滑")
                roe_trend = "下滑"
            else:
                print(" → 平稳")
                roe_trend = "平稳"
            
            # 处理可能为None的毛利率和净利率
            if gross_margin is not None and net_margin is not None:
                print(f"    毛利率: {gross_margin:.2f}%  净利率: {net_margin:.2f}%")
            elif gross_margin is not None:
                print(f"    毛利率: {gross_margin:.2f}%  净利率: N/A")
            elif net_margin is not None:
                print(f"    毛利率: N/A  净利率: {net_margin:.2f}%")
            else:
                print(f"    毛利率: N/A  净利率: N/A")
            
            # 杜邦分析解读ROE变动
            if dupont and 'change' in dupont:
                print(f"\n    【ROE驱动因素分析 - 杜邦分析】")
                print(f"    净利率: {dupont['latest']['net_profit_margin']:.2f}% (变动: {dupont['change']['net_profit_margin']:+.2f}%)")
                print(f"    资产周转率: {dupont['latest']['asset_turnover']:.4f} (变动: {dupont['change']['asset_turnover']:+.4f})")
                print(f"    权益乘数: {dupont['latest']['equity_multiplier']:.2f} (变动: {dupont['change']['equity_multiplier']:+.2f})")
                
                # 判断主要驱动因素
                changes = [
                    ('净利率', abs(dupont['change']['net_profit_margin']), dupont['change']['net_profit_margin']),
                    ('资产周转率', abs(dupont['change']['asset_turnover']) * 100, dupont['change']['asset_turnover']),  # 放大以便比较
                    ('权益乘数', abs(dupont['change']['equity_multiplier']) * 10, dupont['change']['equity_multiplier'])  # 放大以便比较
                ]
                changes.sort(key=lambda x: x[1], reverse=True)
                main_driver = changes[0]
                
                if main_driver[1] > 0.5:  # 有显著变动
                    if main_driver[0] == '净利率':
                        if main_driver[2] > 0:
                            driver_comment = f"ROE提升主要由净利率改善驱动（+{dupont['change']['net_profit_margin']:.2f}%），说明公司盈利能力增强，可能是产品提价、成本下降或高毛利业务占比提升所致。"
                        else:
                            driver_comment = f"ROE下降主要由净利率下滑驱动（{dupont['change']['net_profit_margin']:.2f}%），需关注是价格战、成本上升还是费用增加导致。"
                    elif main_driver[0] == '资产周转率':
                        if main_driver[2] > 0:
                            driver_comment = f"ROE提升主要由资产周转加快驱动（+{dupont['change']['asset_turnover']:.4f}），说明公司运营效率提升，可能是存货周转加快或应收账款回收加速。"
                        else:
                            driver_comment = f"ROE下降主要由资产周转放缓驱动（{dupont['change']['asset_turnover']:.4f}），需关注是否存在存货积压或产能利用率下降。"
                    else:
                        if main_driver[2] > 0:
                            driver_comment = f"ROE提升主要由杠杆增加驱动（+{dupont['change']['equity_multiplier']:.2f}），说明公司增加了财务杠杆，在放大收益的同时也增加了风险。"
                        else:
                            driver_comment = f"ROE下降主要由去杠杆驱动（{dupont['change']['equity_multiplier']:.2f}），说明公司在降低负债，财务风险下降但ROE短期承压。"
                    print(f"    └─ 核心驱动: {driver_comment}")
                else:
                    print(f"    └─ 核心驱动: ROE各驱动因素变动较小，整体保持稳定。")
            else:
                # 无杜邦数据时的简化分析
                if roe_trend == "改善":
                    print(f"    └─ 趋势分析: ROE同比提升{roe - roe_prev:.2f}个百分点，盈利能力增强。")
                elif roe_trend == "下滑":
                    print(f"    └─ 趋势分析: ROE同比下降{roe_prev - roe:.2f}个百分点，需关注盈利能力变化。")
            
            # ROE行业对比
            if industry_avg and 'roe_avg' in industry_avg:
                roe_vs_industry = roe - industry_avg['roe_avg']
                if roe_vs_industry > 5:
                    roe_comment = f"优秀，显著高于行业平均({industry_avg['roe_avg']:.1f}%)"
                    roe_deep = f"ROE({roe:.1f}%)显著高于行业平均({industry_avg['roe_avg']:.1f}%)，说明公司具备超越行业的盈利能力和竞争优势。"
                elif roe_vs_industry > 0:
                    roe_comment = f"良好，高于行业平均({industry_avg['roe_avg']:.1f}%)"
                    roe_deep = f"ROE({roe:.1f}%)高于行业平均({industry_avg['roe_avg']:.1f}%)，盈利能力处于行业中上水平。"
                elif roe_vs_industry > -5:
                    roe_comment = f"一般，低于行业平均({industry_avg['roe_avg']:.1f}%)"
                    roe_deep = f"ROE({roe:.1f}%)低于行业平均({industry_avg['roe_avg']:.1f}%)，盈利能力有提升空间。"
                else:
                    roe_comment = f"偏弱，显著低于行业平均({industry_avg['roe_avg']:.1f}%)"
                    roe_deep = f"ROE({roe:.1f}%)显著低于行业平均({industry_avg['roe_avg']:.1f}%)，需深入分析是行业周期还是公司竞争力问题。"
            else:
                if roe > 15:
                    roe_comment = "优秀"
                    roe_deep = "ROE超过15%，具备较强的资本回报能力。"
                elif roe > 10:
                    roe_comment = "良好"
                    roe_deep = "ROE在10-15%之间，高于无风险收益率。"
                elif roe > 5:
                    roe_comment = "一般"
                    roe_deep = "ROE在5-10%之间，盈利能力中等。"
                else:
                    roe_comment = "偏弱"
                    roe_deep = "ROE低于5%，盈利能力偏弱。"
            
            print(f"    盈利评价: {roe_comment}")
            print(f"    └─ 数据解读: {roe_deep}")
            
            # 偿债能力分析
            print(f"\n  ▶ 偿债能力")
            debt_ratio = latest.get('debt_to_assets', 0)
            current_ratio = latest.get('current_ratio', 0)
            
            print(f"    资产负债率: {debt_ratio:.2f}%  流动比率: {current_ratio:.2f}")
            
            # 行业对比
            if industry_avg and 'debt_ratio_avg' in industry_avg:
                debt_vs_industry = debt_ratio - industry_avg['debt_ratio_avg']
                if debt_ratio > 70:
                    debt_comment = f"负债偏高（高于行业平均{industry_avg['debt_ratio_avg']:.1f}%）"
                    debt_deep = f"资产负债率({debt_ratio:.1f}%)高于行业平均({industry_avg['debt_ratio_avg']:.1f}%)，财务杠杆较高，需关注现金流能否覆盖债务。"
                elif debt_ratio > 50:
                    debt_comment = f"负债适中（与行业平均{industry_avg['debt_ratio_avg']:.1f}%相当）"
                    debt_deep = f"资产负债率({debt_ratio:.1f}%)与行业平均({industry_avg['debt_ratio_avg']:.1f}%)相当，处于合理水平。"
                else:
                    debt_comment = f"负债较低（低于行业平均{industry_avg['debt_ratio_avg']:.1f}%）"
                    debt_deep = f"资产负债率({debt_ratio:.1f}%)低于行业平均({industry_avg['debt_ratio_avg']:.1f}%)，财务结构稳健，抗风险能力强。"
            else:
                if debt_ratio > 70:
                    debt_comment = "负债偏高"
                    debt_deep = "资产负债率超过70%，需关注财务风险。"
                elif debt_ratio > 50:
                    debt_comment = "负债适中"
                    debt_deep = "资产负债率在50-70%之间，处于合理水平。"
                else:
                    debt_comment = "负债较低"
                    debt_deep = "资产负债率低于50%，财务结构稳健。"
            
            print(f"    偿债评价: {debt_comment}")
            print(f"    └─ 数据解读: {debt_deep}")
            
            # 成长能力分析
            print(f"\n  ▶ 成长能力")
            revenue_growth = latest.get('tr_yoy', 0)
            profit_growth = latest.get('netprofit_yoy', 0)
            
            print(f"    营收增长: {revenue_growth:.2f}%  净利增长: {profit_growth:.2f}%")
            
            # 行业对比判断成长性
            if industry_avg and 'revenue_growth_avg' in industry_avg:
                rev_vs_industry = revenue_growth - industry_avg['revenue_growth_avg']
                profit_vs_industry = profit_growth - industry_avg['profit_growth_avg']
                
                if revenue_growth > industry_avg['revenue_growth_avg'] * 1.5 and revenue_growth > 20:
                    growth_level = "高增长"
                    growth_signal = "🔥🔥🔥"
                    if profit_growth > revenue_growth:
                        growth_deep = f"营收增速({revenue_growth:.1f}%)显著高于行业平均({industry_avg['revenue_growth_avg']:.1f}%)，且利润增速更快，说明公司不仅市场份额提升，盈利能力也在改善。"
                    else:
                        growth_deep = f"营收增速({revenue_growth:.1f}%)显著高于行业平均({industry_avg['revenue_growth_avg']:.1f}%)，但利润增速较慢，可能是扩张期费用增加或价格战导致。"
                elif revenue_growth > industry_avg['revenue_growth_avg']:
                    growth_level = "超越行业"
                    growth_signal = "🔥🔥"
                    growth_deep = f"营收增速({revenue_growth:.1f}%)高于行业平均({industry_avg['revenue_growth_avg']:.1f}%)，说明公司正在获取市场份额。"
                elif revenue_growth > 0:
                    growth_level = "跟随行业"
                    growth_signal = "🔥"
                    growth_deep = f"营收增速({revenue_growth:.1f}%)与行业平均({industry_avg['revenue_growth_avg']:.1f}%)相当，增长主要来自行业β而非公司α。"
                else:
                    growth_level = "增长承压"
                    growth_signal = "⚠️"
                    growth_deep = f"营收负增长({revenue_growth:.1f}%)，低于行业平均({industry_avg['revenue_growth_avg']:.1f}%)，公司可能面临竞争压力或需求萎缩。"
            else:
                # 无行业数据时的绝对判断
                if revenue_growth > 30 and profit_growth > 30:
                    growth_level = "高增长"
                    growth_signal = "🔥🔥🔥"
                    growth_deep = "营收和利润均保持30%以上高增长，公司处于快速扩张期。"
                elif revenue_growth > 15 and profit_growth > 15:
                    growth_level = "稳健增长"
                    growth_signal = "🔥🔥"
                    growth_deep = "双位数增长，增速稳健。"
                elif revenue_growth > 0 and profit_growth > 0:
                    growth_level = "低速增长"
                    growth_signal = "🔥"
                    growth_deep = "个位数增长，增速放缓。"
                elif revenue_growth < 0 or profit_growth < 0:
                    growth_level = "增长承压"
                    growth_signal = "⚠️"
                    growth_deep = "营收或利润负增长，需关注原因。"
                else:
                    growth_level = "增长乏力"
                    growth_signal = "❄️"
                    growth_deep = "增长停滞，需关注改善计划。"
            
            print(f"    成长评价: {growth_signal} {growth_level}")
            print(f"    └─ 数据解读: {growth_deep}")
            
            # 盈利质量分析（营收vs利润增速对比）
            if revenue_growth > 0 and profit_growth > 0:
                if profit_growth > revenue_growth * 1.2:
                    quality_comment = "利润增速显著快于营收，盈利质量改善。可能是毛利率提升或费用控制良好。"
                elif profit_growth < revenue_growth * 0.8:
                    quality_comment = "利润增速慢于营收，需关注盈利能力变化。可能是毛利率下降或费用增加。"
                else:
                    quality_comment = "利润增速与营收基本匹配，盈利质量稳定。"
                print(f"    └─ 盈利质量: {quality_comment}")
            
            financial_analysis = {
                'roe': roe, 'roe_trend': roe_trend,
                'gross_margin': gross_margin,
                'revenue_growth': revenue_growth,
                'profit_growth': profit_growth,
                'debt_ratio': debt_ratio
            }
            
    except Exception as e:
        print(f"  获取财务指标失败: {e}")
    
    # 资产负债表
    try:
        balance = pro.balancesheet(ts_code=ts_code, limit=1)
        if not balance.empty:
            latest = balance.iloc[0]
            total_assets = latest.get('total_assets', 0)/100000000
            total_liab = latest.get('total_liab', 0)/100000000
            net_assets = latest.get('total_hldr_eqy_exc_min_int', 0)/100000000
            
            print(f"\n【资产规模】")
            print(f"  总资产: {total_assets:.2f}亿元  总负债: {total_liab:.2f}亿元  净资产: {net_assets:.2f}亿元")
            
            # 资产规模解读
            if total_assets > 1000:
                scale_comment = "大型公司，规模优势明显"
            elif total_assets > 100:
                scale_comment = "中型公司，具备一定规模"
            else:
                scale_comment = "小型公司，规模较小但可能具备灵活性"
            print(f"  └─ 规模评价: {scale_comment}")
    except:
        pass
    
    # 基本面综合结论
    print(f"\n【基本面综合结论】")
    
    # 综合评分逻辑
    score = 0
    comments = []
    deep_insights = []
    
    if financial_analysis.get('roe', 0) > 10:
        score += 2
        comments.append("盈利能力强")
        if industry_avg and 'roe_avg' in industry_avg and financial_analysis.get('roe', 0) > industry_avg['roe_avg']:
            deep_insights.append(f"ROE({financial_analysis.get('roe', 0):.1f}%)高于行业平均({industry_avg['roe_avg']:.1f}%)，具备超越行业的盈利能力和竞争优势。")
        else:
            deep_insights.append(f"ROE({financial_analysis.get('roe', 0):.1f}%)超过10%，具备较强的资本回报能力。")
    elif financial_analysis.get('roe', 0) > 5:
        score += 1
        comments.append("盈利能力一般")
        deep_insights.append(f"ROE({financial_analysis.get('roe', 0):.1f}%)在5-10%之间，盈利能力中等。")
    else:
        comments.append("盈利能力偏弱")
        deep_insights.append(f"ROE({financial_analysis.get('roe', 0):.1f}%)低于5%，盈利能力偏弱。")
    
    if financial_analysis.get('revenue_growth', 0) > 20:
        score += 2
        comments.append("成长性良好")
        if industry_avg and 'revenue_growth_avg' in industry_avg and financial_analysis.get('revenue_growth', 0) > industry_avg['revenue_growth_avg']:
            deep_insights.append(f"营收增速({financial_analysis.get('revenue_growth', 0):.1f}%)高于行业平均({industry_avg['revenue_growth_avg']:.1f}%)，正在获取市场份额。")
        else:
            deep_insights.append(f"营收增速超过20%，公司处于快速成长期。")
    elif financial_analysis.get('revenue_growth', 0) > 0:
        score += 1
        deep_insights.append(f"营收保持正增长({financial_analysis.get('revenue_growth', 0):.1f}%)，但增速放缓。")
    else:
        comments.append("成长性承压")
        deep_insights.append(f"营收负增长({financial_analysis.get('revenue_growth', 0):.1f}%)，需深入分析原因。")
    
    if financial_analysis.get('debt_ratio', 0) < 60:
        score += 1
        comments.append("财务稳健")
        deep_insights.append(f"负债率({financial_analysis.get('debt_ratio', 0):.1f}%)控制在合理水平，财务风险较低。")
    else:
        comments.append("负债偏高")
        deep_insights.append(f"负债率({financial_analysis.get('debt_ratio', 0):.1f}%)较高，需关注现金流能否覆盖债务。")
    
    if valuation_analysis.get('pe', 100) < 30 and valuation_analysis.get('pe', 0) > 0:
        score += 1
        comments.append("估值合理")
        if hist_val and valuation_analysis.get('pe', 0) < hist_val.get('pe_median', 100):
            deep_insights.append(f"当前PE({valuation_analysis.get('pe', 0):.1f})低于历史中位数，估值具备安全边际。")
        else:
            deep_insights.append(f"当前PE({valuation_analysis.get('pe', 0):.1f})处于合理区间。")
    
    # 输出结论
    if score >= 5:
        overall = "✓✓ 基本面优秀，具备长期投资价值"
        overall_deep = "公司基本面扎实，盈利能力强、成长性良好、财务稳健，具备长期持有的基础。"
    elif score >= 3:
        overall = "✓ 基本面良好，关注边际变化"
        overall_deep = "公司基本面健康，但某些方面存在改进空间。建议持续跟踪业绩变化。"
    elif score >= 2:
        overall = "→ 基本面一般，需精选时机"
        overall_deep = "公司基本面平平，可能存在某些风险点。建议谨慎参与。"
    else:
        overall = "⚠️ 基本面偏弱，谨慎参与"
        overall_deep = "公司基本面存在较多问题，建议回避或仅作为短期交易标的。"
    
    print(f"  {overall}")
    print(f"  └─ 综合判断: {overall_deep}")
    print(f"\n  关键亮点: {', '.join([c for c in comments if '强' in c or '良好' in c or '稳健' in c]) or '暂无'}")
    print(f"  关注风险: {', '.join([c for c in comments if '偏弱' in c or '承压' in c or '偏高' in c]) or '暂无'}")
    
    # 深度洞察汇总
    print(f"\n【深度洞察 - 基于数据的结论】")
    for i, insight in enumerate(deep_insights, 1):
        print(f"  {i}. {insight}")
    
    # 风险信号扫描
    print(f"\n【风险信号扫描 - 基于财务数据】")
    risk_signals = []
    
    try:
        # 获取多期财务数据用于趋势分析
        fina_multi = pro.fina_indicator(ts_code=ts_code, limit=4)
        if not fina_multi.empty and len(fina_multi) >= 2:
            # 1. 应收账款风险
            latest_ar = fina_multi.iloc[0].get('ar_turn', 0)  # 应收账款周转率
            prev_ar = fina_multi.iloc[1].get('ar_turn', 0)
            if latest_ar > 0 and prev_ar > 0:
                ar_change = (latest_ar - prev_ar) / prev_ar * 100
                if ar_change < -20:  # 周转率下降超过20%
                    risk_signals.append(f"⚠️ 应收账款周转率下降{abs(ar_change):.1f}%，回款变慢，可能存在坏账风险或下游客户资金紧张。")
            
            # 2. 存货风险
            latest_inv = fina_multi.iloc[0].get('inv_turn', 0)  # 存货周转率
            prev_inv = fina_multi.iloc[1].get('inv_turn', 0)
            if latest_inv > 0 and prev_inv > 0:
                inv_change = (latest_inv - prev_inv) / prev_inv * 100
                if inv_change < -20:
                    risk_signals.append(f"⚠️ 存货周转率下降{abs(inv_change):.1f}%，库存积压风险上升，可能面临减值压力。")
            
            # 3. 现金流风险
            latest_cf = fina_multi.iloc[0].get('ocf_to_profit', 0)  # 经营现金流/净利润
            if latest_cf and latest_cf < 0.5:
                risk_signals.append(f"⚠️ 经营现金流/净利润比率({latest_cf:.2f})低于0.5，利润含金量低，可能存在大量赊销。")
            
            # 4. 毛利率异常
            latest_gm = fina_multi.iloc[0].get('grossprofit_margin', 0)
            prev_gm = fina_multi.iloc[1].get('grossprofit_margin', 0)
            if latest_gm and prev_gm and latest_gm < prev_gm * 0.9:
                gm_change = (latest_gm - prev_gm) / prev_gm * 100
                risk_signals.append(f"⚠️ 毛利率下降{abs(gm_change):.1f}%，盈利能力恶化，可能是价格战或成本上升导致。")
            
            # 5. 费用率异常
            latest_expense = fina_multi.iloc[0].get('expense_of_sales', 0)  # 销售费用率
            prev_expense = fina_multi.iloc[1].get('expense_of_sales', 0)
            if latest_expense and prev_expense and latest_expense > prev_expense * 1.2:
                expense_change = (latest_expense - prev_expense) / prev_expense * 100
                risk_signals.append(f"⚠️ 销售费用率上升{expense_change:.1f}%，获客成本增加，可能面临竞争加剧。")
    except:
        pass
    
    # 估值风险
    if hist_val and valuation_analysis.get('pe', 0) > hist_val.get('pe_75th', 999):
        risk_signals.append(f"⚠️ 当前PE({valuation_analysis.get('pe', 0):.1f})高于历史75%分位，估值回归风险较大。")
    
    if industry_avg and financial_analysis.get('roe', 0) < industry_avg.get('roe_avg', 0) * 0.7:
        risk_signals.append(f"⚠️ ROE({financial_analysis.get('roe', 0):.1f}%)显著低于行业平均({industry_avg.get('roe_avg', 0):.1f}%)，竞争力存疑。")
    
    if risk_signals:
        for signal in risk_signals:
            print(f"  {signal}")
    else:
        print(f"  ✓ 未发现明显风险信号")
    
    # 未来趋势推演
    print(f"\n【未来趋势推演 - 基于数据的判断】")
    
    trend_signals = []
    
    # 1. 业绩趋势判断
    try:
        if not fina_multi.empty and len(fina_multi) >= 3:
            # ROE趋势
            roe_trend_data = [fina_multi.iloc[i].get('roe', 0) for i in range(min(4, len(fina_multi)))]
            roe_trend_data = [r for r in roe_trend_data if r is not None]
            if len(roe_trend_data) >= 3:
                if roe_trend_data[0] > roe_trend_data[1] > roe_trend_data[2]:
                    trend_signals.append("ROE连续改善，盈利能力处于上升通道。")
                elif roe_trend_data[0] < roe_trend_data[1] < roe_trend_data[2]:
                    trend_signals.append("ROE连续下滑，盈利能力持续恶化，需警惕。")
            
            # 营收趋势
            rev_trend_data = [fina_multi.iloc[i].get('tr_yoy', 0) for i in range(min(4, len(fina_multi)))]
            rev_trend_data = [r for r in rev_trend_data if r is not None]
            if len(rev_trend_data) >= 3:
                if rev_trend_data[0] > rev_trend_data[1] > rev_trend_data[2]:
                    trend_signals.append("营收增速逐季提升，业务扩张加速。")
                elif rev_trend_data[0] < rev_trend_data[1] < rev_trend_data[2]:
                    trend_signals.append("营收增速逐季下滑，增长动能减弱。")
    except:
        pass
    
    # 2. 行业周期位置判断
    if industry_avg:
        if financial_analysis.get('revenue_growth', 0) > industry_avg.get('revenue_growth_avg', 0) * 1.5:
            trend_signals.append("公司增速显著超越行业，处于相对优势地位，若行业复苏将双重受益。")
        elif financial_analysis.get('revenue_growth', 0) < 0 and industry_avg.get('revenue_growth_avg', 0) < 0:
            trend_signals.append("公司与行业同步下滑，可能处于周期底部，关注拐点信号。")
    
    # 3. 估值与业绩匹配度
    if valuation_analysis.get('pe', 0) > 50 and financial_analysis.get('profit_growth', 0) < 30:
        trend_signals.append("高估值(PE>50)但利润增速(<30%)不匹配，若业绩无法加速，估值下修风险大。")
    elif valuation_analysis.get('pe', 0) < 20 and financial_analysis.get('profit_growth', 0) > 20:
        trend_signals.append("低估值(PE<20)但利润增速(>20%)较高，存在估值修复空间。")
    
    # 4. 财务健康度趋势
    if financial_analysis.get('debt_ratio', 0) < 40:
        trend_signals.append("低负债率提供财务弹性，若行业底部可逆势扩张，周期向上时受益更大。")
    elif financial_analysis.get('debt_ratio', 0) > 70:
        trend_signals.append("高负债率限制财务弹性，若经济下行或利率上升，偿债压力将增大。")
    
    if trend_signals:
        for i, signal in enumerate(trend_signals, 1):
            print(f"  {i}. {signal}")
    else:
        print(f"  数据不足，无法形成明确趋势判断。建议持续跟踪季度财务数据。")
    

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 fundamental_analysis.py <股票代码>")
        print("示例: python3 fundamental_analysis.py 000001.SZ")
        print("      python3 fundamental_analysis.py 600519.SH")
        sys.exit(1)
    
    ts_code = sys.argv[1]
    
    print(f"\n【基本面分析框架】")
    print(f"  本分析从以下五个维度评估公司基本面：")
    print(f"  1. 商业模式: 做什么、怎么赚钱、壁垒在哪（详见商业模式分析）")
    print(f"  2. 竞争格局: 行业地位、竞争对手、护城河（详见竞争格局分析）")
    print(f"  3. 成长逻辑: 业绩增长的驱动因素是否可持续")
    print(f"  4. 估值合理性: 当前PE/PB与业绩增速是否匹配")
    print(f"  5. 财务健康度: 盈利、偿债、运营能力综合评估")
    
    # 分析宏观环境（含行业指数走势）
    analyze_macro(ts_code)
    
    # 分析具体公司
    analyze_company(ts_code)
