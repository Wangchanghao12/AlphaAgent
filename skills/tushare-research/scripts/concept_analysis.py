#!/usr/bin/env python3
"""
同花顺概念板块分析脚本
分析公司所属概念板块、概念热度、概念关联公司

注意：ths_member接口查询效率较低，本脚本提供分析框架
实际使用时可根据需要优化查询策略
"""
import sys
import os
import tushare as ts
import pandas as pd
from datetime import datetime

_token = (os.environ.get('TUSHARE_TOKEN') or '').strip()
pro = ts.pro_api(_token) if _token else ts.pro_api()


def analyze_concept_sectors(ts_code):
    """分析公司所属概念板块"""
    print("---")
    print(f"🏷️ 概念板块分析 - {ts_code}")
    print("---")
    
    # 获取公司基本信息
    try:
        basic = pro.stock_basic(ts_code=ts_code, fields='name,industry')
        if not basic.empty:
            company_name = basic.iloc[0]['name']
            industry = basic.iloc[0]['industry']
            print(f"\n【公司信息】")
            print(f"  公司名称: {company_name}")
            print(f"  所属行业: {industry}")
    except:
        company_name = ts_code
        industry = "未知"
    
    print(f"\n【概念板块分析框架】")
    print(f"""
由于同花顺概念接口查询效率限制，本分析提供概念板块分析框架：

【Step 1: 获取所属概念板块】
  方法：
  • 使用同花顺/东方财富等平台的"个股资料-所属概念"功能
  • 查看公司官网/年报中的业务描述对应的概念标签
  • 使用股票软件（如通达信、同花顺APP）查看F10资料

  常见概念分类：
  • 行业概念：芯片、新能源、人工智能、5G等
  • 地域概念：长三角、粤港澳、成渝等
  • 业绩概念：高股息、绩优股、成长股等
  • 事件概念：并购重组、股权激励、回购等

【Step 2: 分析概念板块表现】
  方法：
  • 查看概念指数近期涨跌幅
  • 对比大盘和所属概念的表现差异
  • 关注概念板块的资金流向

  判断标准：
  • 概念涨幅 > 5%：极强热度 🔥🔥🔥
  • 概念涨幅 3-5%：很强热度 🔥🔥
  • 概念涨幅 1-3%：较强热度 🔥
  • 概念涨幅 0-1%：一般 →
  • 概念涨幅 < 0%：弱势 ❄️

【Step 3: 分析概念关联公司】
  方法：
  • 查看同一概念下的其他公司
  • 识别概念龙头股和跟风股
  • 分析与关联公司的竞争/合作关系

  关注点：
  • 谁是概念龙头？（市值大、涨幅领先）
  • 公司与龙头的差距？
  • 是否有独特的差异化定位？

【Step 4: 概念驱动因素分析】
  政策驱动：
  • 是否有相关政策出台？
  • 政策力度和持续性如何？
  • 公司是否直接受益？

  技术驱动：
  • 是否有技术突破？
  • 技术商业化进度？
  • 公司技术储备如何？

  市场驱动：
  • 下游需求变化？
  • 产品价格走势？
  • 供需格局变化？
    """)
    
    # 提供搜索关键词
    print(f"\n【推荐搜索关键词】")
    print(f"  1. \"{company_name} {ts_code.split('.')[0]} 所属概念\"")
    print(f"  2. \"{company_name} 概念板块\"")
    print(f"  3. \"{company_name} 同花顺 概念\"")
    print(f"  4. \"{industry} 概念龙头股\"")
    print(f"  5. \"{industry} 板块 涨跌幅\"")
    
    # 概念分析用途
    print(f"\n【概念板块分析用途】")
    print(f"""
1. 情绪面分析补充：
   • 概念热度直接影响个股情绪
   • 热门概念容易吸引资金关注
   • 概念退潮时个股承压

2. 竞争格局补充：
   • 同一概念下的公司可能是竞争对手
   • 也可能是产业链上下游关系
   • 概念龙头往往有溢价

3. 消息面跟踪：
   • 概念板块政策对个股的影响
   • 行业事件对概念内公司的影响
   • 概念轮动规律

4. 投资主题识别：
   • 公司所属的热门投资主题
   • 主题投资的持续性判断
   • 主题内选股策略
    """)
    
    # 注意事项
    print(f"\n【注意事项】")
    print(f"""
⚠️ 概念炒作风险：
  • 概念热度与基本面可能脱节
  • 纯概念炒作容易大起大落
  • 需结合基本面分析

⚠️ 概念重叠问题：
  • 一家公司可能属于多个概念
  • 不同概念可能有冲突
  • 需识别主要驱动概念

⚠️ 概念时效性：
  • 概念热度具有时效性
  • 需持续跟踪概念变化
  • 及时识别概念退潮信号
    """)


def main():
    if len(sys.argv) < 2:
        print("用法: python3 concept_analysis.py <股票代码>")
        print("示例: python3 concept_analysis.py 688205.SH")
        print("      python3 concept_analysis.py 000001.SZ")
        sys.exit(1)
    
    ts_code = sys.argv[1]
    analyze_concept_sectors(ts_code)


if __name__ == '__main__':
    main()
