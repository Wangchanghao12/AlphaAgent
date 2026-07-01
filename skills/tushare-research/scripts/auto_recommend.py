#!/usr/bin/env python3
"""
自动股票推荐系统 - 从中证500+中证1000中随机选择
"""
import os
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 配置
WORKSPACE = "/root/.openclaw/workspace/skills/tushare-research"
STOCK_POOL_FILE = f"{WORKSPACE}/data/stock_pool_zz500_zz1000.json"
RECOMMENDED_FILE = f"{WORKSPACE}/data/recommended_stocks.json"
CACHE_EXPIRY_HOURS = 168  # 股票池缓存7天（168小时）
SCORE_THRESHOLD = 50  # 谨慎看好最低分

def get_tushare_token():
    """获取Tushare Token"""
    # 优先从环境变量获取
    token = os.environ.get('TUSHARE_TOKEN', '')
    if token:
        return token
    # 备用token（从.bashrc中读取）
    return "e7ddc5aa8def10756221267f73308d60738cfa1e2d30483d7e17d178"

def fetch_index_stocks(index_code):
    """从Tushare获取指数成分股"""
    try:
        import tushare as ts
        token = get_tushare_token()
        if not token:
            print("⚠️ 未配置TUSHARE_TOKEN，使用默认股票池")
            return []
        
        ts.set_token(token)
        pro = ts.pro_api()
        
        # 获取指数成分股
        df = pro.index_weight(index_code=index_code)
        if df is not None and not df.empty:
            # 格式化为带后缀的代码
            stocks = []
            for _, row in df.iterrows():
                code = row['con_code']
                # 检查是否已经带有后缀
                if '.SH' in code or '.SZ' in code:
                    stocks.append(code)
                elif code.startswith('6'):
                    stocks.append(f"{code}.SH")
                else:
                    stocks.append(f"{code}.SZ")
            return list(set(stocks))  # 去重
        return []
    except Exception as e:
        print(f"⚠️ 获取指数{index_code}成分股失败: {e}")
        return []

def build_stock_pool():
    """构建中证500+中证1000的股票池"""
    print("正在从中证500和中证1000获取股票池...")
    
    # 中证500: 000905.SH, 中证1000: 000852.SH
    zz500 = fetch_index_stocks('000905.SH')
    zz1000 = fetch_index_stocks('000852.SH')
    
    # 合并并去重
    all_stocks = list(set(zz500 + zz1000))
    
    if not all_stocks:
        print("⚠️ 无法获取指数成分股，使用备用股票池")
        return get_fallback_pool()
    
    print(f"✅ 成功获取 {len(all_stocks)} 只股票（中证500: {len(zz500)}, 中证1000: {len(zz1000)}）")
    
    # 缓存到文件
    os.makedirs(os.path.dirname(STOCK_POOL_FILE), exist_ok=True)
    with open(STOCK_POOL_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            "stocks": all_stocks,
            "zz500_count": len(zz500),
            "zz1000_count": len(zz1000),
            "total": len(all_stocks),
            "updated_at": datetime.now().isoformat()
        }, f, ensure_ascii=False, indent=2)
    
    return all_stocks

def get_fallback_pool():
    """备用股票池（当API失败时使用）"""
    return [
        "000938.SZ", "002230.SZ", "002371.SZ", "002415.SZ", "300014.SZ",
        "300033.SZ", "300059.SZ", "300124.SZ", "300274.SZ", "300408.SZ",
        "300413.SZ", "300433.SZ", "300750.SZ", "300760.SZ", "300782.SZ",
        "600009.SH", "600036.SH", "600276.SH", "600309.SH", "600406.SH",
        "600438.SH", "600519.SH", "600570.SH", "600585.SH", "600588.SH",
        "600690.SH", "600745.SH", "600809.SH", "600887.SH", "601012.SH",
        "601066.SH", "601088.SH", "601138.SH", "601211.SH", "601288.SH",
        "601318.SH", "601398.SH", "601601.SH", "601628.SH", "601633.SH",
        "601658.SH", "601668.SH", "601688.SH", "601766.SH", "601857.SH",
        "601888.SH", "601899.SH", "601995.SH", "603019.SH", "603259.SH",
        "603288.SH", "603501.SH", "603659.SH", "603986.SH", "688036.SH",
        "688111.SH", "688169.SH", "688187.SH", "688223.SH", "688271.SH",
        "688981.SH", "688599.SH"
    ]

def load_stock_pool():
    """加载股票池（带缓存）"""
    # 检查缓存是否存在且未过期
    if os.path.exists(STOCK_POOL_FILE):
        try:
            with open(STOCK_POOL_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 检查缓存时间
            updated_at = datetime.fromisoformat(data.get('updated_at', '2000-01-01'))
            if datetime.now() - updated_at < timedelta(hours=CACHE_EXPIRY_HOURS):
                print(f"✅ 使用缓存股票池（共 {len(data['stocks'])} 只，缓存于 {updated_at.strftime('%m-%d %H:%M')}）")
                return data['stocks']
            else:
                print("🔄 股票池缓存已过期，重新获取...")
        except Exception as e:
            print(f"⚠️ 读取缓存失败: {e}，重新获取...")
    
    # 重新构建股票池
    return build_stock_pool()

def load_recommended():
    """加载已推荐的股票列表"""
    if os.path.exists(RECOMMENDED_FILE):
        with open(RECOMMENDED_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"stocks": [], "last_update": datetime.now().isoformat()}

def save_recommended(data):
    """保存已推荐的股票列表"""
    os.makedirs(os.path.dirname(RECOMMENDED_FILE), exist_ok=True)
    with open(RECOMMENDED_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_available_stocks():
    """获取未推荐过的股票"""
    pool = load_stock_pool()
    recommended = load_recommended()
    recommended_codes = {s["code"] for s in recommended.get("stocks", [])}
    
    available = [s for s in pool if s not in recommended_codes]
    
    # 如果全部推荐完了，清空列表重新开始
    if not available:
        print("🔄 所有股票已推荐一轮，清空记录重新开始")
        recommended["stocks"] = []
        save_recommended(recommended)
        available = pool
    
    return available

def pick_random_stocks(count=10):
    """随机选择N支候选股票"""
    available = get_available_stocks()
    if len(available) <= count:
        return available
    return random.sample(available, count)

def main():
    """主函数 - 输出候选股票列表供Agent分析"""
    candidates = pick_random_stocks(10)
    
    print("=" * 60)
    print(f"自动股票推荐系统 - 候选股票 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    print("股票池来源: 中证500 + 中证1000")
    print("=" * 60)
    
    for i, code in enumerate(candidates, 1):
        print(f"{i}. {code}")
    
    print("\n请依次分析以上候选股票，进行财务+技术面综合评分（10选1）")
    print(f"评分权重：技术面70% + 财务30%")
    print(f"当前阈值: {SCORE_THRESHOLD}分 (谨慎看好)")
    
    # 保存候选到临时文件
    temp_file = f"{WORKSPACE}/data/current_candidates.json"
    os.makedirs(os.path.dirname(temp_file), exist_ok=True)
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump({
            "candidates": candidates,
            "created_at": datetime.now().isoformat()
        }, f, ensure_ascii=False, indent=2)
    
    return candidates

if __name__ == "__main__":
    main()
