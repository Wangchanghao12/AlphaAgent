#!/usr/bin/env python3
"""
市场预期分析模块 - 精简版
采用列表形式，去除复杂表格
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tushare as ts
import pandas as pd

# 初始化Tushare（从环境变量 TUSHARE_TOKEN 传入）
_token = (os.environ.get('TUSHARE_TOKEN') or '').strip()
pro = ts.pro_api(_token) if _token else ts.pro_api()


class MarketExpectationAnalyzer:
    """市场预期分析器 - 精简版"""

    def __init__(self, ts_code):
        self.ts_code = ts_code
        self.stock_name = ""
        self.industry = ""
        self.pe = 0
        self.industry_pe = 0
        self.market_cap = 0
        self._load_basic_info()

    def _load_basic_info(self):
        try:
            basic = pro.stock_basic(ts_code=self.ts_code, fields='ts_code,name,industry')
            if not basic.empty:
                self.stock_name = basic.iloc[0]['name']
                self.industry = basic.iloc[0]['industry']
        except:
            pass

    def analyze(self):
        """主分析入口 - 聚焦估值、预期与风险（与2.2竞争格局互补）"""
        # print("\n市场预期分析")
        
        self._get_valuation()
        self._evaluate_valuation()
        self._analyze_expectations_and_type()
        self._list_risks()
        self._print_search_hints()

    def _get_valuation(self):
        """获取估值数据"""
        try:
            daily = pro.daily_basic(ts_code=self.ts_code, limit=1)
            if not daily.empty:
                self.pe = daily.iloc[0].get('pe_ttm', 0) or 0
                self.market_cap = daily.iloc[0].get('total_mv', 0) or 0
        except:
            pass
        
        try:
            if self.industry:
                peers = pro.stock_basic(exchange='', list_status='L', fields='ts_code,industry')
                industry_peers = peers[peers['industry'] == self.industry]['ts_code'].tolist()[:20]
                pe_list = []
                for code in industry_peers:
                    try:
                        d = pro.daily_basic(ts_code=code, limit=1)
                        if not d.empty:
                            p = d.iloc[0].get('pe_ttm', 0)
                            if p and p > 0 and p < 500:
                                pe_list.append(p)
                    except:
                        continue
                if pe_list:
                    self.industry_pe = sum(pe_list) / len(pe_list)
        except:
            pass

    def _evaluate_valuation(self):
        """估值水平 - 表格化"""
        print(f"\n- **估值水平**\n")
        
        premium = (self.pe / self.industry_pe - 1) * 100 if self.industry_pe > 0 else 0
        print("| 指标 | 数值 |")
        print("|:-----|------|")
        print(f"| 当前 PE-TTM | {self.pe:.1f} 倍 |")
        print(f"| 行业均值 PE | {self.industry_pe:.1f} 倍 |")
        if self.industry_pe > 0:
            print(f"| 相对行业溢价 | {'+' if premium > 0 else ''}{premium:.0f}% |")
        
        if self.pe > 100:
            judgment = "极高估值，需业绩爆发支撑"
        elif self.pe > 50:
            judgment = "高估值，依赖成长预期"
        elif self.pe > self.industry_pe * 1.5 and self.industry_pe > 0:
            judgment = "溢价明显，需验证成长逻辑"
        elif self.pe > 0:
            judgment = "估值合理或偏低"
        else:
            judgment = "亏损状态，PE 无参考意义"
        print(f"\n**估值判断**：{judgment}")

    def _analyze_expectations_and_type(self):
        """预期来源与投资类型 - 合并输出，避免与2.2交叉"""
        print(f"\n- **预期拆解与策略建议**\n")
        
        if self.pe > 100:
            print("| 预期来源 | 说明 | 策略建议 |")
            print("|:---------|:-----|:---------|")
            print("| 概念/题材 | 高 PE 可能反映 AI/机器人等概念预期 | 主题投资，仓位&lt;15%，严格止损 |")
            print("| 业绩爆发 | PE 需高增速支撑，需验证订单/产能 | 短线操作，跟踪业绩兑现 |")
        elif self.pe > 50:
            print("| 预期来源 | 说明 | 策略建议 |")
            print("|:---------|:-----|:---------|")
            print("| 成长预期 | 市场看好 2–3 年增长 | 成长+主题，仓位 20–30% |")
            print("| 行业景气 | 行业处于上升周期 | 跟踪行业数据验证 |")
        elif self.pe > 20:
            print("- 估值处于合理区间，关注业绩兑现")
            print("- 策略：长期持有，仓位 30–50%")
        elif self.pe > 0:
            print("- 价值/周期股，策略：逆向投资，低买高卖")
        else:
            print("- 亏损股，关注扭亏进展")

    def _list_risks(self):
        """估值相关风险 - 不重复2.2竞争分析"""
        print(f"\n- **估值风险提示**\n")
        print("| 风险类型 | 说明 |")
        print("|:---------|:-----|")
        print("| 业绩不及预期 | 高估值对业绩敏感，业绩下修易导致估值下杀 |")
        print("| 行业景气下行 | 行业 beta 转负时，估值压缩 |")
        print("| 预期落空 | 概念退潮或成长逻辑证伪，估值回归 |")

    def _print_search_hints(self):
        """市场预期待补充 - 搜索建议（与2.2护城河格式一致）"""
        print(f"\n- **市场预期待补充（需搜索验证）**\n")
        print("> 以下维度需通过研报、公告、新闻搜索补充，以验证估值合理性：\n\n")
        print("| 维度 | 关注点 | 建议搜索关键词 |")
        print("|:-----|:-------|:---------------|")
        print(f"| 机构一致预期 | 券商目标价、盈利预测、评级 | `{self.stock_name} 机构 目标价 一致预期` |")
        print(f"| 订单/产能 | 在手订单、产能释放节奏、扩产计划 | `{self.stock_name} 订单 产能 扩产` |")
        print(f"| 概念/题材 | 所属概念、题材催化、市场热度 | `{self.stock_name} 概念 题材 {self.industry}` |")
        print(f"| 估值锚定 | 同行估值、历史PE分位、可比公司 | `{self.stock_name} PE 估值 研报` |")
        print(f"| 业绩催化剂 | 业绩拐点、新品放量、政策落地 | `{self.stock_name} 业绩 催化剂 2025` |")
        print()


def analyze_market_expectation(ts_code):
    """主入口"""
    analyzer = MarketExpectationAnalyzer(ts_code)
    analyzer.analyze()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 market_expectation_analysis.py <ts_code>")
        sys.exit(1)
    
    analyze_market_expectation(sys.argv[1])
