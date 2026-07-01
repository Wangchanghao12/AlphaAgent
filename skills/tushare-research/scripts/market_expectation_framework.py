#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
估值预期分析框架 - 可复用的分析模块（严谨版）
分析高PE/PB背后的市场预期、转型叙事、概念题材

核心原则：
1. **没有验证，不输出** - 所有预期必须经过外部信息验证
2. **区分"推测"与"确认"** - 明确标注信息来源和可信度
3. **强制查证机制** - 无内置案例时，必须通过网络搜索验证

分析流程：
Step 1: 估值溢价识别（数据层）
Step 2: 概念题材初筛（关键词匹配）
Step 3: **外部信息验证**（网络搜索/公告/研报）⚠️ 关键步骤
Step 4: 市场预期拆解（仅输出验证后的信息）
Step 5: 投资类型判断

使用场景：
1. 当股票PE/PB显著高于行业平均时，挖掘背后的市场预期
2. 区分"价值投资"与"主题投资"
3. 评估估值透支程度与预期兑现风险
"""

import sys
import os
import json
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

# 尝试导入tushare
try:
    import tushare as ts
    pro = ts.pro_api()
    TUSHARE_AVAILABLE = True
except:
    TUSHARE_AVAILABLE = False
    pro = None


# =============================================================================
# 1. 概念题材知识库（仅用于初筛，不作为最终结论）
# =============================================================================

CONCEPT_KEYWORDS = {
    "人形机器人": {
        "keywords": ["机器人", "丝杠", "轴承", "关节", "减速器", "执行器", "Optimus", "特斯拉机器人", "人形"],
        "requires_verification": True,
        "verification_sources": ["公司公告", "投资者互动", "供应链新闻"]
    },
    "固态电池": {
        "keywords": ["固态电池", "硫化物", "聚合物", "电解质", "能量密度", "凝聚态"],
        "requires_verification": True,
        "verification_sources": ["公司公告", "专利信息", "技术合作新闻"]
    },
    "新能源汽车": {
        "keywords": ["新能源", "电动车", "锂电池", "动力电池", "电机", "电控", "三电"],
        "requires_verification": True,
        "verification_sources": ["公司公告", "客户订单", "产能新闻"]
    },
    "AI/人工智能": {
        "keywords": ["AI", "人工智能", "大模型", "算力", "芯片", "智驾", "自动驾驶"],
        "requires_verification": True,
        "verification_sources": ["公司公告", "技术合作", "产品发布"]
    },
    "低空经济": {
        "keywords": ["低空", "飞行汽车", "eVTOL", "无人机", "航空", "通航"],
        "requires_verification": True,
        "verification_sources": ["公司公告", "适航认证", "订单新闻"]
    },
    "国企改革": {
        "keywords": ["重组", "资产注入", "集团", "混改", "央企", "国资", "壳资源"],
        "requires_verification": True,
        "verification_sources": ["公司公告", "集团动态", "监管批复"]
    },
    "华为链": {
        "keywords": ["华为", "鸿蒙", "问界", "智选", "供应商", "海思"],
        "requires_verification": True,
        "verification_sources": ["公司公告", "供应链新闻", "华为发布会"]
    },
    "特斯拉链": {
        "keywords": ["特斯拉", "Tesla", "Optimus", "Cybertruck", "上海工厂", "马斯克"],
        "requires_verification": True,
        "verification_sources": ["公司公告", "供应链新闻", "特斯拉财报"]
    },
    "储能": {
        "keywords": ["储能", "逆变器", "光伏", "风电", "电网", "虚拟电厂"],
        "requires_verification": True,
        "verification_sources": ["公司公告", "订单新闻", "项目投产"]
    },
    "半导体": {
        "keywords": ["芯片", "半导体", "晶圆", "光刻", "封测", "EDA", "设备", "材料"],
        "requires_verification": True,
        "verification_sources": ["公司公告", "客户认证", "产能新闻"]
    }
}


# =============================================================================
# 2. 已验证案例库（经过严格查证的公司）
# =============================================================================

VERIFIED_CASES = {
    "000559.SZ": {
        "name": "万向钱潮",
        "verification_status": "已验证",
        "verification_sources": [
            "2025年4月28日互动易：公司在人形机器人方面重点布局精密轴承和丝杠",
            "2025年7月9日投资者关系活动记录表：与特斯拉Optimus团队接洽",
            "2024年12月25日互动易：万向一二三固态电池技术路线覆盖硫化物与聚合物",
            "2024年5月6日公告：重大资产重组进行中"
        ],
        "traditional_business": "汽车零部件（万向节、轮毂轴承）",
        "traditional_valuation": "PE 15-20倍",
        "transformation_narrative": "从传统汽配向'机器人+新能源+智能底盘'转型",
        "verified_expectations": [
            {
                "type": "business_transformation",
                "name": "人形机器人",
                "content": "切入特斯拉Optimus供应链，精密轴承+丝杠供应商",
                "evidence": [
                    "互动易确认：产品处于开发验证阶段",
                    "投资者调研：已具备10万套滚柱丝杠年产能",
                    "计划2026年建成120万套机器人专用轴承产能"
                ],
                "catalyst": "2026年产能120万套",
                "timeline": "2026年",
                "probability": "中",
                "impact": "高",
                "risk": "特斯拉量产推迟；竞争加剧（三花、拓普更强）",
                "valuation_contribution": "机器人业务PE 40-50倍",
                "confidence": "中高（有官方确认）"
            },
            {
                "type": "supply_chain_positioning",
                "name": "固态电池",
                "content": "参股万向一二三10.74%，布局硫化物/聚合物双路线",
                "evidence": [
                    "互动易确认：万向一二三固态电池技术路线覆盖硫化物与聚合物",
                    "已研制出能量密度350Wh/kg固态电池样件",
                    "万向一二三估值400亿+，上市辅导中"
                ],
                "catalyst": "2026年小批量生产",
                "timeline": "2026-2027年",
                "probability": "中",
                "impact": "中高",
                "risk": "技术路线不确定；量产进度不及预期",
                "valuation_contribution": "万向一二三账面增值200%+",
                "confidence": "中高（有官方确认）"
            },
            {
                "type": "asset_restructuring",
                "name": "资产重组",
                "content": "收购万向集团优质资产进行中",
                "evidence": [
                    "2024年5月6日公告：重大资产重组",
                    "投资者关系活动：尽职调查、审计、评估进行中"
                ],
                "catalyst": "资产注入增厚业绩",
                "timeline": "待定",
                "probability": "中高",
                "impact": "中高",
                "risk": "时间不确定；注入资产质量待验证",
                "valuation_contribution": "业绩增厚+资产重估",
                "confidence": "中（有公告确认，但细节待定）"
            }
        ],
        "unverified_rumors": [
            {
                "content": "与特斯拉达成独家供应协议",
                "status": "未证实",
                "note": "仅市场传闻，公司未确认"
            }
        ],
        "valuation_logic": "传统业务PE 15-20倍 + 机器人业务PE 40-50倍 + 固态电池资产重估",
        "investment_type": "主题投资（非价值投资）",
        "key_monitoring_points": [
            "特斯拉Optimus量产进度",
            "万向一二三上市进展",
            "资产重组公告",
            "机器人业务订单"
        ],
        "last_updated": "2026-03-03"
    }
}


# =============================================================================
# 3. 核心分析类（严谨版）
# =============================================================================

class ValuationExpectationAnalyzer:
    """
    估值预期分析器（严谨版）
    
    核心原则：没有验证，不输出
    """
    
    def __init__(self):
        self.concept_db = CONCEPT_KEYWORDS
        self.verified_cases = VERIFIED_CASES
        
    def analyze(self, code: str, name: str = "", industry: str = "", 
                pe: float = None, pb: float = None, 
                industry_pe: float = None, industry_pb: float = None,
                skip_verification: bool = False,
                **kwargs) -> Dict[str, Any]:
        """
        执行完整的估值预期分析
        
        Args:
            code: 股票代码
            name: 公司名称
            industry: 所属行业
            pe: 当前PE
            pb: 当前PB
            industry_pe: 行业平均PE
            industry_pb: 行业平均PB
            skip_verification: 是否跳过验证（仅用于测试）
            **kwargs: 其他可选参数
            
        Returns:
            完整的估值预期分析报告
        """
        # 1. 估值溢价分析（数据层，无需验证）
        valuation_analysis = self._analyze_valuation_premium(
            pe=pe, pb=pb, 
            industry_pe=industry_pe, 
            industry_pb=industry_pb
        )
        
        # 2. 检查是否有已验证案例
        verified_case = self.verified_cases.get(code)
        
        if verified_case:
            # 使用已验证案例
            transformation = self._get_verified_transformation(verified_case)
            expectations = verified_case.get("verified_expectations", [])
            unverified = verified_case.get("unverified_rumors", [])
            verification_status = "已验证"
        else:
            # 无验证案例，必须进行外部查证
            if not skip_verification:
                transformation = {
                    "status": "未验证",
                    "message": "⚠️ 无内置验证案例，必须通过网络搜索/公告核实",
                    "traditional_business": f"{industry}传统业务（待验证）",
                    "transformation_narrative": "待查证",
                    "action_required": "请运行网络搜索验证以下信息：",
                    "verification_checklist": self._generate_verification_checklist(code, name, industry)
                }
                expectations = []
                unverified = []
                verification_status = "未验证"
            else:
                # 测试模式：仅输出概念初筛结果
                transformation = {
                    "status": "测试模式（跳过验证）",
                    "message": "⚠️ 当前为测试模式，信息未经验证"
                }
                expectations = []
                unverified = []
                verification_status = "测试模式"
        
        # 3. 概念题材初筛（仅作为查证线索，不作为结论）
        concept_clues = self._detect_concept_clues(name, industry)
        
        # 4. 投资类型判断
        investment_type = self._classify_investment_type(
            valuation_analysis, verified_case is not None
        )
        
        return {
            "code": code,
            "name": name,
            "industry": industry,
            "verification_status": verification_status,
            "valuation": {
                "pe": pe,
                "pb": pb,
                "industry_pe": industry_pe,
                "industry_pb": industry_pb,
                **valuation_analysis
            },
            "concept_clues": concept_clues,  # 仅作为查证线索
            "transformation": transformation,
            "expectations": expectations,  # 仅输出验证后的预期
            "unverified_rumors": unverified,  # 明确标注未证实传闻
            "investment_type": investment_type,
            "disclaimer": "本分析基于公开信息，投资有风险，决策需谨慎",
            "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    
    def _analyze_valuation_premium(self, pe: float = None, pb: float = None,
                                   industry_pe: float = None, 
                                   industry_pb: float = None) -> Dict:
        """分析估值溢价/折价（纯数据计算，无需验证）"""
        result = {
            "pe_premium_pct": None,
            "pb_premium_pct": None,
            "premium_level": "unknown",
            "interpretation": ""
        }
        
        if pe and industry_pe and industry_pe > 0:
            pe_premium = (pe - industry_pe) / industry_pe * 100
            result["pe_premium_pct"] = round(pe_premium, 1)
            
            if pe_premium > 100:
                result["premium_level"] = "significant_premium"
                result["interpretation"] = "⚠️ 估值显著高于行业，必须通过外部信息验证是否存在转型/题材溢价"
            elif pe_premium > 50:
                result["premium_level"] = "high_premium"
                result["interpretation"] = "⚠️ 估值高于行业，建议通过网络搜索验证预期"
            elif pe_premium > 20:
                result["premium_level"] = "moderate_premium"
                result["interpretation"] = "→ 估值略高于行业，可能有成长性溢价"
            elif pe_premium < -20:
                result["premium_level"] = "discount"
                result["interpretation"] = "✓ 估值低于行业，可能存在低估"
            else:
                result["premium_level"] = "fair"
                result["interpretation"] = "→ 估值与行业基本持平"
        
        if pb and industry_pb and industry_pb > 0:
            pb_premium = (pb - industry_pb) / industry_pb * 100
            result["pb_premium_pct"] = round(pb_premium, 1)
        
        return result
    
    def _detect_concept_clues(self, name: str, industry: str) -> List[Dict]:
        """
        检测概念题材线索（仅作为查证方向，不作为结论）
        """
        text = f"{name} {industry}"
        clues = []
        
        for concept_name, concept_info in self.concept_db.items():
            for keyword in concept_info["keywords"]:
                if keyword in text:
                    clues.append({
                        "concept": concept_name,
                        "keyword": keyword,
                        "note": "⚠️ 仅为关键词匹配，必须通过外部信息验证",
                        "verification_required": True,
                        "suggested_sources": concept_info.get("verification_sources", [])
                    })
                    break
        
        return clues
    
    def _get_verified_transformation(self, case: Dict) -> Dict:
        """获取已验证的转型信息"""
        return {
            "status": "已验证",
            "verification_sources": case.get("verification_sources", []),
            "traditional_business": case.get("traditional_business", ""),
            "traditional_valuation": case.get("traditional_valuation", ""),
            "transformation_narrative": case.get("transformation_narrative", ""),
            "valuation_logic": case.get("valuation_logic", ""),
            "last_updated": case.get("last_updated", "")
        }
    
    def _generate_verification_checklist(self, code: str, name: str, 
                                         industry: str) -> List[Dict]:
        """生成验证清单"""
        return [
            {
                "priority": "高",
                "item": "公司业务转型动态",
                "sources": ["公司公告", "投资者互动", "年报/半年报"],
                "keywords": [f"{name} 转型", f"{name} 新业务", f"{name} 机器人", f"{name} 新能源"]
            },
            {
                "priority": "高",
                "item": "资产重组/并购信息",
                "sources": ["公司公告", "监管批复"],
                "keywords": [f"{name} 重组", f"{name} 资产注入", f"{name} 收购"]
            },
            {
                "priority": "中",
                "item": "供应链/客户信息",
                "sources": ["供应链新闻", "客户公告"],
                "keywords": [f"{name} 特斯拉", f"{name} 华为", f"{name} 供应商"]
            },
            {
                "priority": "中",
                "item": "技术突破/产品进展",
                "sources": ["专利信息", "技术新闻"],
                "keywords": [f"{name} 固态电池", f"{name} 新技术", f"{name} 量产"]
            }
        ]
    
    def _classify_investment_type(self, valuation: Dict, 
                                  has_verified_case: bool) -> Dict:
        """判断投资类型"""
        pe_premium = valuation.get("pe_premium_pct")
        premium_level = valuation.get("premium_level", "unknown")
        
        # 高估值 + 无验证案例 = 高风险
        if not has_verified_case and premium_level in ["significant_premium", "high_premium"]:
            return {
                "type": "unverified_thematic",
                "name": "⚠️ 未验证主题投资",
                "characteristics": "估值高但缺乏验证信息，风险极高",
                "suitable_for": "不建议参与，或极轻仓试错",
                "key_risk": "预期落空导致估值回归，跌幅可能超过50%",
                "action_required": "必须通过外部信息验证后再决策"
            }
        
        # 有验证案例的分类
        if premium_level == "significant_premium" or (pe_premium and pe_premium > 100):
            return {
                "type": "thematic",
                "name": "主题投资",
                "characteristics": "预期驱动、题材溢价、波动大",
                "suitable_for": "高风险偏好、短期交易",
                "key_risk": "预期落空导致估值回归"
            }
        elif premium_level == "high_premium" or (pe_premium and pe_premium > 50):
            return {
                "type": "high_growth",
                "name": "高成长投资",
                "characteristics": "高增速、赛道红利、估值容忍度高",
                "suitable_for": "成长型投资者、中期持有",
                "key_risk": "增速不及预期导致杀估值"
            }
        elif premium_level == "discount":
            return {
                "type": "value",
                "name": "价值投资",
                "characteristics": "低估值、高股息、安全边际",
                "suitable_for": "价值型投资者、长期持有",
                "key_risk": "价值陷阱"
            }
        else:
            return {
                "type": "unknown",
                "name": "待判断",
                "characteristics": "信息不足",
                "suitable_for": "需进一步分析",
                "key_risk": "未知"
            }
    
    def generate_report(self, analysis: Dict) -> str:
        """生成文字报告（严谨版）"""
        lines = []
        
        lines.append("="*70)
        lines.append("🔍 估值预期分析报告（严谨版）")
        lines.append("="*70)
        
        # 验证状态警告
        verification_status = analysis.get("verification_status", "未知")
        if verification_status == "未验证":
            lines.append("\n" + "⚠️"*20)
            lines.append("【重要警告】")
            lines.append("本股票无内置验证案例，以下分析仅基于公开数据计算，")
            lines.append("所有预期信息必须通过外部渠道验证后方可作为投资依据。")
            lines.append("⚠️"*20)
        
        # 基本信息
        lines.append(f"\n【公司信息】")
        lines.append(f"  股票代码: {analysis['code']}")
        lines.append(f"  公司名称: {analysis['name']}")
        lines.append(f"  所属行业: {analysis['industry']}")
        lines.append(f"  验证状态: {verification_status}")
        
        # 估值分析
        val = analysis['valuation']
        lines.append(f"\n【估值分析】")
        if val.get('pe'):
            lines.append(f"  当前PE: {val['pe']:.2f}")
        if val.get('industry_pe'):
            lines.append(f"  行业PE: {val['industry_pe']:.2f}")
        if val.get('pe_premium_pct') is not None:
            lines.append(f"  估值溢价: {val['pe_premium_pct']:+.1f}%")
        if val.get('interpretation'):
            lines.append(f"  解读: {val['interpretation']}")
        
        # 概念线索（仅作为查证方向）
        concept_clues = analysis.get("concept_clues", [])
        if concept_clues:
            lines.append(f"\n【概念线索（待验证）】")
            lines.append("⚠️ 以下仅为关键词匹配结果，必须通过外部信息验证：")
            for c in concept_clues:
                lines.append(f"\n  • {c['concept']}")
                lines.append(f"    匹配词: {c['keyword']}")
                lines.append(f"    建议查证: {', '.join(c.get('suggested_sources', []))}")
        
        # 转型叙事
        trans = analysis['transformation']
        lines.append(f"\n【转型叙事】")
        lines.append(f"  状态: {trans.get('status', '未知')}")
        
        if trans.get('status') == "未验证":
            lines.append(f"\n  ⚠️ 必须通过以下方式验证：")
            if trans.get('verification_checklist'):
                for item in trans['verification_checklist']:
                    lines.append(f"\n    【{item['priority']}优先级】{item['item']}")
                    lines.append(f"    建议渠道: {', '.join(item['sources'])}")
                    lines.append(f"    搜索关键词: {', '.join(item['keywords'])}")
        else:
            lines.append(f"  传统业务: {trans.get('traditional_business', 'N/A')}")
            if trans.get('traditional_valuation'):
                lines.append(f"  传统估值: {trans['traditional_valuation']}")
            lines.append(f"  转型方向: {trans.get('transformation_narrative', 'N/A')}")
            if trans.get('verification_sources'):
                lines.append(f"\n  验证来源:")
                for src in trans['verification_sources']:
                    lines.append(f"    • {src}")
        
        # 已验证的预期
        expectations = analysis.get('expectations', [])
        if expectations:
            lines.append(f"\n【已验证的市场预期】")
            for i, exp in enumerate(expectations, 1):
                lines.append(f"\n  【预期{i}】{exp.get('name', 'N/A')}")
                lines.append(f"    可信度: {exp.get('confidence', 'N/A')}")
                lines.append(f"    内容: {exp.get('content', 'N/A')}")
                if exp.get('evidence'):
                    lines.append(f"    证据:")
                    for ev in exp['evidence']:
                        lines.append(f"      • {ev}")
                if exp.get('catalyst'):
                    lines.append(f"    催化剂: {exp['catalyst']}")
                if exp.get('timeline'):
                    lines.append(f"    时间线: {exp['timeline']}")
                if exp.get('probability'):
                    lines.append(f"    兑现概率: {exp['probability']}")
                if exp.get('risk'):
                    lines.append(f"    风险点: {exp['risk']}")
        
        # 未证实传闻
        unverified = analysis.get('unverified_rumors', [])
        if unverified:
            lines.append(f"\n【未证实传闻（仅供参考）】")
            for rumor in unverified:
                lines.append(f"\n  • {rumor.get('content', 'N/A')}")
                lines.append(f"    状态: {rumor.get('status', 'N/A')}")
                if rumor.get('note'):
                    lines.append(f"    说明: {rumor['note']}")
        
        # 投资类型
        inv_type = analysis['investment_type']
        lines.append(f"\n【投资类型判断】")
        lines.append(f"  类型: {inv_type['name']}")
        lines.append(f"  特征: {inv_type['characteristics']}")
        lines.append(f"  适合: {inv_type['suitable_for']}")
        lines.append(f"  核心风险: {inv_type['key_risk']}")
        if inv_type.get('action_required'):
            lines.append(f"\n  ⚠️ 必须行动: {inv_type['action_required']}")
        
        lines.append(f"\n【免责声明】")
        lines.append(f"{analysis.get('disclaimer', '')}")
        lines.append(f"\n分析时间: {analysis.get('analysis_time', '')}")
        lines.append("\n" + "="*70)
        
        return "\n".join(lines)


# =============================================================================
# 4. 便捷使用函数
# =============================================================================

def analyze_valuation_expectation(code: str, skip_verification: bool = False, 
                                  **kwargs) -> Dict:
    """
    便捷的估值预期分析函数
    
    Args:
        code: 股票代码
        skip_verification: 是否跳过验证（仅用于测试）
        **kwargs: 可选参数
        
    Returns:
        分析结果字典
    """
    analyzer = ValuationExpectationAnalyzer()
    return analyzer.analyze(code, skip_verification=skip_verification, **kwargs)


def print_valuation_report(code: str, skip_verification: bool = False, **kwargs):
    """
    直接打印估值预期分析报告
    
    Args:
        code: 股票代码
        skip_verification: 是否跳过验证（仅用于测试）
        **kwargs: 可选参数
    """
    analyzer = ValuationExpectationAnalyzer()
    analysis = analyzer.analyze(code, skip_verification=skip_verification, **kwargs)
    report = analyzer.generate_report(analysis)
    print(report)
    return analysis


# =============================================================================
# 5. 命令行入口
# =============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("市场预期分析框架（严谨版）")
        print("---")
        print("\n核心原则：没有验证，不输出")
        print("\n用法:")
        print("  python3 market_expectation_framework.py <股票代码>")
        print("\n示例:")
        print("  python3 market_expectation_framework.py 000559.SZ")
        print("\n功能:")
        print("  1. 识别估值溢价/折价")
        print("  2. 生成概念查证线索")
        print("  3. 输出验证清单（无内置案例时）")
        print("  4. 仅输出已验证的预期")
        print("\n注意:")
        print("  • 无内置案例的股票会提示必须通过外部信息验证")
        print("  • 所有预期必须标注信息来源和可信度")
        print("  • 未证实传闻会明确标注")
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
    
    # 尝试获取数据
    name = ""
    industry = ""
    pe = None
    pb = None
    industry_pe = None
    
    if TUSHARE_AVAILABLE:
        try:
            df_basic = pro.stock_basic(ts_code=code)
            if df_basic is not None and not df_basic.empty:
                name = df_basic.iloc[0]["name"]
                industry = df_basic.iloc[0].get("industry", "")
            
            df_val = pro.daily_basic(ts_code=code)
            if df_val is not None and not df_val.empty:
                pe = df_val.iloc[0].get("pe_ttm")
                pb = df_val.iloc[0].get("pb")
            
            if industry:
                df_industry = pro.stock_basic(industry=industry)
                if df_industry is not None and not df_industry.empty:
                    codes = df_industry["ts_code"].head(20).tolist()
                    pe_list = []
                    for c in codes:
                        try:
                            df = pro.daily_basic(ts_code=c)
                            if df is not None and not df.empty:
                                p = df.iloc[0].get("pe_ttm")
                                if p and p > 0 and p < 500:
                                    pe_list.append(p)
                        except:
                            continue
                    if pe_list:
                        industry_pe = sum(pe_list) / len(pe_list)
        except Exception as e:
            print(f"数据获取失败: {e}")
    
    # 执行分析
    print_valuation_report(
        code=code,
        name=name,
        industry=industry,
        pe=pe,
        pb=pb,
        industry_pe=industry_pe
    )
