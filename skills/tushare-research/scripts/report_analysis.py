#!/usr/bin/env python3
"""
研报数据挖掘与交叉验证分析框架
核心原则：从研报提取关键数据，但不迷信观点，做独立交叉验证
"""
import sys
import tushare as ts
import pandas as pd
from datetime import datetime

# 初始化Tushare
pro = ts.pro_api()


class ReportAnalyzer:
    """研报分析器 - 提取数据、交叉验证、独立判断"""
    
    def __init__(self, ts_code):
        self.ts_code = ts_code
        self.company_name = ""
        self._load_basic_info()
        
    def _load_basic_info(self):
        """加载公司基本信息"""
        try:
            basic = pro.stock_basic(ts_code=self.ts_code, fields='ts_code,name,industry')
            if not basic.empty:
                self.company_name = basic.iloc[0]['name']
        except:
            pass
    
    def analyze_reports(self):
        """
        研报深度分析主函数
        输出：提取关键数据 + 交叉验证 + 独立判断
        """
        print("---")
        print(f"📊 研报数据挖掘与交叉验证 - {self.company_name} ({self.ts_code})")
        print("---")
        
        # 1. 获取研报数据
        reports = self._get_report_data()
        
        # 2. 获取业绩快报（实际数据）
        actual_data = self._get_actual_performance()
        
        # 3. 交叉验证
        self._cross_validation(reports, actual_data)
        
        # 4. 独立判断
        self._independent_assessment(reports, actual_data)
    
    def _get_report_data(self):
        """获取研报数据"""
        print("\n【研报数据提取】")
        
        try:
            reports = pro.report_rc(ts_code=self.ts_code, limit=30)
            if reports.empty:
                print("  ⚠️ 无研报数据")
                return None
            
            # 按日期排序
            reports = reports.sort_values('report_date', ascending=False)
            
            print(f"  共获取 {len(reports)} 份研报")
            
            # 提取最新研报关键信息
            latest = reports.iloc[0]
            print(f"\n  最新研报:")
            print(f"    日期: {latest['report_date']}")
            print(f"    机构: {latest['org_name']}")
            print(f"    标题: {latest['report_title']}")
            print(f"    评级: {latest['rating']}")
            
            # 从标题提取关键定位信息
            title_keywords = self._extract_keywords_from_title(latest['report_title'])
            if title_keywords:
                print(f"    定位关键词: {', '.join(title_keywords)}")
            
            return reports
            
        except Exception as e:
            print(f"  ⚠️ 研报获取失败: {e}")
            return None
    
    def _extract_keywords_from_title(self, title):
        """从研报标题提取定位关键词"""
        if not title:
            return []
        
        # 常见定位关键词
        keywords = []
        keyword_map = {
            '龙头': '行业龙头',
            '领军': '行业领军',
            '第一': '行业第一',
            '唯一': '唯一标的',
            '稀缺': '稀缺性',
            '成长': '成长股',
            '周期': '周期股',
            '价值': '价值股',
            '洁净室': '洁净室工程',
            '半导体': '半导体产业链',
            '芯片': '芯片产业链',
            '电子': '电子制造',
            '出海': '海外布局',
            '国产替代': '国产替代',
        }
        
        for kw, meaning in keyword_map.items():
            if kw in title:
                keywords.append(meaning)
        
        return keywords
    
    def _get_actual_performance(self):
        """获取实际业绩数据（业绩快报）"""
        print("\n【实际业绩数据（业绩快报）】")
        
        try:
            express = pro.express(ts_code=self.ts_code, limit=5)
            if express.empty:
                print("  ⚠️ 无业绩快报数据")
                return {}
            
            actual_data = {}
            for _, row in express.iterrows():
                year = str(row['end_date'])[:4]
                actual_data[year] = {
                    'revenue': row['revenue'] / 100000000,  # 亿元
                    'net_profit': row['n_income'] / 10000,   # 万元
                    'yoy': row.get('n_income_yoy', None)     # 同比增长
                }
                print(f"  {year}年: 营收{actual_data[year]['revenue']:.2f}亿, "
                      f"净利润{actual_data[year]['net_profit']:.0f}万元")
            
            return actual_data
            
        except Exception as e:
            print(f"  ⚠️ 业绩快报获取失败: {e}")
            return {}
    
    def _cross_validation(self, reports, actual_data):
        """交叉验证：研报预测 vs 实际业绩"""
        print("\n【交叉验证：研报预测 vs 实际业绩】")
        
        if reports is None or not actual_data:
            print("  ⚠️ 数据不足，无法交叉验证")
            return
        
        # 提取最新研报预测
        predictions = {}
        for _, row in reports.iterrows():
            if pd.notna(row['quarter']) and pd.notna(row['np']):
                year = str(row['quarter'])[:4]
                if year not in predictions:
                    predictions[year] = {
                        'np_pred': row['np'],  # 万元
                        'pe_pred': row['pe'] if pd.notna(row['pe']) else None,
                        'roe_pred': row['roe'] if pd.notna(row['roe']) else None,
                        'org': row['org_name'],
                        'date': row['report_date']
                    }
        
        # 对比预测与实际
        for year in ['2024', '2025', '2026']:
            if year in predictions and year in actual_data:
                pred = predictions[year]
                actual = actual_data[year]
                
                print(f"\n  {year}年:")
                print(f"    研报预测净利润: {pred['np_pred']:.0f}万元 ({pred['org']}, {pred['date']})")
                print(f"    实际净利润: {actual['net_profit']:.0f}万元")
                
                # 计算偏差
                diff_pct = (actual['net_profit'] - pred['np_pred']) / pred['np_pred'] * 100
                
                if abs(diff_pct) < 10:
                    status = "✓ 符合预期"
                elif diff_pct > 10:
                    status = f"✓ 超预期 (+{diff_pct:.1f}%)"
                else:
                    status = f"⚠️ 低于预期 ({diff_pct:.1f}%)"
                
                print(f"    验证结果: {status}")
                
                # 估值目标对比
                if pred['pe_pred']:
                    print(f"    研报目标PE: {pred['pe_pred']:.1f}倍")
    
    def _independent_assessment(self, reports, actual_data):
        """独立判断：基于数据，形成独立观点"""
        print("\n---")
        print("🎯 独立判断（基于数据，不迷信研报观点）")
        print("---")
        
        # 1. 研报定位验证
        print("\n【1. 研报定位验证】")
        if reports is not None and not reports.empty:
            latest_title = reports.iloc[0]['report_title']
            keywords = self._extract_keywords_from_title(latest_title)
            
            print(f"  研报定位: {', '.join(keywords) if keywords else '未明确'}")
            print(f"  独立验证:")
            print(f"    - 需要结合fina_mainbz验证主营业务构成")
            print(f"    - 需要对比同行业公司验证'龙头'说法")
        
        # 2. 预测准确性评估
        print("\n【2. 研报预测准确性】")
        print(f"  评估方法:")
        print(f"    - 对比研报发布日期与预测年份（时间差越大，准确性越低）")
        print(f"    - 对比多家机构预测的一致性")
        print(f"    - 关注预测修正频率（频繁修正说明不确定性高）")
        
        # 3. 估值合理性判断
        print("\n【3. 估值合理性判断】")
        print(f"  关键对比:")
        print(f"    - 研报目标PE vs 当前PE")
        print(f"    - 研报目标PE vs 行业平均PE")
        print(f"    - 当前PE vs 历史PE区间")
        
        # 4. 风险信号识别
        print("\n【4. 风险信号识别】")
        risk_signals = []
        
        # 检查当前估值vs研报目标
        try:
            daily_basic = pro.daily_basic(ts_code=self.ts_code, limit=1)
            if not daily_basic.empty:
                current_pe = daily_basic.iloc[0].get('pe_ttm', None)
                if current_pe and reports is not None:
                    # 获取研报目标PE
                    for _, row in reports.iterrows():
                        if pd.notna(row['pe']) and row['pe'] > 0:
                            if current_pe > row['pe'] * 1.5:
                                risk_signals.append(f"当前PE({current_pe:.1f})远高于研报目标({row['pe']:.1f})")
                            break
        except:
            pass
        
        # 检查业绩增速与估值匹配度
        if '2025' in actual_data and '2024' in actual_data:
            yoy_growth = (actual_data['2025']['net_profit'] / actual_data['2024']['net_profit'] - 1) * 100
            try:
                daily_basic = pro.daily_basic(ts_code=self.ts_code, limit=1)
                if not daily_basic.empty:
                    current_pe = daily_basic.iloc[0].get('pe_ttm', None)
                    if current_pe and current_pe > yoy_growth * 2:
                        risk_signals.append(f"PE({current_pe:.1f})远高于业绩增速({yoy_growth:.1f}%)，估值透支")
            except:
                pass
        
        if risk_signals:
            for signal in risk_signals:
                print(f"  ⚠️ {signal}")
        else:
            print(f"  ✓ 未发现明显风险信号")
        
        # 5. 关键问题清单
        print("\n【5. 需要进一步验证的问题】")
        print(f"  □ 研报'龙头'说法是否有数据支撑？（市占率、技术壁垒）")
        print(f"  □ 高增长的驱动因素是什么？（订单、产能、并购？）")
        print(f"  □ 毛利率趋势如何？（研报说'有望修复'，实际呢？）")
        print(f"  □ 现金流与利润是否匹配？（工程类公司关注回款）")
        print(f"  □ 机构调研频率如何？（关注度高vs低）")


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python3 report_analysis.py <股票代码>")
        print("示例: python3 report_analysis.py 603163.SH")
        sys.exit(1)
    
    ts_code = sys.argv[1]
    
    analyzer = ReportAnalyzer(ts_code)
    analyzer.analyze_reports()
    
    print("\n---")
    print("📋 分析总结")
    print("---")
    print("""
本分析框架的核心原则：
1. 【数据提取】从研报提取关键数据（定位、预测、估值）
2. 【交叉验证】对比研报预测 vs 实际业绩，评估准确性
3. 【独立判断】不迷信研报评级，基于数据形成独立观点
4. 【风险识别】识别估值透支、预测偏差等风险信号

关键提醒：
- 研报发布日期很重要（越新越有价值）
- 多家机构一致性比单一机构更可靠
- 预测准确率反映机构对公司的理解深度
- 当前估值与研报目标价的差距是重要信号
    """)


if __name__ == '__main__':
    main()
