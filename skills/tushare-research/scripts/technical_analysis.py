#!/usr/bin/env python3
"""
A股技术面分析脚本 - 使用Tushare数据
因子视角：动量、反转、流动性、波动率、趋势
"""
import sys
import os
import tushare as ts
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 初始化Tushare（从环境变量 TUSHARE_TOKEN 传入）
import os
_token = (os.environ.get('TUSHARE_TOKEN') or '').strip()
pro = ts.pro_api(_token) if _token else ts.pro_api()

def calculate_ma(df, periods=[5, 10, 20, 60]):
    """计算移动平均线"""
    for period in periods:
        df[f'MA{period}'] = df['close'].rolling(window=period).mean()
    return df

def calculate_macd(df, fast=12, slow=26, signal=9):
    """计算MACD指标"""
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    df['MACD'] = ema_fast - ema_slow
    df['Signal'] = df['MACD'].ewm(span=signal, adjust=False).mean()
    df['Histogram'] = df['MACD'] - df['Signal']
    return df

def calculate_rsi(df, period=14):
    """计算RSI指标"""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def calculate_kdj(df, n=9, m1=3, m2=3):
    """计算KDJ指标"""
    low_list = df['low'].rolling(window=n, min_periods=n).min()
    high_list = df['high'].rolling(window=n, min_periods=n).max()
    rsv = (df['close'] - low_list) / (high_list - low_list) * 100
    df['K'] = rsv.ewm(alpha=1/m1, adjust=False).mean()
    df['D'] = df['K'].ewm(alpha=1/m2, adjust=False).mean()
    df['J'] = 3 * df['K'] - 2 * df['D']
    return df


def _ensure_macd_cols(df):
    """确保 DIF/DEA/MACD 列存在（plot_kline_chart 会写入，此处供独立调用时使用）"""
    if 'DIF' not in df.columns:
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = ema12 - ema26
        df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
        df['MACD_hist'] = (df['DIF'] - df['DEA']) * 2
    return df


def compute_momentum_factor(df, latest):
    """动量因子：ROC、MACD、均线斜率、RSI 趋势"""
    n = min(20, len(df) - 1)
    roc5 = (latest['close'] / df.iloc[-6]['close'] - 1) * 100 if len(df) >= 6 else 0
    roc20 = (latest['close'] / df.iloc[-21]['close'] - 1) * 100 if len(df) >= 21 else 0
    dif = latest.get('DIF', 0) or 0
    dea = latest.get('DEA', 0) or 0
    rsi = latest.get('RSI', 50) or 50
    # 均线斜率（MA20 近5日）
    ma20 = df['MA20'].tail(5) if 'MA20' in df.columns else pd.Series([latest['close']] * 5)
    slope = (ma20.iloc[-1] - ma20.iloc[0]) / ma20.iloc[0] * 100 if len(ma20) >= 2 and ma20.iloc[0] != 0 else 0
    score = 50
    if dif > dea and rsi > 50 and roc20 > 0:
        score = min(85, 60 + roc20 * 0.5)
    elif dif > dea or (roc5 > 2 and roc20 > 0):
        score = 65
    elif dif < dea and rsi < 50 and roc20 < 0:
        score = max(15, 40 + roc20 * 0.5)
    elif dif < dea or roc20 < -5:
        score = 35
    direction = "偏多" if score >= 60 else "偏空" if score <= 40 else "中性"
    return {
        'score': int(np.clip(score, 0, 100)),
        'direction': direction,
        'detail': f"5日收益{roc5:+.1f}% 20日收益{roc20:+.1f}% MACD{'多头' if dif>dea else '空头'} RSI{rsi:.0f}",
        'table': [
            ("5日涨幅", f"{roc5:+.1f}%"),
            ("20日涨幅", f"{roc20:+.1f}%"),
            ("MACD", "多头" if dif > dea else "空头"),
            ("RSI", f"{rsi:.1f}"),
        ]
    }


def compute_reversal_factor(df, latest):
    """反转因子：RSI 超买超卖、均线偏离、短期反转"""
    rsi = latest.get('RSI', 50) or 50
    ma20 = latest.get('MA20', latest['close']) or latest['close']
    dev_pct = (latest['close'] / ma20 - 1) * 100 if ma20 else 0
    roc5 = (latest['close'] / df.iloc[-6]['close'] - 1) * 100 if len(df) >= 6 else 0
    score = 50
    if rsi > 70:
        score = 30
        direction = "偏空"
        detail = f"RSI超买({rsi:.0f})，警惕回调"
    elif rsi < 30:
        score = 70
        direction = "偏多"
        detail = f"RSI超卖({rsi:.0f})，关注反弹"
    elif dev_pct > 8:
        score = 40
        direction = "偏空"
        detail = f"偏离MA20达{dev_pct:+.1f}%，存在回归压力"
    elif dev_pct < -8:
        score = 65
        direction = "偏多"
        detail = f"偏离MA20达{dev_pct:+.1f}%，存在回归动力"
    elif roc5 > 5:
        score = 45
        direction = "偏空"
        detail = f"短期涨幅{roc5:+.1f}%较大，谨防获利回吐"
    elif roc5 < -5:
        score = 60
        direction = "偏多"
        detail = f"短期跌幅{roc5:+.1f}%较大，关注超跌反弹"
    else:
        direction = "中性"
        detail = "无显著反转信号"
    return {
        'score': int(np.clip(score, 0, 100)),
        'direction': direction,
        'detail': detail,
        'table': [
            ("RSI", f"{rsi:.1f}"),
            ("偏离MA20", f"{dev_pct:+.1f}%"),
            ("5日涨幅", f"{roc5:+.1f}%"),
        ]
    }


def compute_liquidity_factor(df, latest):
    """流动性因子：量比、换手率、量价关系"""
    avg5 = df.tail(5)['vol'].mean()
    avg20 = df.tail(20)['vol'].mean()
    vol_ratio = latest['vol'] / avg5 if avg5 > 0 else 1
    turnover = latest.get('turnover_rate') or 0
    if isinstance(turnover, float) and np.isnan(turnover):
        turnover = 0
    pct_chg = latest.get('pct_chg', 0) or 0
    score = 50
    if vol_ratio > 1.5 and pct_chg > 0:
        score = 75
        detail = "放量上涨，资金参与积极"
    elif vol_ratio > 1.5 and pct_chg < 0:
        score = 35
        detail = "放量下跌，资金出逃"
    elif vol_ratio > 1.2:
        score = 60
        detail = "量能放大，观望方向"
    elif vol_ratio < 0.7:
        score = 40
        detail = "缩量，流动性偏弱"
    else:
        detail = "量能正常"
    direction = "偏多" if score >= 60 else "偏空" if score <= 40 else "中性"
    return {
        'score': int(np.clip(score, 0, 100)),
        'direction': direction,
        'detail': detail,
        'table': [
            ("量比", f"{vol_ratio:.2f}x"),
            ("换手率", f"{turnover:.2f}%" if turnover > 0 else "-"),
            ("5日均量", f"{avg5/10000:.1f}万手"),
        ]
    }


