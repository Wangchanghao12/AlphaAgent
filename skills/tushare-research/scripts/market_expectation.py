#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
估值预期分析模块
分析高PE/PB背后的市场预期、转型叙事、概念题材
"""

import sys
import os
import tushare as ts
import pandas as pd
from datetime import datetime, timedelta

# 初始化Tushare
pro = ts.pro_api()

# 热门概念题材关键词映射
CONCEPT_KEYWORDS = {
    "人形机器人": ["机器人", "丝杠", "轴承", "关节", "减速器", "执行器", "Optimus", "特斯拉"],
    "固态电池": ["固态电池", "硫化物", "聚合物", "电解质", "能量密度", "万向一二三"],
    "新能源汽车": ["新能源", "电动车", "锂电池", "动力电池", "电机", "电控"],
    "AI/人工智能": ["AI", "人工智能", "大模型", "算力", "芯片", "智驾"],
    "低空经济": ["低空", "飞行汽车", "eVTOL", "无人机", "航空"],
    "国企改革": ["重组", "资产注入", "集团", "混改", "央企", "国资"],
    "华为链": ["华为", "鸿蒙", "问界", "智选", "供应商"],
    "特斯拉链": ["特斯拉", "Tesla", "Optimus", "Cybertruck", "上海工厂"],
    "储能": ["储能", "逆变器", "光伏", "风电", "电网"],
    "半导体": ["芯片", "半导体", "晶圆", "光刻", "封测", "EDA"]
}

# 典型转型案例分析（用于参考）
TRANSFORMATION_CASES = {
    "000559.SZ": {
        "name": "万向钱潮",
        "traditional_business": "汽车零部件（万向节、轮毂轴承）",
        "transformation_narrative": "从传统汽配向'机器人+新能源+智能底盘'转型",
        "key_expectations": [
            {"type": "人形机器人", "content": "切入特斯拉Optimus供应链，精密轴承+丝杠供应商", "catalyst": "2026年产能120万套", "probability": "中", "risk": "特斯拉量产推迟；竞争加剧"},
            {"type": "固态电池", "content": "参股万向一二三10.74%，布局硫化物/聚合物双路线", "catalyst": "2026年小批量生产", "probability": "中", "risk": "技术路线不确定；量产进度不及预期"},
            {"type": "资产重组", "content": "收购万向集团优质资产进行中", "catalyst": "资产注入增厚业绩", "probability": "中高", "risk": "时间不确定；注入资产质量待验证"},
            {"type": "低空经济", "content": "万向集团布局飞行汽车，存在协同可能", "catalyst": "eVTOL市场爆发", "probability": "低", "risk": "尚处早期；协同效应不确定"}
        ],
        "valuation_logic": "传统业务PE 15-20倍 + 机器人业务PE 40-50倍 + 固态电池资产重估",
        "investment_type": "主题投资（非价值投资）"
    }
}


def get_basic_info(code):
    """获取公司基本信息"""
    try:
        df = pro.stock_basic(ts_code=code)
        if df is not None and not df.empty:
            return {
                "name": df.iloc[0]["name"],
                "industry": df.iloc[0].get("industry", ""),
                "fullname": df.iloc[0].get("fullname", ""),
                "list_date": df.iloc[0].get("list_date", "")
            }
    except Exception as e:
        print(f"获取基本信息失败: {e}")
    return {}


def get_valuation_metrics(code):
    """获取估值指标"""
    try:
        df = pro.daily_basic(ts_code=code)
        if df is not None and not df.empty:
            latest = df.iloc[0]
            return {
                "pe_ttm": latest.get("pe_ttm"),
                "pb": latest.get("pb"),
                "ps_ttm": latest.get("ps_ttm"),
                "dv_ttm": latest.get("dv_ttm"),
                "total_mv": latest.get("total_mv"),
                "circ_mv": latest.get("circ_mv")
            }
    except Exception as e:
        print(f"获取估值指标失败: {e}")
    return {}


def get_industry_comparison(code, industry):
    """获取行业估值对比"""
    try:
        if not industry:
            return {}
        
        # 获取同行业公司
        industry_stocks = pro.stock_basic(industry=industry)
        if industry_stocks is None or industry_stocks.empty:
            return {}
        
        # 取前20家获取估值数据
        codes = industry_stocks["ts_code"].head(20).tolist()
        
        pe_list = []
        pb_list = []
        
        for c in codes:
            try:
                df = pro.daily_basic(ts_code=c)
                if df is not None and not df.empty:
                    pe = df.iloc[0].get("pe_ttm")
                    pb = df.iloc[0].get("pb")
                    if pe and pe > 0 and pe < 500:  # 过滤异常值
                        pe_list.append(pe)
                    if pb and pb > 0 and pb < 50:
                        pb_list.append(pb)
            except:
                continue
        
        if pe_list and pb_list:
            return {
                "industry_name": industry,
                "pe_avg": sum(pe_list) / len(pe_list),
                "pe_median": sorted(pe_list)[len(pe_list)//2],
                "pb_avg": sum(pb_list) / len(pb_list),
                "pb_median": sorted(pb_list)[len(pb_list)//2],
                "sample_size": len(pe_list)
            }
    except Exception as e:
        print(f"获取行业对比失败: {e}")
    return {}


def detect_concepts(basic_info):
    """检测公司涉及的概念题材"""
    name = basic_info.get("name", "")
    fullname = basic_info.get("fullname", "")
    industry = basic_info.get("industry", "")
    
    text = f"{name} {fullname} {industry}"
    
    detected = []
    for concept, keywords in CONCEPT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                detected.append({
                    "concept": concept,
                    "keyword": keyword,
                    "relevance": "直接关联" if keyword in name else "间接关联"
                })
                break
    
    return detected


def print_valuation_report(code, basic_info, valuation, industry, concepts, case):
    """打印估值预期分析报告"""
    
    print("\n---")
    print("🔍 估值预期分析 - 高PE/PB背后的市场预期")
    print("---")
    
    # 公司信息
    print(f"\n【公司信息】")
    print(f"  股票代码: {code}")
    print(f"  公司名称: {basic_info.get('name', 'N/A')}")
    print(f"  所属行业: {basic_info.get('industry', 'N/A')}")
    
    # 估值指标
    print(f"\n【估值指标】")
    pe = valuation.get("pe_ttm")
    pb = valuation.get("pb")
    mv = valuation.get("total_mv")
    
    if pe:
        print(f"  PE-TTM: {pe:.2f}")
    if pb:
        print(f"  PB: {pb:.2f}")
    if mv:
        print(f"  总市值: {mv/10000:.2f}亿元")
    
    # 行业对比
    if industry and industry.get("pe_avg"):
        print(f"\n【行业对比 - {industry.get('industry_name', 'N/A')}】")
        print(f"  样本数量: {industry.get('sample_size', 0)}家")
        
        pe_avg = industry["pe_avg"]
        pe_median = industry["pe_median"]
        print(f"  行业PE平均: {pe_avg:.2f}")
        print(f"  行业PE中位数: {pe_median:.2f}")
        
        if pe:
            pe_premium = (pe - pe_avg) / pe_avg * 100
            print(f"  公司PE: {pe:.2f}")
            print(f"  估值溢价: {pe_premium:+.1f}%")
            
            if pe_premium > 100:
                print(f"  ⚠️ 估值显著高于行业平均，存在重大转型/题材溢价")
            elif pe_premium > 50:
                print(f"  ⚠️ 估值高于行业平均，存在转型/题材溢价")
            elif pe_premium > 20:
                print(f"  → 估值略高于行业平均，可能有成长性溢价")
            elif pe_premium < -20:
                print(f"  ✓ 估值低于行业平均，可能存在低估")
    
    # 概念题材
    if concepts:
        print(f"\n【概念题材映射】")
        for c in concepts:
            print(f"  • {c['concept']} ({c['relevance']})")
    
    # 案例分析
    if case:
        print(f"\n【转型叙事分析】")
        print(f"  传统业务: {case.get('traditional_business', 'N/A')}")
        print(f"  转型方向: {case.get('transformation_narrative', 'N/A')}")
        print(f"  投资类型: {case.get('investment_type', 'N/A')}")
        
        print(f"\n  市场预期拆解:")
        print(f"  {'='*60}")
        for i, exp in enumerate(case.get("key_expectations", []), 1):
            print(f"\n  【预期{i}】{exp.get('type', 'N/A')}")
            print(f"    内容: {exp.get('content', 'N/A')}")
            print(f"    催化剂: {exp.get('catalyst', 'N/A')}")
            print(f"    兑现概率: {exp.get('probability', 'N/A')}")
            print(f"    风险点: {exp.get('risk', 'N/A')}")
        
        print(f"\n  {'='*60}")
        print(f"  估值逻辑:")
        print(f"    {case.get('valuation_logic', 'N/A')}")
    else:
        # 通用分析框架
        print(f"\n【估值分析框架】")
        print(f"  高PE/PB可能的支撑逻辑：")
        print(f"  1. 业务转型预期（传统→新兴赛道）")
        print(f"  2. 资产重组预期（资产注入、并购）")
        print(f"  3. 技术突破预期（固态电池、AI等）")
        print(f"  4. 供应链卡位预期（特斯拉、华为等）")
        print(f"  5. 业绩爆发预期（新产品放量）")
        print(f"\n  建议：通过网络搜索获取公司最新转型动态")
    
    print("\n---")


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python3 market_expectation.py <股票代码>")
        print("示例: python3 market_expectation.py 000559.SZ")
        print("      python3 market_expectation.py 000559")
        sys.exit(1)
    
    code = sys.argv[1]
    
    # 标准化代码格式
    if not (code.endswith('.SZ') or code.endswith('.SH') or code.endswith('.BJ')):
        if code.startswith('6'):
            code = code + '.SH'
        elif code.startswith('8') or code.startswith('4'):
            code = code + '.BJ'
        else:
            code = code + '.SZ'
    
    print(f"正在分析 {code} 的估值预期...")
    
    # 获取数据
    basic_info = get_basic_info(code)
    valuation = get_valuation_metrics(code)
    industry = get_industry_comparison(code, basic_info.get("industry", ""))
    concepts = detect_concepts(basic_info)
    case = TRANSFORMATION_CASES.get(code)
    
    # 打印报告
    print_valuation_report(code, basic_info, valuation, industry, concepts, case)


if __name__ == "__main__":
    main()
