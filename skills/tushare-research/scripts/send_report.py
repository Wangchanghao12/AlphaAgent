#!/usr/bin/env python3
"""
研报发送工具 - 带自动防重复功能
用法: python3 send_report.py <stock_code> <report_file>
"""

import sys
import json
import os
from datetime import datetime

SENT_RECORDS_FILE = '/root/.openclaw/workspace/skills/tushare-research/.sent_reports.json'
REPORTS_DIR = '/root/.openclaw/workspace/skills/tushare-research/reports'
CHARTS_DIR = '/root/.openclaw/workspace/skills/tushare-research/charts'

def load_sent_records():
    """加载已发送记录"""
    if not os.path.exists(SENT_RECORDS_FILE):
        return {"sent_reports": [], "last_update": ""}
    with open(SENT_RECORDS_FILE, 'r') as f:
        return json.load(f)

def save_sent_records(filename):
    """保存已发送记录"""
    data = load_sent_records()
    if filename not in data['sent_reports']:
        data['sent_reports'].append(filename)
        data['last_update'] = datetime.now().isoformat()
        with open(SENT_RECORDS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"✅ 已记录: {filename}")
        return True
    return False

def check_already_sent(filename):
    """检查是否已发送"""
    data = load_sent_records()
    return filename in data['sent_reports']

def get_report_info(report_file):
    """获取研报信息"""
    full_path = os.path.join(REPORTS_DIR, report_file)
    if not os.path.exists(full_path):
        return None
    
    # 提取股票代码
    parts = report_file.split('_')
    if len(parts) >= 2:
        stock_code = parts[0]
        # 确定后缀 .SH 或 .SZ
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # 从内容中查找股票代码后缀
            if '.SH' in content[:500] or '上交所' in content[:500]:
                suffix = 'SH'
            elif '.SZ' in content[:500] or '深交所' in content[:500]:
                suffix = 'SZ'
            else:
                suffix = 'SH'  # 默认
        return {
            'stock_code': f"{stock_code}_{suffix}",
            'filename': report_file,
            'full_path': full_path
        }
    return None

def check_kline_exists(stock_code):
    """检查K线图是否存在"""
    kline_path = os.path.join(CHARTS_DIR, f"{stock_code}_kline.png")
    return os.path.exists(kline_path), kline_path

def main():
    if len(sys.argv) < 2:
        print("用法: python3 send_report.py <report_file>")
        sys.exit(1)
    
    report_file = sys.argv[1]
    
    print(f"\n{'='*50}")
    print(f"研报发送检查 - {report_file}")
    print(f"{'='*50}\n")
    
    # 1. 检查是否已发送
    if check_already_sent(report_file):
        print(f"❌ 该研报已在发送记录中，跳过")
        sys.exit(0)
    
    # 2. 获取研报信息
    info = get_report_info(report_file)
    if not info:
        print(f"❌ 研报文件不存在: {report_file}")
        sys.exit(1)
    
    print(f"✅ 研报文件存在: {info['full_path']}")
    print(f"   股票代码: {info['stock_code']}")
    
    # 3. 检查K线图
    kline_exists, kline_path = check_kline_exists(info['stock_code'])
    if not kline_exists:
        print(f"❌ K线图不存在: {kline_path}")
        sys.exit(1)
    print(f"✅ K线图存在: {kline_path}")
    
    # 4. 发送前确认
    print(f"\n{'='*50}")
    print("所有检查通过，准备发送...")
    print(f"{'='*50}\n")
    
    print("请使用以下命令发送:")
    print(f"1. 发送K线图:")
    print(f"   message action=\"send\" channel=\"feishu\" target=\"ou_1a07d889dfd5d81481d1be521258a92a\" filePath=\"{kline_path}\"")
    print(f"\n2. 发送研报文件:")
    print(f"   message action=\"send\" channel=\"feishu\" target=\"ou_1a07d889dfd5d81481d1be521258a92a\" filePath=\"{info['full_path']}\"")
    print(f"\n3. 发送后记录:")
    print(f"   python3 send_report.py --record {report_file}")
    
    return info['stock_code'], kline_path, info['full_path']

if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == '--record':
        # 仅记录，不发送
        save_sent_records(sys.argv[2])
    else:
        main()
