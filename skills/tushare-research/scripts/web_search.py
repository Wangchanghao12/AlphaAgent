#!/usr/bin/env python3
"""
网络搜索统一接口
封装 kimi_search 模块，提供简化的搜索 API

支持：
- 股票/公司相关新闻搜索
- 行业/概念搜索
- 财报/公告搜索
- 宏观经济新闻搜索
"""
import os
import sys
from typing import List, Dict, Optional

# 导入 kimi_search 模块
from kimi_search import kimi_search, moonshot_search, brave_search, duckduckgo_search, searxng_search


def search_news(stock_code: str, stock_name: str, limit: int = 10) -> List[Dict]:
    """
    搜索股票相关新闻
    
    参数:
        stock_code: 股票代码（如 600519）
        stock_name: 股票名称（如 贵州茅台）
        limit: 返回结果数量
    
    返回:
        新闻搜索结果列表
    """
    queries = [
        f"{stock_name} {stock_code} 最新新闻",
        f"{stock_name} 公司公告",
        f"{stock_name} 业绩 财报",
    ]
    
    all_results = []
    for query in queries:
        results = kimi_search(query, limit=limit // len(queries))
        all_results.extend(results)
    
    # 去重（基于 URL）
    seen_urls = set()
    unique_results = []
    for r in all_results:
        if r.get('url') not in seen_urls:
            seen_urls.add(r.get('url'))
            unique_results.append(r)
    
    return unique_results[:limit]


def search_industry(industry: str, limit: int = 5) -> List[Dict]:
    """
    搜索行业相关新闻/分析
    
    参数:
        industry: 行业名称
        limit: 返回结果数量
    
    返回:
        搜索结果列表
    """
    queries = [
        f"{industry} 行业分析 2024 2025",
        f"{industry} 发展趋势",
        f"{industry} 市场规模",
    ]
    
    all_results = []
    for query in queries:
        results = kimi_search(query, limit=limit // len(queries))
        all_results.extend(results)
    
    return all_results[:limit]


def search_concept(concept: str, limit: int = 5) -> List[Dict]:
    """
    搜索概念板块相关信息
    
    参数:
        concept: 概念名称（如 AI、芯片、新能源）
        limit: 返回结果数量
    
    返回:
        搜索结果列表
    """
    query = f"{concept} 概念板块 龙头股 最新"
    return kimi_search(query, limit=limit)


def search_macro(topic: str, limit: int = 5) -> List[Dict]:
    """
    搜索宏观经济新闻/数据
    
    参数:
        topic: 宏观主题（如 GDP、CPI、利率）
        limit: 返回结果数量
    
    返回:
        搜索结果列表
    """
    queries = [
        f"中国 {topic} 最新数据",
        f"{topic} 经济分析 2024 2025",
    ]
    
    all_results = []
    for query in queries:
        results = kimi_search(query, limit=limit // len(queries))
        all_results.extend(results)
    
    return all_results[:limit]


def search_company_info(company_name: str, info_type: str = "general", limit: int = 5) -> List[Dict]:
    """
    搜索公司信息
    
    参数:
        company_name: 公司名称
        info_type: 信息类型 (general/competitors/products/financial)
        limit: 返回结果数量
    
    返回:
        搜索结果列表
    """
    query_map = {
        'general': f"{company_name} 公司简介 主营业务",
        'competitors': f"{company_name} 竞争对手 市场竞争",
        'products': f"{company_name} 主要产品 核心业务",
        'financial': f"{company_name} 财务状况 盈利能力",
    }
    
    query = query_map.get(info_type, query_map['general'])
    return kimi_search(query, limit=limit)


if __name__ == '__main__':
    # 测试
    print("=" * 60)
    print("网络搜索模块测试")
    print("=" * 60)
    
    # 测试1: 搜索股票新闻
    print("\n【测试 1】搜索股票新闻：贵州茅台")
    results = search_news("600519", "贵州茅台", limit=3)
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}")
        print(f"   {r['url']}")
        print()
    
    # 测试 2: 搜索行业信息
    print("\n【测试 2】搜索行业信息：白酒")
    results = search_industry("白酒", limit=3)
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}")
        print(f"   {r['snippet'][:80]}...")
        print()
    
    # 测试 3: 搜索公司信息
    print("\n【测试 3】搜索公司信息：宁德时代")
    results = search_company_info("宁德时代", info_type="products", limit=3)
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}")
        print(f"   {r['snippet'][:80]}...")
        print()