def compute_volatility_factor(df, latest, window=20):
    """波动率因子：ATR、历史波动率、分位"""
    recent = df.tail(window)
    high_low = recent['high'] - recent['low']
    atr = high_low.rolling(14).mean().iloc[-1] if len(recent) >= 14 else high_low.mean()
    returns = df['close'].pct_change().tail(60).dropna()
    hv = returns.std() * np.sqrt(252) * 100 if len(returns) >= 20 else 0
    hv_60 = df['close'].pct_change().tail(60).std() * 100 if len(df) >= 60 else 0
    hv_percentile = (df['close'].pct_change().tail(60).rank().iloc[-1] / 60 * 100) if len(df) >= 60 else 50
    atr_pct = atr / latest['close'] * 100 if latest['close'] else 0
    score = 50
    if atr_pct > 4 and hv_60 > 3:
        score = 35
        detail = "波动率扩张，风险加大"
    elif atr_pct < 1.5:
        score = 55
        detail = "波动收窄，待方向选择"
    else:
        detail = f"ATR占股价{atr_pct:.1f}%"
    direction = "偏空" if score <= 40 else "偏多" if score >= 60 else "中性"
    return {
        'score': int(np.clip(score, 0, 100)),
        'direction': direction,
        'detail': detail,
        'table': [
            ("ATR", f"{atr:.2f} ({atr_pct:.1f}%)"),
            ("60日波动率", f"{hv_60:.2f}%"),
        ]
    }


def compute_trend_factor(df, latest):
    """趋势因子：均线排列、区间位置、高低点结构"""
    current = latest['close']
    ma5 = latest.get('MA5', current) or current
    ma20 = latest.get('MA20', current) or current
    ma60 = latest.get('MA60', current) if 'MA60' in df.columns else None
    recent = df.tail(60)
    rh, rl = recent['high'].max(), recent['low'].min()
    position_pct = (current - rl) / (rh - rl) * 100 if rh != rl else 50
    highs = recent['high'].values
    lows = recent['low'].values
    hh = sum(1 for i in range(1, len(highs)) if highs[i] > highs[i-1])
    hl = sum(1 for i in range(1, len(lows)) if lows[i] > lows[i-1])
    lh = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i-1])
    ll = sum(1 for i in range(1, len(lows)) if lows[i] < lows[i-1])
    score = 50
    if current > ma5 > ma20 and (ma60 is None or ma5 > ma60):
        score = min(85, 55 + position_pct * 0.25)
        detail = "均线多头排列，趋势向上"
    elif current < ma5 < ma20 and (ma60 is None or ma5 < ma60):
        score = max(15, 45 - position_pct * 0.25)
        detail = "均线空头排列，趋势向下"
    elif hh >= 35 and hl >= 35:
        score = 65
        detail = "高低点上移，上升通道"
    elif lh >= 35 and ll >= 35:
        score = 35
        detail = "高低点下移，下降通道"
    elif position_pct > 70:
        score = 60
        detail = f"位于区间{position_pct:.0f}%位置，偏强"
    elif position_pct < 30:
        score = 40
        detail = f"位于区间{position_pct:.0f}%位置，偏弱"
    else:
        detail = "震荡整理，方向待选"
    direction = "偏多" if score >= 60 else "偏空" if score <= 40 else "中性"
    return {
        'score': int(np.clip(score, 0, 100)),
        'direction': direction,
        'detail': detail,
        'table': [
            ("均线排列", "多头" if current > ma5 > ma20 else "空头" if current < ma5 < ma20 else "纠缠"),
            ("区间位置", f"{position_pct:.0f}%"),
            ("60日高低", f"{rl:.2f}-{rh:.2f}"),
        ]
    }


def _find_close_price_peaks(closes, window=10):
    """
    波峰定义：某日收盘价严格高于其前 window 日、后 window 日（均不含当日）的收盘价。
    closes: 一维收盘价序列（与展示区间对齐的索引）。
    返回 [(i, price), ...]，i 为 closes 中的 0-based 下标。
    """
    n = len(closes)
    peaks = []
    for i in range(window, n - window):
        c = closes[i]
        if all(closes[j] < c for j in range(i - window, i)) and \
           all(closes[j] < c for j in range(i + 1, i + window + 1)):
            peaks.append((i, float(c)))
    return peaks


