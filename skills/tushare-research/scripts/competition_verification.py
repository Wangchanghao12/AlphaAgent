#!/usr/bin/env python3
"""
竞争格局验证助手 - 生成需要网络搜索验证的关键问题清单

使用方法：
1. 先运行业务分析脚本获取财务指标
2. 运行此脚本生成验证问题清单
3. 根据清单进行网络搜索
4. 结合搜索结果修正竞争分析结论

示例：
    python3 scripts/competition_verification.py 688205.SH
"""
import sys
import os
import tushare as ts

_token = (os.environ.get('TUSHARE_TOKEN') or '').strip()
pro = ts.pro_api(_token) if _token else ts.pro_api()


def generate_verification_checklist(ts_code):
    """生成竞争分析验证清单"""
    
    print("---")
    print(f"🔍 竞争格局验证清单 - {ts_code}")
    print("---")
    
    # 获取基本信息
    try:
        basic = pro.stock_basic(ts_code=ts_code, fields='name,industry')
        if not basic.empty:
            company_name = basic.iloc[0]['name']
            industry = basic.iloc[0]['industry']
        else:
            company_name = ts_code
            industry = "未知"
    except:
        company_name = ts_code
        industry = "未知"
    
    print(f"\n【公司信息】")
    print(f"  公司名称: {company_name}")
    print(f"  股票代码: {ts_code}")
    print(f"  所属行业: {industry}")
    
    # 必查信息清单
    print(f"\n---")
    print("📋 必查信息清单（按优先级排序）")
    print("---")
    
    print(f"\n【第一优先级：确定竞争关系】")
    print(f"  □ 1. 查阅招股说明书")
    print(f"     - 历史沿革：是否有大股东/关联方背景？")
    print(f"     - 前五大客户：客户是谁？占比多少？")
    print(f"     - 前五大供应商：供应商是谁？占比多少？")
    print(f"     - 对标企业：公司明确提及的竞争对手是谁？")
    print(f"  ")
    print(f"  搜索关键词建议：")
    print(f"    • \"{company_name} {ts_code.split('.')[0]} 招股说明书\"")
    print(f"    • \"{company_name} 前五大客户\"")
    print(f"    • \"{company_name} 竞争对手\"")
    
    print(f"\n【第二优先级：验证产业链位置】")
    print(f"  □ 2. 确认产业链位置")
    print(f"     - 上游：原材料/零部件供应商？")
    print(f"     - 中游：器件/模块制造商？")
    print(f"     - 下游：设备集成商/终端客户？")
    print(f"  ")
    print(f"  搜索关键词建议：")
    print(f"    • \"{company_name} 主营业务 产业链\"")
    print(f"    • \"{company_name} 产品 应用\"")
    print(f"    • \"{industry} 产业链结构\"")
    
    print(f"\n【第三优先级：识别真实竞争对手】")
    print(f"  □ 3. 找到直接竞争对手")
    print(f"     - 同行业同细分领域公司")
    print(f"     - 产品可相互替代的公司")
    print(f"     - 客户重叠度高的公司")
    print(f"  ")
    print(f"  搜索关键词建议：")
    print(f"    • \"{company_name} vs [竞争对手] 对比\"")
    print(f"    • \"{industry} 龙头企业\"")
    print(f"    • \"{industry} 竞争格局\"")
    
    print(f"\n【第四优先级：评估可替代性】")
    print(f"  □ 4. 验证客户粘性")
    print(f"     - 客户认证周期多长？")
    print(f"     - 是否有长期合同？")
    print(f"     - 切换供应商的成本？")
    print(f"  □ 5. 验证技术壁垒")
    print(f"     - 核心技术是什么？")
    print(f"     - 专利数量/质量？")
    print(f"     - 技术是否容易被模仿？")
    print(f"  ")
    print(f"  搜索关键词建议：")
    print(f"    • \"{company_name} 核心技术 专利\"")
    print(f"    • \"{company_name} 客户 认证\"")
    print(f"    • \"{industry} 技术壁垒\"")
    
    # 生成搜索关键词组合
    print(f"\n---")
    print("🔎 推荐搜索关键词组合")
    print("---")
    
    keywords = [
        f"{company_name} {ts_code.split('.')[0]} 招股说明书",
        f"{company_name} 主营业务 产品",
        f"{company_name} 客户 供应商",
        f"{company_name} 竞争对手 对标",
        f"{company_name} 中兴通讯 关系" if "通信" in industry else f"{company_name} 行业龙头",
        f"{industry} 竞争格局 市场份额",
        f"{company_name} 产业链 上下游",
        f"{company_name} 核心技术 壁垒",
    ]
    
    for i, kw in enumerate(keywords, 1):
        print(f"  {i}. {kw}")
    
    # 验证框架
    print(f"\n---")
    print("✅ 验证框架：财务指标 → 业务实际 → 修正结论")
    print("---")
    
    print(f"""
【Step 1: 财务指标初步推测】
  • 查看毛利率、ROE、市值排名
  • 初步判断竞争关系类型
  • ⚠️ 注意：这只是推测，不是结论

【Step 2: 网络搜索获取业务信息】
  • 使用上述关键词进行搜索
  • 重点关注招股说明书、公司公告
  • 记录关键发现（客户、供应商、竞争对手）

【Step 3: 验证/修正竞争关系】
  • 财务推测是否与业务实际一致？
  • 如果不一致，以业务实际为准
  • 明确关系类型：直接竞争/上下游/互补/无关

【Step 4: 重新评估可替代性】
  • 结合业务实际评估壁垒
  • 客户集中度 vs 客户粘性
  • 技术壁垒 vs 技术替代风险
  • 形成最终结论
    """)
    
    # 常见陷阱提醒
    print(f"---")
    print("⚠️ 常见陷阱提醒")
    print("---")
    
    print(f"""
1. 【行业分类误导】
   ❌ 陷阱：看到同行业就认为是竞争对手
   ✅ 正确：细分到产业链环节（如器件 vs 设备）
   
2. 【规模对比误导】
   ❌ 陷阱：看到市值差距大就认为是追赶者
   ✅ 正确：先确认是竞争关系还是上下游关系
   
3. 【毛利率误导】
   ❌ 陷阱：毛利率相近就认为是直接竞争
   ✅ 正确：验证产品是否真正重叠
   
4. 【客户名称误导】
   ❌ 陷阱：看到客户重叠就认为是竞争
   ✅ 正确：确认是竞争对手还是共同客户
   
5. 【历史关系忽视】
   ❌ 陷阱：忽视公司历史沿革
   ✅ 正确：查看是否有股权/业务往来历史
    """)
    
    # 输出格式建议
    print(f"---")
    print("📝 分析结论输出格式建议")
    print("---")
    
    print(f"""
【竞争关系结论】
  • 关系类型：[直接竞争/上下游/互补合作/无直接关系]
  • 关系描述：[具体描述，如"德科立是中兴通讯的供应商"]
  • 信息来源：[招股说明书/年报/新闻等]

【真实竞争对手】
  • 主要竞争对手：[列出实际竞争对手]
  • 竞争焦点：[技术/成本/客户等]

【可替代性评估】
  • 评级：[高/中/低]
  • 关键壁垒：[客户认证/技术/规模等]
  • 主要风险：[客户集中/技术替代等]

【数据来源】
  • 财务数据：Tushare Pro API
  • 业务信息：[具体来源，如"德科立招股说明书"]
    """)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 competition_verification.py <股票代码>")
        print("示例: python3 competition_verification.py 688205.SH")
        print("      python3 competition_verification.py 600519.SH")
        sys.exit(1)
    
    ts_code = sys.argv[1]
    generate_verification_checklist(ts_code)
