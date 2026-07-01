#!/usr/bin/env python3
"""
股票推荐报告生成器 - 生成带核心结论速览的精简报告
"""
import os
import re
import sys
from datetime import datetime

WORKSPACE = "/root/.openclaw/workspace/skills/tushare-research"

def extract_sections(report_path):
    """从完整研报中提取关键章节"""
    if not os.path.exists(report_path):
        return None
    
    with open(report_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    sections = {}
    
    # 提取股票基本信息
    name_match = re.search(r'#\s*(.+?)\s*\(\d+\)', content)
    sections['name'] = name_match.group(1) if name_match else "未知"
    
    code_match = re.search(r'\((\d+)\)', content)
    sections['code'] = code_match.group(1) if code_match else "000000"
    
    # 提取当前价格
    price_match = re.search(r'最新收盘价[：:]\s*([\d.]+)', content)
    sections['price'] = price_match.group(1) if price_match else "N/A"
    
    # 提取投资评级
    rating_match = re.search(r'投资评级[：:]\s*([^\n]+)', content)
    sections['rating'] = rating_match.group(1).strip() if rating_match else "中性"
    
    # 提取综合评分
    score_match = re.search(r'综合评分[：:]\s*(\d+)\s*分', content)
    sections['score'] = score_match.group(1) if score_match else "0"
    
    # 提取核心逻辑
    logic_match = re.search(r'##\s*核心投资逻辑.*?(?=##|\Z)', content, re.DOTALL)
    sections['logic'] = logic_match.group(0) if logic_match else ""
    
    # 提取交易预案
    trade_match = re.search(r'##\s*交易预案.*?(?=##|\Z)', content, re.DOTALL)
    sections['trade'] = trade_match.group(0) if trade_match else ""
    
    # 提取风险提示
    risk_match = re.search(r'##\s*风险提示清单.*?(?=##|\Z)', content, re.DOTALL)
    sections['risks'] = risk_match.group(0) if risk_match else ""
    
    return sections

def generate_summary(report_path, output_path=None):
    """生成核心结论速览"""
    sections = extract_sections(report_path)
    if not sections:
        return None
    
    if output_path is None:
        date_str = datetime.now().strftime('%Y%m%d')
        output_path = f"{WORKSPACE}/reports/summary_{sections['code']}_{date_str}.md"
    
    summary = f"""# 📊 {sections['name']}（{sections['code']}）深度研报

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**当前股价**: {sections['price']}元
**投资评级**: {sections['rating']}
**综合评分**: {sections['score']}分

---

## 📋 核心结论速览

{sections['logic']}

---

## 🎯 交易预案

{sections['trade']}

---

## ⚠️ 风险提示

{sections['risks']}

---

*完整研报详见: {report_path}*
"""
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(summary)
    
    return output_path, summary

def main():
    if len(sys.argv) < 2:
        print("用法: python3 generate_summary.py <完整研报路径> [输出路径]")
        sys.exit(1)
    
    report_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    result = generate_summary(report_path, output_path)
    
    if result:
        path, summary = result
        print(f"✅ 速览报告已生成: {path}")
        print("\n" + "="*60)
        print(summary)
        print("="*60)
    else:
        print("❌ 生成失败")
        sys.exit(1)

if __name__ == "__main__":
    main()
