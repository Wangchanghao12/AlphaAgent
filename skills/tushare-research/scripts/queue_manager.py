#!/usr/bin/env python3
"""
研报发送队列管理
- 生成任务将研报加入队列
- 推送任务消费队列
- 发送失败保留在队列，下次重试
- 发送成功从队列移除并记录到已发送
"""

import json
import os
from datetime import datetime
from pathlib import Path

QUEUE_FILE = Path(__file__).parent.parent / ".send_queue.json"
SENT_FILE = Path(__file__).parent.parent / ".sent_reports.json"

def load_queue():
    """加载待发送队列"""
    if QUEUE_FILE.exists():
        try:
            with open(QUEUE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {"queue": [], "last_update": ""}
    return {"queue": [], "last_update": ""}

def save_queue(data):
    """保存队列"""
    data["last_update"] = datetime.now().isoformat()
    with open(QUEUE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_sent():
    """加载已发送记录"""
    if SENT_FILE.exists():
        try:
            with open(SENT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {"sent_reports": [], "last_update": ""}
    return {"sent_reports": [], "last_update": ""}

def add_to_queue(report_filename):
    """将研报加入待发送队列"""
    queue_data = load_queue()
    sent_data = load_sent()
    
    # 双重检查：不在队列中且未发送过
    if report_filename in queue_data["queue"]:
        print(f"⚠️ 已在队列中: {report_filename}")
        return False
    
    if report_filename in sent_data["sent_reports"]:
        print(f"✅ 已发送过: {report_filename}")
        return False
    
    queue_data["queue"].append(report_filename)
    save_queue(queue_data)
    print(f"✅ 已加入队列: {report_filename}")
    return True

def pop_from_queue():
    """从队列取出一个待发送研报（FIFO）"""
    queue_data = load_queue()
    sent_data = load_sent()
    
    # 跳过已发送的（防止重复）
    while queue_data["queue"]:
        report = queue_data["queue"].pop(0)
        if report not in sent_data["sent_reports"]:
            save_queue(queue_data)
            return report
        print(f"⚠️ 跳过已发送: {report}")
    
    save_queue(queue_data)
    return None

def get_queue_status():
    """获取队列状态"""
    queue_data = load_queue()
    sent_data = load_sent()
    
    # 过滤掉已发送的
    pending = [r for r in queue_data["queue"] if r not in sent_data["sent_reports"]]
    
    # 清理已发送的记录
    if len(pending) != len(queue_data["queue"]):
        queue_data["queue"] = pending
        save_queue(queue_data)
    
    return {
        "pending_count": len(pending),
        "pending_reports": pending,
        "total_sent": len(sent_data["sent_reports"])
    }

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        # 显示队列状态
        status = get_queue_status()
        print(f"📋 队列状态:")
        print(f"   待发送: {status['pending_count']} 份")
        print(f"   已发送: {status['total_sent']} 份")
        if status['pending_reports']:
            print(f"   队列内容: {', '.join(status['pending_reports'][:5])}")
            if len(status['pending_reports']) > 5:
                print(f"   ... 等共 {len(status['pending_reports'])} 份")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "--add" and len(sys.argv) >= 3:
        # 添加研报到队列
        report = sys.argv[2]
        success = add_to_queue(report)
        sys.exit(0 if success else 1)
    
    elif cmd == "--pop":
        # 取出一个研报
        report = pop_from_queue()
        if report:
            print(report)
            sys.exit(0)
        else:
            print("队列为空")
            sys.exit(1)
    
    elif cmd == "--status":
        # 显示状态
        status = get_queue_status()
        print(json.dumps(status, ensure_ascii=False, indent=2))
        sys.exit(0)
    
    else:
        print("用法:")
        print(f"  {sys.argv[0]}                    # 显示状态")
        print(f"  {sys.argv[0]} --add 研报文件名    # 添加研报到队列")
        print(f"  {sys.argv[0]} --pop               # 取出一个研报")
        print(f"  {sys.argv[0]} --status            # 详细状态(JSON)")
        sys.exit(1)
