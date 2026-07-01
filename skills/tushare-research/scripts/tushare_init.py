#!/usr/bin/env python3
"""
Tushare 初始化工具 - 统一加载 token
"""
import os
import re
import tushare as ts

def init_tushare():
    """初始化 Tushare，返回 pro 对象"""
    def load_token_from_bashrc():
        """从 ~/.bashrc 加载 TUSHARE_TOKEN"""
        token = os.environ.get("TUSHARE_TOKEN", "")
        if token:
            return token
        
        bashrc_path = os.path.expanduser("~/.bashrc")
        if os.path.exists(bashrc_path):
            try:
                with open(bashrc_path, 'r') as f:
                    content = f.read()
                    match = re.search(r'export\s+TUSHARE_TOKEN=["\']([^"\']+)["\']', content)
                    if match:
                        return match.group(1)
            except:
                pass
        return ""
    
    token = load_token_from_bashrc()
    if token:
        ts.set_token(token)
    return ts.pro_api()

# 兼容旧代码
pro = init_tushare()
