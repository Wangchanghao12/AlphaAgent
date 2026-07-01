#!/usr/bin/env python3
"""
从研报中提取评分和推荐信息
"""
import sys
import os
import re
import json
from datetime import datetime

WORKSPACE = "/root/.openclaw/workspace/skills/tushare-research"
RECOMMENDED_FILE = f"{WORKSPACE}/data/recommended_stocks.json"

def extract_score_from_report(report_path):
    """从研报文件中提取综合评分"""
    if not os.path.exists(report_path):
        return None, None
    
    with open(report_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 查找综合评分
    score_match = re.search(r'综合评分[：:]\s*(\d+)\s*分', content)
    rating_match = re.search(r'投资评级[：:]\s*([^\n]+)', content)
    
    score = int(score_match.group(1)) if score_match else 0
    rating = rating_match.group(1).strip() if rating_match else "未知"
    
    return score, rating

def extract_stock_code_from_report(report_path):
    """从研报文件名提取股票代码"""
    filename = os.path.basename(report_path)
    match = re.search(r'(\d{6})_(SH|SZ)', filename)
    if match:
        suffix = "SH" if "SH" in filename else "SZ"
        return f"{match.group(1)}.{suffix}"
    return None

def save_recommendation(code, score, rating, report_path):
    """保存推荐记录"""
    os.makedirs(os.path.dirname(RECOMMENDED_FILE), exist_ok=True)
    
    data = {"stocks": [], "last_update": datetime.now().isoformat()}
    if os.path.exists(RECOMMENDED_FILE):
        with open(RECOMMENDED_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    
    data["stocks"].append({
        "code": code,
        "score": score,
        "rating": rating,
        "report_path": report_path,
        "recommended_at": datetime.now().isoformat()
    })
    data["last_update"] = datetime.now().isoformat()
    
    with open(RECOMMENDED_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 已记录推荐: {code}, 评分: {score}分, 评级: {rating}")

def main():
    if len(sys.argv) < 2:
        print("用法: python3 record_recommendation.py <研报文件路径>")
        sys.exit(1)
    
    report_path = sys.argv[1]
    code = extract_stock_code_from_report(report_path)
    
    if not code:
        print(f"❌ 无法从文件名提取股票代码: {report_path}")
        sys.exit(1)
    
    score, rating = extract_score_from_report(report_path)
    
    if score is None:
        print(f"❌ 无法从研报提取评分: {report_path}")
        sys.exit(1)
    
    save_recommendation(code, score, rating, report_path)
    print(f"\n📊 股票: {code}")
    print(f"📊 评分: {score}分")
    print(f"📊 评级: {rating}")

if __name__ == "__main__":
    main()