def plot_kline_chart(df, ts_code, title=None, ma_periods=[5, 20, 60],
                     display_days=100, total_days=190, save_path=None):
    """
    生成K线图并保存，用于可视化技术分析

    参数:
        df: DataFrame with OHLCV data
        ts_code: 股票代码
        title: 图表标题（可选）
        ma_periods: 均线周期列表，默认[5, 20, 60]
        display_days: 显示最近N个交易日，默认100
        total_days: 总共获取N个交易日用于计算长周期均线，默认190
        save_path: 保存路径（可选）

    波峰可视化:
        若某日收盘价为波峰（前后各10个交易日收盘价均低于该日），
        在该收盘价高度画水平虚线，自该日起向右延伸约30根K线（不超出展示区间）。

    返回:
        保存的图片路径
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("Warning: matplotlib not installed. Skip chart generation.")
        return None

    # 确保数据足够
    if len(df) < display_days:
        display_days = len(df)

    # 计算均线
    for period in ma_periods:
        df[f'MA{period}'] = df['close'].rolling(window=period).mean()

    # 计算MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = ema12 - ema26
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD'] = (df['DIF'] - df['DEA']) * 2

    # 取最近display_days天显示
    df_display = df.tail(display_days).reset_index(drop=True)
    df_display['day_num'] = range(1, display_days + 1)

    # 创建图表（constrained_layout 避免 tight_layout 的兼容性警告）
    fig, axes = plt.subplots(3, 1, figsize=(16, 10),
                             gridspec_kw={'height_ratios': [3, 1, 1], 'hspace': 0.08},
                             constrained_layout=True)
    ax1, ax2, ax3 = axes

    # 绘制K线
    for idx, row in df_display.iterrows():
        x_pos = row['day_num']
        color = 'red' if row['close'] >= row['open'] else 'green'
        # 实体
        ax1.bar(x_pos, row['close'] - row['open'],
                bottom=row['open'], color=color, width=0.7, alpha=0.7)
        # 影线
        ax1.plot([x_pos, x_pos], [row['low'], row['high']],
                color=color, linewidth=0.8)

    # 绘制均线
    colors = ['orange', 'blue', 'purple', 'gray']
    for i, period in enumerate(ma_periods):
        col_name = f'MA{period}'
        color = colors[i % len(colors)]
        ax1.plot(df_display['day_num'], df_display[col_name],
                label=f'MA{period}', color=color, linewidth=1.2)

    # 波峰：前后各10日（不含当日）收盘均低于当日收盘 → 水平虚线自该日起向右延伸约30根K线
    peak_window = 10
    peak_extend_bars = 30
    closes_arr = df_display['close'].values
    if len(closes_arr) > 2 * peak_window:
        peaks = _find_close_price_peaks(closes_arr, window=peak_window)
        for pk, (i0, peak_price) in enumerate(peaks):
            x_peak = i0 + 1  # day_num 与 K 线一致
            x_end = min(x_peak + peak_extend_bars, display_days)
            lbl = 'Peak' if pk == 0 else None
            ax1.plot(
                [x_peak, x_end], [peak_price, peak_price],
                linestyle='--', color='#444444', linewidth=2.0, alpha=0.8,
                zorder=4, label=lbl,
            )

    # 设置主图
    chart_title = title or f'{ts_code} - Last {display_days} Trading Days'
    ax1.set_title(chart_title, fontsize=14, fontweight='bold')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    ax1.set_ylabel('Price')
    ax1.set_xticks(range(0, display_days + 1, 10))
    ax1.set_xticklabels([])

    # 成交量
    colors_vol = ['red' if df_display.iloc[i]['close'] >= df_display.iloc[i]['open']
                  else 'green' for i in range(len(df_display))]
    ax2.bar(df_display['day_num'], df_display['vol'] / 10000,
            color=colors_vol, alpha=0.6, width=0.7)
    ax2.set_ylabel('Volume (10K)')
    ax2.grid(True, alpha=0.3)
    ax2.set_xticks(range(0, display_days + 1, 10))
    ax2.set_xticklabels([])

    # MACD
    macd_colors = ['red' if m >= 0 else 'green' for m in df_display['MACD']]
    ax3.bar(df_display['day_num'], df_display['MACD'],
            color=macd_colors, alpha=0.6, width=0.7, label='MACD Histogram')
    ax3.plot(df_display['day_num'], df_display['DIF'],
            label='DIF', color='blue', linewidth=1.5)
    ax3.plot(df_display['day_num'], df_display['DEA'],
            label='DEA', color='orange', linewidth=1.5)
    ax3.axhline(y=0, color='gray', linestyle='--', linewidth=0.8)
    ax3.set_ylabel('MACD')
    ax3.set_xlabel(f'Trading Day (Last {display_days} of {len(df)})', fontsize=12)
    ax3.legend(loc='upper right')
    ax3.grid(True, alpha=0.3)
    ax3.set_xticks(range(0, display_days + 1, 10))

    # 保存
    if save_path is None:
        # 默认保存到 charts/ 目录
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        charts_dir = os.path.join(script_dir, 'charts')
        os.makedirs(charts_dir, exist_ok=True)
        save_path = os.path.join(charts_dir, f'{ts_code.replace(".", "_")}_kline.png')

    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()

    return save_path

def analyze_kline_patterns(df):
    """分析K线形态"""
    patterns = []

    if len(df) < 3:
        return patterns

    # 获取最近3根K线
    k1 = df.iloc[-1]  # 最新
    k2 = df.iloc[-2]  # 前一根
    k3 = df.iloc[-3]  # 前二根

    # 锤子线（Hammer）
    body = abs(k1['close'] - k1['open'])
    lower_shadow = min(k1['close'], k1['open']) - k1['low']
    upper_shadow = k1['high'] - max(k1['close'], k1['open'])

    if lower_shadow > body * 2 and upper_shadow < body * 0.5 and k1['pct_chg'] > -2:
        patterns.append("锤子线（潜在底部反转）")

    # 吞没形态（Engulfing）
    k2_body = k2['close'] - k2['open']
    k1_body = k1['close'] - k1['open']

    if k2_body < 0 and k1_body > 0:  # 前阴后阳
        if k1['open'] < k2['close'] and k1['close'] > k2['open']:
            patterns.append("阳吞没（看涨信号）")
    elif k2_body > 0 and k1_body < 0:  # 前阳后阴
        if k1['open'] > k2['close'] and k1['close'] < k2['open']:
            patterns.append("阴吞没（看跌信号）")

    # 十字星（Doji）
    if body <= (k1['high'] - k1['low']) * 0.1:
        patterns.append("十字星（变盘信号）")

    # 长上影线
    if upper_shadow > body * 2 and lower_shadow < body:
        patterns.append("长上影线（上方压力大）")

    # 长下影线
    if lower_shadow > body * 2 and upper_shadow < body:
        patterns.append("长下影线（下方支撑强）")

    return patterns

def analyze_gaps(df):
    """分析缺口"""
    gaps = []

    for i in range(1, len(df)):
        prev_close = df.iloc[i-1]['close']
        curr_open = df.iloc[i]['open']
        curr_low = df.iloc[i]['low']
        curr_high = df.iloc[i]['high']

        # 向上跳空缺口
        if curr_low > prev_close * 1.01:  # 1%以上缺口
            gap_size = (curr_low - prev_close) / prev_close * 100
            gaps.append(f"向上跳空缺口 {df.iloc[i]['trade_date']} (+{gap_size:.2f}%)")

        # 向下跳空缺口
        elif curr_high < prev_close * 0.99:  # 1%以上缺口
            gap_size = (prev_close - curr_high) / prev_close * 100
            gaps.append(f"向下跳空缺口 {df.iloc[i]['trade_date']} (-{gap_size:.2f}%)")

    return gaps[-3:]  # 返回最近3个缺口

def analyze_technical(ts_code, days=60):
    """技术分析"""
    print("---")
    print(f"📈 技术面分析 - {ts_code}")
    print("---")

    # 获取历史数据
    try:
        df = pro.daily(ts_code=ts_code, limit=days+20)  # 多取一些用于计算均线
        if df.empty:
            print("  获取数据失败")
            return

        df = df.sort_values('trade_date')

        # 计算指标
        df = calculate_ma(df)
        df = calculate_macd(df)
        df = calculate_rsi(df)
        df = calculate_kdj(df)

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        print(f"\n【价格走势】")
        print(f"  最新日期: {latest['trade_date']}")
        print(f"  开盘价: {latest['open']:.2f}")
        print(f"  收盘价: {latest['close']:.2f}")
        print(f"  最高价: {latest['high']:.2f}")
        print(f"  最低价: {latest['low']:.2f}")
        print(f"  涨跌幅: {latest['pct_chg']:.2f}%")

        # 计算实体和影线
        body = abs(latest['close'] - latest['open'])
        upper_shadow = latest['high'] - max(latest['close'], latest['open'])
        lower_shadow = min(latest['close'], latest['open']) - latest['low']
        total_range = latest['high'] - latest['low']

        print(f"  实体: {body:.2f} ({body/total_range*100:.1f}%)")
        print(f"  上影线: {upper_shadow:.2f} ({upper_shadow/total_range*100:.1f}%)")
        print(f"  下影线: {lower_shadow:.2f} ({lower_shadow/total_range*100:.1f}%)")

        # 均线系统
        print(f"\n【均线系统】")
        for period in [5, 10, 20, 60]:
            ma_key = f'MA{period}'
            if ma_key in latest and not pd.isna(latest[ma_key]):
                ma_val = latest[ma_key]
                status = "↑" if latest['close'] > ma_val else "↓"
                # 计算偏离度
                deviation = (latest['close'] - ma_val) / ma_val * 100
                print(f"  MA{period}: {ma_val:.2f} {status} (偏离{deviation:+.2f}%)")

        # 趋势判断
        print(f"\n【趋势判断】")
        close = latest['close']
        ma5 = latest.get('MA5', close)
        ma10 = latest.get('MA10', close)
        ma20 = latest.get('MA20', close)
        ma60 = latest.get('MA60', close)

        if close > ma5 > ma10 > ma20 > ma60:
            trend = "多头排列（强势上涨）"
            trend_strength = 5
        elif close > ma5 > ma10 > ma20:
            trend = "中期多头（上涨趋势）"
            trend_strength = 4
        elif close > ma20 > ma60:
            trend = "中期上升趋势"
            trend_strength = 3
        elif close < ma5 < ma10 < ma20 < ma60:
            trend = "空头排列（强势下跌）"
            trend_strength = 1
        elif close < ma5 < ma10 < ma20:
            trend = "中期空头（下跌趋势）"
            trend_strength = 2
        elif close < ma20:
            trend = "中期下降趋势"
            trend_strength = 2
        else:
            trend = "震荡整理"
            trend_strength = 3

        print(f"  趋势: {trend}")
        print(f"  趋势强度: {'★' * trend_strength}{'☆' * (5-trend_strength)}")

        # 支撑压力
        print(f"\n【支撑与压力】")
        recent_20 = df.tail(20)
        recent_high = recent_20['high'].max()
        recent_low = recent_20['low'].min()
        recent_high_date = recent_20[recent_20['high'] == recent_high].iloc[-1]['trade_date']
        recent_low_date = recent_20[recent_20['low'] == recent_low].iloc[-1]['trade_date']

        print(f"  近20日高点: {recent_high:.2f} ({recent_high_date}) 压力位")
        print(f"  近20日低点: {recent_low:.2f} ({recent_low_date}) 支撑位")
        print(f"  当前位置: {(close-recent_low)/(recent_high-recent_low)*100:.1f}% (0%=支撑, 100%=压力)")

        # 缺口分析
        print(f"\n【缺口分析】")
        gaps = analyze_gaps(df.tail(30))
        if gaps:
            for gap in gaps[-3:]:
                print(f"  {gap}")
        else:
            print(f"  近30日无显著缺口")

        # K线形态
        print(f"\n【K线形态】")
        patterns = analyze_kline_patterns(df.tail(10))
        if patterns:
            for pattern in patterns:
                print(f"  • {pattern}")
        else:
            print(f"  无明显K线形态")

        # MACD
        print(f"\n【MACD指标】")
        macd = latest.get('MACD', 0)
        signal = latest.get('Signal', 0)
        hist = latest.get('Histogram', 0)
        print(f"  DIF: {macd:.3f}")
        print(f"  DEA: {signal:.3f}")
        print(f"  MACD柱: {hist:.3f}")

        if macd > signal and prev.get('MACD', 0) <= prev.get('Signal', 0):
            macd_signal = "金叉（买入信号）"
        elif macd < signal and prev.get('MACD', 0) >= prev.get('Signal', 0):
            macd_signal = "死叉（卖出信号）"
        elif macd > 0 and signal > 0:
            macd_signal = "多头延续"
        elif macd < 0 and signal < 0:
            macd_signal = "空头延续"
        else:
            macd_signal = "震荡"
        print(f"  信号: {macd_signal}")

        # RSI
        print(f"\n【RSI指标】")
        rsi = latest.get('RSI', 50)
        print(f"  RSI(14): {rsi:.2f}")
        if rsi > 80:
            rsi_status = "严重超买（谨慎）"
        elif rsi > 70:
            rsi_status = "超买区域（谨慎）"
        elif rsi < 20:
            rsi_status = "严重超卖（关注）"
        elif rsi < 30:
            rsi_status = "超卖区域（关注）"
        else:
            rsi_status = "正常区域"
        print(f"  状态: {rsi_status}")

        # KDJ
        print(f"\n【KDJ指标】")
        k = latest.get('K', 50)
        d = latest.get('D', 50)
        j = latest.get('J', 50)
        print(f"  K: {k:.2f}")
        print(f"  D: {d:.2f}")
        print(f"  J: {j:.2f}")

        if k > d and prev.get('K', 0) <= prev.get('D', 0):
            kdj_signal = "金叉（买入信号）"
        elif k < d and prev.get('K', 0) >= prev.get('D', 0):
            kdj_signal = "死叉（卖出信号）"
        elif j > 100:
            kdj_signal = "J值超买"
        elif j < 0:
            kdj_signal = "J值超卖"
        else:
            kdj_signal = "震荡"
        print(f"  信号: {kdj_signal}")

        # 成交量分析
        print(f"\n【成交量分析】")
        vol = latest['vol']
        vol_ma5 = df['vol'].tail(5).mean()
        vol_ma20 = df['vol'].tail(20).mean()
        print(f"  今日成交量: {vol/10000:.2f} 万手")
        print(f"  5日均量: {vol_ma5/10000:.2f} 万手")
        print(f"  20日均量: {vol_ma20/10000:.2f} 万手")

        if vol > vol_ma5 * 1.5:
            vol_status = "放量"
        elif vol < vol_ma5 * 0.7:
            vol_status = "缩量"
        else:
            vol_status = "正常"

        # 量价配合
        price_change = latest['pct_chg']
        if price_change > 0 and vol > vol_ma5:
            vp_status = "放量上涨（健康）"
        elif price_change > 0 and vol < vol_ma5:
            vp_status = "缩量上涨（背离）"
        elif price_change < 0 and vol > vol_ma5:
            vp_status = "放量下跌（恐慌）"
        elif price_change < 0 and vol < vol_ma5:
            vp_status = "缩量下跌（蓄势）"
        else:
            vp_status = "量价平稳"

        print(f"  量能: {vol_status}")
        print(f"  量价配合: {vp_status}")

        # 综合技术评分
        print(f"\n【技术综合评估】")
        score = 0
        if trend_strength >= 4:
            score += 2
        elif trend_strength >= 3:
            score += 1

        if '金叉' in macd_signal or '金叉' in kdj_signal:
            score += 1

        if 30 < rsi < 70:
            score += 1

        if '放量上涨' in vp_status:
            score += 1

        if '锤子线' in str(patterns) or '阳吞没' in str(patterns):
            score += 1

        if score >= 4:
            tech_rating = "强势看多"
        elif score >= 3:
            tech_rating = "偏多"
        elif score >= 2:
            tech_rating = "中性"
        elif score >= 1:
            tech_rating = "偏空"
        else:
            tech_rating = "看空"

        print(f"  技术评分: {score}/5")
        print(f"  技术评级: {tech_rating}")

        # 技术结论与操作建议
        print(f"\n【技术结论】")

        # 趋势判断
        if trend_strength >= 4:
            trend_comment = "趋势强劲，顺势而为"
        elif trend_strength >= 2:
            trend_comment = "趋势一般，关注突破"
        else:
            trend_comment = "趋势不明，谨慎参与"

        # 关键位置
        position_pct = (close-recent_low)/(recent_high-recent_low)*100 if recent_high != recent_low else 50
        if position_pct < 20:
            position_comment = f"接近支撑位{recent_low:.2f}，关注反弹机会"
        elif position_pct > 80:
            position_comment = f"接近压力位{recent_high:.2f}，注意回调风险"
        else:
            position_comment = f"处于震荡区间中部，等待方向选择"

        # 综合建议
        print(f"  • 趋势判断: {trend_comment}")
        print(f"  • 位置判断: {position_comment}")

        if score >= 4:
            print(f"  • 操作建议: 技术面向好，可考虑逢低布局")
            print(f"  • 关键价位: 支撑{recent_low:.2f} / 压力{recent_high:.2f}")
        elif score >= 3:
            print(f"  • 操作建议: 技术面偏多，关注量能配合")
            print(f"  • 关键价位: 支撑{recent_low:.2f} / 压力{recent_high:.2f}")
        elif score >= 2:
            print(f"  • 操作建议: 技术面中性，观望为主")
            print(f"  • 关键价位: 支撑{recent_low:.2f} / 压力{recent_high:.2f}")
        elif score >= 1:
            print(f"  • 操作建议: 技术面偏弱，控制仓位")
            print(f"  • 关键价位: 跌破{recent_low:.2f}考虑止损")
        else:
            print(f"  • 操作建议: 技术面看空，回避为主")
            print(f"  • 关键价位: 反弹不过{recent_high:.2f}不介入")

    except Exception as e:
        print(f"  分析失败: {e}")
        import traceback
        traceback.print_exc()

def analyze_technical_visual(ts_code, days=190, display_days=100, ma_periods=[5, 20, 90], save_path=None):
    """
    可视化技术分析 - 生成K线图并输出分析

    参数:
        ts_code: 股票代码，如'601138.SH'
        days: 获取多少个交易日数据（用于计算长周期均线）
        display_days: 显示最近多少个交易日
        ma_periods: 均线周期列表，默认[5, 20, 90]
        save_path: 图表保存路径

    返回:
        chart_path: 生成的图表路径
    """
    print(f"\n## 📊 {ts_code} 技术分析\n")

    try:
        # 获取数据（使用前复权数据，避免除权除息导致的跳变）
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - pd.Timedelta(days=days*1.5)).strftime('%Y%m%d')

        df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

        # 获取复权因子并计算前复权价格
        try:
            adj_df = pro.adj_factor(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if adj_df is not None and len(adj_df) > 0:
                adj_df = adj_df.sort_values('trade_date')
                df = df.sort_values('trade_date')
                df = df.merge(adj_df[['trade_date', 'adj_factor']], on='trade_date', how='left')
                # 计算前复权价格（使用最新交易日的复权因子作为基准）
                latest_adj_factor = df['adj_factor'].iloc[-1]
                for col in ['open', 'high', 'low', 'close']:
                    df[col] = df[col] * df['adj_factor'] / latest_adj_factor
        except Exception as e:
            print(f"Warning: 复权处理失败，使用原始价格: {e}")

        if df is None or len(df) == 0:
            print(f"Error: 无法获取 {ts_code} 的数据")
            return None

        df = df.sort_values('trade_date')
        df['trade_date'] = pd.to_datetime(df['trade_date'])

        # 确保数据足够
        if len(df) < days:
            days = len(df)

        # 取最近days天
        df = df.tail(days).reset_index(drop=True)

        # 合并换手率（daily 无此字段，需从 daily_basic 获取）
        try:
            dates = df['trade_date'].dt.strftime('%Y%m%d')
            db = pro.daily_basic(ts_code=ts_code, start_date=dates.min(), end_date=dates.max(), fields='trade_date,turnover_rate')
            if db is not None and not db.empty:
                db = db.rename(columns={'trade_date': '_dt'})
                df['_dt'] = dates
                df = df.merge(db, on='_dt', how='left').drop(columns=['_dt'])
        except Exception:
            pass  # 无 daily_basic 权限时跳过，换手率保持空

        # 生成K线图
        chart_path = plot_kline_chart(df, ts_code, ma_periods=ma_periods,
                                      display_days=display_days, total_days=len(df),
                                      save_path=save_path)

        # 计算所有指标
        for period in ma_periods:
            df[f'MA{period}'] = df['close'].rolling(window=period).mean()

        # 确保MA60和MA120被计算（用于三周期分析）
        if len(df) >= 60:
            df['MA60'] = df['close'].rolling(window=60).mean()
        if len(df) >= 120:
            df['MA120'] = df['close'].rolling(window=120).mean()
        if len(df) >= 10:
            df['MA10'] = df['close'].rolling(window=10).mean()

        df = calculate_macd(df)
        df = calculate_rsi(df)
        df = calculate_kdj(df)

        # 取最新数据
        latest = df.iloc[-1]

        # 确保 DIF/DEA 存在（plot_kline_chart 已写入）
        _ensure_macd_cols(df)
        latest = df.iloc[-1]

        current = latest['close']

        # ========== 一、关键价位 ==========
        r20 = df.tail(20)
        r60 = df.tail(60)
        h20, l20 = r20['high'].max(), r20['low'].min()
        h60, l60 = r60['high'].max(), r60['low'].min()
        fib_382 = h20 - (h20 - l20) * 0.382
        fib_618 = h20 - (h20 - l20) * 0.618

        print(f"\n- **关键价位**")
        print("")
        print("    | 类型 | 价位 | 距当前 | 计算依据 |")
        print("    |:-----|------|:-------|:---------|")
        print(f"    | 当前价 | {current:.2f} | - | 最新收盘价 |")
        print(f"    | 近期压力 | {h20:.2f} | +{(h20/current-1)*100:.1f}% | 20日最高价 |")
        print(f"    | 强压力 | {h60:.2f} | +{(h60/current-1)*100:.1f}% | 60日最高价 |")
        print(f"    | 斐波0.382 | {fib_382:.2f} | {(fib_382/current-1)*100:+.1f}% | 20日区间自高点回撤38.2% |")
        print(f"    | 斐波0.618 | {fib_618:.2f} | {(fib_618/current-1)*100:+.1f}% | 20日区间自高点回撤61.8% |")
        print(f"    | 近期支撑 | {l20:.2f} | {(l20/current-1)*100:+.1f}% | 20日最低价 |")
        print(f"    | 强支撑 | {l60:.2f} | {(l60/current-1)*100:+.1f}% | 60日最低价 |")

        # ========== 二、因子计算 ==========
        mom = compute_momentum_factor(df, latest)
        rev = compute_reversal_factor(df, latest)
        liq = compute_liquidity_factor(df, latest)
        vol_f = compute_volatility_factor(df, latest)
        trd = compute_trend_factor(df, latest)
        factors = [("动量", mom), ("反转", rev), ("流动性", liq), ("波动率", vol_f), ("趋势", trd)]

        # ========== 三、因子总览 ==========
        print(f"\n- **因子总览**")
        print("")
        print("    | 因子 | 得分 | 方向 | 简要结论 |")
        print("    |:-----|----:|:----:|:---------|")
        for name, f in factors:
            print(f"    | {name} | {f['score']} | {f['direction']} | {f['detail'][:24]} |")

        # ========== 四、综合结论与操作建议 ==========
        avg_score = np.mean([f[1]['score'] for f in factors])
        multi_cnt = sum(1 for _, f in factors if f['direction'] == '偏多')
        short_cnt = sum(1 for _, f in factors if f['direction'] == '偏空')
        multi_names = [n for n, f in factors if f['direction'] == '偏多']
        short_names = [n for n, f in factors if f['direction'] == '偏空']
        neutral_names = [n for n, f in factors if f['direction'] == '中性']
        basis_parts = []
        if multi_names:
            basis_parts.append(f"{'、'.join(multi_names)}偏多")
        if short_names:
            basis_parts.append(f"{'、'.join(short_names)}偏空")
        if neutral_names:
            basis_parts.append(f"{'、'.join(neutral_names)}中性")
        basis_str = "；".join(basis_parts) + f" → {multi_cnt}多{short_cnt}空"

        if multi_cnt >= 4:
            conclusion = "偏多"
            action = "试仓或持有，关注压力位"
        elif short_cnt >= 4:
            conclusion = "偏空"
            action = "减仓或观望，关注支撑位"
        elif multi_cnt > short_cnt:
            conclusion = "中性偏多"
            action = "谨慎参与，控制仓位"
        elif short_cnt > multi_cnt:
            conclusion = "中性偏空"
            action = "观望为主"
        else:
            conclusion = "中性"
            action = "观望，等待因子共振"

        print(f"\n- **综合结论**")
        print(f"    - 技术面: {conclusion} | 因子均分: {avg_score:.0f}")
        print(f"    - 判断依据: {basis_str}")
        print(f"    - 操作建议: {action}")

        return chart_path

    except Exception as e:
        print(f"  分析失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def analyze_trend_methodology(df, latest, ma_periods):
    """
    应用趋势分析方法论（三周期共振 + 四维度确认）
    参考: trend_analysis_methodology.md
    输出格式：Markdown表格
    """
    print("\n### 八、三周期共振分析\n")

    # 获取各周期数据
    # 1. 长线趋势（60/120日均线）
    ma60 = df['MA60'].iloc[-1] if 'MA60' in df.columns and len(df) >= 60 else None
    ma120 = df['MA120'].iloc[-1] if 'MA120' in df.columns and len(df) >= 120 else None

    long_term = "→ 震荡"
    if ma60 is not None and ma120 is not None:
        if latest['close'] > ma60 > ma120:
            long_term = "↑ 上升"
        elif latest['close'] < ma60 < ma120:
            long_term = "↓ 下降"

    # 2. 中线趋势（20/60日均线）
    ma20 = df['MA20'].iloc[-1] if 'MA20' in df.columns else None
    ma60_current = df['MA60'].iloc[-1] if 'MA60' in df.columns else None

    mid_term = "→ 震荡"
    if ma20 is not None and ma60_current is not None:
        if latest['close'] > ma20 > ma60_current:
            mid_term = "↑ 上升"
        elif latest['close'] < ma20 < ma60_current:
            mid_term = "↓ 下降"

    # 3. 短线趋势（5/10日均线）
    ma5 = df['MA5'].iloc[-1] if 'MA5' in df.columns else None
    ma10 = df['MA10'].iloc[-1] if 'MA10' in df.columns else None

    short_term = "→ 震荡"
    if ma5 is not None and ma10 is not None:
        if latest['close'] > ma5 > ma10:
            short_term = "↑ 上升"
        elif latest['close'] < ma5 < ma10:
            short_term = "↓ 下降"

    # 三周期数据表格
    ma60_str = f"{ma60:.2f}" if ma60 is not None else "数据不足"
    ma120_str = f"{ma120:.2f}" if ma120 is not None else "数据不足"
    ma20_str = f"{ma20:.2f}" if ma20 is not None else "N/A"
    ma5_str = f"{ma5:.2f}" if ma5 is not None else "N/A"
    ma10_str = f"{ma10:.2f}" if ma10 is not None else "N/A"

    print("| 周期 | 均线 | 数值 | 趋势判断 |")
    print("|------|------|------|----------|")
    print(f"| 长线（60/120日） | MA60 | {ma60_str} | {long_term} |")
    print(f"| 长线（60/120日） | MA120 | {ma120_str} | - |")
    print(f"| 中线（20/60日） | MA20 | {ma20_str} | {mid_term} |")
    print(f"| 中线（20/60日） | MA60 | {ma60_str} | - |")
    print(f"| 短线（5/10日） | MA5 | {ma5_str} | {short_term} |")
    print(f"| 短线（5/10日） | MA10 | {ma10_str} | - |")

    # 共振强度判断
    trend_count = sum([1 for t in [long_term, mid_term, short_term] if "上升" in t])
    down_count = sum([1 for t in [long_term, mid_term, short_term] if "下降" in t])

    if trend_count == 3:
        resonance = "★★★★★ 三周期共振向上 - 强烈看多"
    elif trend_count == 2:
        resonance = "★★★★☆ 两周期向上 - 偏多"
    elif down_count == 3:
        resonance = "★★★★★ 三周期共振向下 - 强烈看空"
    elif down_count == 2:
        resonance = "★★★☆☆ 两周期向下 - 偏空"
    else:
        resonance = "★★☆☆☆ 趋势不明 - 观望"

    print(f"\n**共振强度**: {resonance}\n")

    # 四维度评分 - 表格版
    print("### 九、四维度评分（各25分，总分100分）\n")
    print("| 维度 | 满分 | 得分 | 状态 | 关键依据 |")
    print("|------|------|------|------|----------|")

    price_score = 10  # 默认震荡
    recent_highs = df.tail(20)['high'].max()
    recent_lows = df.tail(20)['low'].min()
    prev_highs = df.tail(60).head(40)['high'].max()
    prev_lows = df.tail(60).head(40)['low'].min()
    current_price = latest['close']

    # 计算距离高低点的位置（百分比）
    range_20 = recent_highs - recent_lows
    position_pct = (current_price - recent_lows) / range_20 * 100 if range_20 > 0 else 50

    if current_price > recent_highs * 0.98:  # 接近或突破近期高点
        price_score = 20
        price_status = "突破前期高点"
        price_detail = f"收盘价{current_price:.2f}接近20日高点{recent_highs:.2f}（{(current_price/recent_highs-1)*100:+.1f}%），多头强势"
    elif current_price > prev_highs and current_price > recent_highs * 0.95:  # 突破更前期高点
        price_score = 20
        price_status = "创阶段新高"
        price_detail = f"突破前期高点{prev_highs:.2f}，创阶段新高"
    elif position_pct > 60:  # 位于区间上沿
        price_score = 15
        price_status = "处于区间上沿"
        price_detail = f"位于20日区间{position_pct:.0f}%位置（区间{recent_lows:.2f}-{recent_highs:.2f}），偏多"
    elif position_pct < 40:  # 位于区间下沿
        price_score = 8
        price_status = "处于区间下沿"
        price_detail = f"位于20日区间{position_pct:.0f}%位置（区间{recent_lows:.2f}-{recent_highs:.2f}），偏弱"
    elif current_price < recent_lows * 1.02:  # 接近近期低点
        price_score = 5
        price_status = "接近前期低点"
        price_detail = f"接近20日低点{recent_lows:.2f}，需警惕破位风险"
    else:
        price_score = 10
        price_status = "震荡整理中"
        price_detail = f"位于20日区间中部{position_pct:.0f}%位置"

    print(f"| 价格结构 | 25 | {price_score} | {price_status} | {price_detail} |")

    vol_score = 10
    avg_vol_5 = df.tail(5)['vol'].mean()
    avg_vol_20 = df.tail(20)['vol'].mean()
    latest_vol = latest['vol']

    # 计算量比
    vol_ratio_5 = latest_vol / avg_vol_5 if avg_vol_5 > 0 else 1
    vol_ratio_20 = latest_vol / avg_vol_20 if avg_vol_20 > 0 else 1

    if vol_ratio_5 > 2.0:
        vol_score = 25
        vol_status = "显著放量"
        vol_detail = f"今日成交量{latest_vol/10000:.2f}万手，是5日均量{avg_vol_5/10000:.2f}万手的{vol_ratio_5:.1f}倍，放量突破"
    elif vol_ratio_5 > 1.5:
        vol_score = 20
        vol_status = "放量突破"
        vol_detail = f"今日成交量为5日均量的{vol_ratio_5:.1f}倍，符合突破量能要求"
    elif vol_ratio_5 > 1.2:
        vol_score = 15
        vol_status = "温和放量"
        vol_detail = f"今日成交量为5日均量的{vol_ratio_5:.1f}倍，量能温和放大"
    elif vol_ratio_5 > 0.8:
        vol_score = 10
        vol_status = "量能一般"
        vol_detail = f"今日成交量与5日均量基本持平（{vol_ratio_5:.1f}倍），无异常"
    elif vol_ratio_5 > 0.5:
        vol_score = 5
        vol_status = "缩量"
        vol_detail = f"今日成交量仅为5日均量的{vol_ratio_5:.1f}倍，缩量明显"
    else:
        vol_score = 3
        vol_status = "严重缩量"
        vol_detail = f"量比{vol_ratio_5:.1f}x"

    print(f"| 量能 | 25 | {vol_score} | {vol_status} | {vol_detail} |")

    momentum_score = 10
    dif = latest.get('DIF', 0)
    dea = latest.get('DEA', 0)
    macd = latest.get('MACD', 0)
    rsi = latest.get('RSI', 50)

    # MACD判断
    dif_dea_diff = dif - dea
    macd_status = ""

    if dif > dea and macd > 0:
        if dif > dea * 1.2:  # DIF明显上穿DEA
            momentum_score = 20
            momentum_status = "MACD金叉，动能强劲"
            macd_status = f"DIF({dif:.2f})明显上穿DEA({dea:.2f})，红柱扩大"
        elif dif > dea * 1.05:
            momentum_score = 18
            momentum_status = "MACD金叉，动能良好"
            macd_status = f"DIF({dif:.2f})上穿DEA({dea:.2f})，金叉确认"
        else:
            momentum_score = 15
            momentum_status = "MACD金叉，动能一般"
            macd_status = f"DIF({dif:.2f})略高于DEA({dea:.2f})，动能较弱"
    elif dif > dea and macd <= 0:
        momentum_score = 12
        momentum_status = "MACD即将金叉"
        macd_status = f"DIF({dif:.2f})接近DEA({dea:.2f})，有望金叉"
    elif dif < dea and macd < 0:
        if dif < dea * 0.8:
            momentum_score = 5
            momentum_status = "MACD死叉，空头强势"
            macd_status = f"DIF({dif:.2f})明显低于DEA({dea:.2f})，绿柱扩大"
        else:
            momentum_score = 8
            momentum_status = "MACD死叉，空头一般"
            macd_status = f"DIF({dif:.2f})低于DEA({dea:.2f})，处于死叉"
    else:
        momentum_score = 10
        momentum_status = "MACD中性"
        macd_status = f"DIF({dif:.2f})与DEA({dea:.2f})接近，方向不明"

    # RSI判断（调整分数）
    rsi_status = ""
    if rsi > 70:
        rsi_status = f"RSI({rsi:.1f})超买，警惕回调"
        if momentum_score > 15:
            momentum_score -= 5  # 超买时降低分数
    elif rsi < 30:
        rsi_status = f"RSI({rsi:.1f})超卖，关注反弹"
        if momentum_score < 15:
            momentum_score += 3  # 超卖时略微提升分数
    elif rsi > 50:
        rsi_status = f"RSI({rsi:.1f})偏强"
    else:
        rsi_status = f"RSI({rsi:.1f})偏弱"

    momentum_detail = f"DIF={dif:.2f}, RSI={rsi:.1f}"
    print(f"| 动能 | 25 | {momentum_score} | {momentum_status} | {momentum_detail} |")

    pattern_score = 10
    # 检查是否在上升通道
    highs = df.tail(20)['high'].values
    lows = df.tail(20)['low'].values
    closes = df.tail(20)['close'].values

    # 简单判断高低点排列
    higher_highs = sum([1 for i in range(1, len(highs)) if highs[i] > highs[i-1]])
    higher_lows = sum([1 for i in range(1, len(lows)) if lows[i] > lows[i-1]])
    lower_highs = sum([1 for i in range(1, len(highs)) if highs[i] < highs[i-1]])
    lower_lows = sum([1 for i in range(1, len(lows)) if lows[i] < lows[i-1]])

    # 计算趋势线斜率（简单线性回归）
    x = np.arange(len(closes))
    slope_high = np.polyfit(x, highs, 1)[0] if len(highs) == len(x) else 0
    slope_low = np.polyfit(x, lows, 1)[0] if len(lows) == len(x) else 0

    if higher_highs >= 12 and higher_lows >= 12 and slope_high > 0 and slope_low > 0:
        pattern_score = 20
        pattern_status = "上升趋势确认（高低点上移）"
        pattern_detail = f"近20日中{higher_highs}日创新高、{higher_lows}日抬升低点，上升通道完好"
    elif higher_highs >= 10 and higher_lows >= 8:
        pattern_score = 18
        pattern_status = "上升趋势良好"
        pattern_detail = f"高低点整体向上，{higher_highs}次创新高"
    elif lower_highs >= 12 and lower_lows >= 12 and slope_high < 0 and slope_low < 0:
        pattern_score = 5
        pattern_status = "下降趋势（高低点下移）"
        pattern_detail = f"近20日中{lower_highs}日创新低、{lower_lows}日下降低点，处于下降通道"
    elif lower_highs >= 10 and lower_lows >= 8:
        pattern_score = 7
        pattern_status = "下降趋势中"
        pattern_detail = f"高低点整体向下，{lower_highs}次创新低"
    elif higher_lows >= 8 and lower_highs >= 8:
        pattern_score = 12
        pattern_status = "三角形整理"
        pattern_detail = f"高点下移、低点上移，振幅收窄，即将选择方向"
    else:
        pattern_score = 10
        pattern_status = "震荡整理"
        pattern_detail = f"高低点无明确规律（新高{higher_highs}次/新低{lower_highs}次），方向不明"

    pattern_detail_short = f"新高{higher_highs}次/新低{lower_lows}次"
    print(f"| 形态 | 25 | {pattern_score} | {pattern_status} | {pattern_detail_short} |")

    # 总分
    total_score = price_score + vol_score + momentum_score + pattern_score
    print(f"\n**综合评分**: {total_score}/100分 ", end="")

    if total_score >= 75:
        print("(趋势确认)")
        trend_state = "↑ 上升趋势"
        action = "满仓或加仓"
    elif total_score >= 60:
        print("(反弹确认)")
        trend_state = "↑ 反弹确认"
        action = "试仓（20%仓位）"
    elif total_score >= 40:
        print("(震荡)")
        trend_state = "→ 震荡整理"
        action = "观望，等待方向选择"
    elif total_score >= 25:
        print("(弱势)")
        trend_state = "↓ 弱势整理"
        action = "减仓或观望"
    else:
        print("(下降)")
        trend_state = "↓ 下降趋势"
        action = "空仓或极轻仓"

    print()

    # 趋势状态与操作建议
    print("### 十、趋势状态与操作建议\n")
    print(f"- **趋势状态**: {trend_state}")
    print(f"- **操作建议**: {action}")
    print()

    # 关键位与交易策略
    print("### 十一、关键位与交易策略\n")
    recent_high = df.tail(20)['high'].max()
    recent_low = df.tail(20)['low'].min()
    current = latest['close']

    print("| 类型 | 价位 | 距当前 | 策略 |")
    print("|------|------|--------|------|")
    print(f"| 压力位 | {recent_high:.2f} | +{(recent_high/current-1)*100:.1f}% | 突破可加仓 |")
    print(f"| 当前价 | {current:.2f} | - | - |")
    print(f"| 支撑位 | {recent_low:.2f} | -{(1-recent_low/current)*100:.1f}% | 跌破需止损 |")
    print()

    # 多周期共振验证表
    print("### 十二、多周期共振验证表\n")
    print("| 长周期 | 中周期 | 短周期 | 共振强度 | 操作建议 |")
    print("|--------|--------|--------|----------|----------|")
    print(f"| {long_term} | {mid_term} | {short_term} | {resonance} | {action} |")
    print()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 technical_analysis.py <股票代码> [天数] [--no-visual]")
        print("示例: python3 technical_analysis.py 000001.SZ")
        print("      python3 technical_analysis.py 600519.SH 120")
        print("      python3 technical_analysis.py 601138.SH --no-visual")
        sys.exit(1)

    ts_code = sys.argv[1]

    # 默认使用可视化，--no-visual 关闭
    if '--no-visual' in sys.argv:
        days = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 60
        analyze_technical(ts_code, days)
    else:
        analyze_technical_visual(ts_code)

