#!/usr/bin/env python3
"""
商业模式与竞争格局精简分析模块
主营业务构成与核心财务指标采用 MD 表格形式展现
"""
import os
import re
import sys
import math
import tushare as ts
import pandas as pd
from datetime import datetime

# 初始化Tushare（从环境变量 TUSHARE_TOKEN 传入）
_token = (os.environ.get('TUSHARE_TOKEN') or '').strip()
pro = ts.pro_api(_token) if _token else ts.pro_api()

# 注：产业链无法从单一数据源一次性补全，无公开 API 提供各行业上下游结构，需结合大模型/网络搜索补充


def _format_report_period(end_date):
    """将报告期 end_date (如 20250930) 格式化为可读描述，如 2025年三季报"""
    if not end_date:
        return ""
    s = str(end_date).strip()
    m = re.search(r'(\d{4})(\d{2})(\d{2})', s)
    if not m:
        return s
    y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
    if mo == 12 and d == 31:
        return f"{y}年报"
    if mo == 9 and d == 30:
        return f"{y}年三季报"
    if mo == 6 and d == 30:
        return f"{y}年半年报"
    if mo == 3 and d == 31:
        return f"{y}年一季报"
    return f"{y}-{mo:02d}-{d:02d}"


def _fetch_growth_data(ts_code):
    """
    获取业绩增长数据，优先业绩预告 > 业绩快报 > 财报。对比去年同期。
    返回 dict: source, period_desc, revenue_yi, revenue_yoy, netprofit_yi, netprofit_yoy, profit_dedt_yi, profit_dedt_yoy
    """
    result = {'source': '', 'period_desc': '', 'revenue_yi': 0, 'revenue_yoy': None,
              'netprofit_yi': 0, 'netprofit_yoy': None, 'profit_dedt_yi': 0, 'profit_dedt_yoy': None}
    try:
        # 1. 优先业绩预告（仅有净利润变动幅度，无营收/扣非）
        fc = pro.forecast(ts_code=ts_code, limit=3)
        if fc is not None and not fc.empty:
            row = fc.iloc[0]
            result['source'] = '业绩预告'
            result['period_desc'] = _format_report_period(row.get('end_date', ''))
            p_min = row.get('p_change_min')
            p_max = row.get('p_change_max')
            if p_min is not None or p_max is not None:
                if p_min == p_max or p_max is None:
                    result['netprofit_yoy'] = float(p_min) if p_min is not None else None
                elif p_min is None:
                    result['netprofit_yoy'] = float(p_max)
                else:
                    result['netprofit_yoy'] = (float(p_min) + float(p_max)) / 2
            net_min = row.get('net_profit_min')
            net_max = row.get('net_profit_max')
            if net_min is not None or net_max is not None:
                vmin = float(net_min) if net_min is not None else 0
                vmax = float(net_max) if net_max is not None else 0
                result['netprofit_yi'] = ((vmin + vmax) / 2) / 10000  # 万元→亿
        # 2. 业绩快报（有营收、净利润、扣非同比）
        exp = pro.express(ts_code=ts_code, limit=2)
        if exp is not None and not exp.empty:
            row = exp.iloc[0]
            if not result['source']:
                result['source'] = '业绩快报'
                result['period_desc'] = _format_report_period(row.get('end_date', ''))
            # 快报有营收、净利润、yoy_sales、yoy_dedu_np；净利润同比可计算
            rev = row.get('revenue', 0) or 0
            result['revenue_yi'] = rev / 1e8
            result['revenue_yoy'] = row.get('yoy_sales')
            if result['revenue_yoy'] is not None:
                result['revenue_yoy'] = float(result['revenue_yoy'])
            np_val = row.get('n_income', 0) or 0
            if not result['source'] == '业绩预告':
                result['netprofit_yi'] = np_val / 1e8
            np_last = row.get('np_last_year', 0) or 0
            if np_last and np_val is not None:
                _yoy = (np_val - np_last) / np_last * 100
                if result['netprofit_yoy'] is None:
                    result['netprofit_yoy'] = _yoy
            result['profit_dedt_yoy'] = row.get('yoy_dedu_np')
            if result['profit_dedt_yoy'] is not None:
                result['profit_dedt_yoy'] = float(result['profit_dedt_yoy'])
            # 扣非绝对值：express 无，需财报
        # 3. 财报补充（fina_indicator + income）
        fina = pro.fina_indicator(ts_code=ts_code, limit=1)
        inc = pro.income(ts_code=ts_code, limit=1, fields='revenue,n_income')
        if fina is not None and not fina.empty and not result['source']:
            result['source'] = result['source'] or '财报'
        if fina is not None and not fina.empty:
            row = fina.iloc[0]
            if not result['period_desc']:
                result['period_desc'] = _format_report_period(row.get('end_date', ''))
            if result['revenue_yoy'] is None:
                result['revenue_yoy'] = row.get('tr_yoy')
                if result['revenue_yoy'] is not None:
                    result['revenue_yoy'] = float(result['revenue_yoy'])
            if result['netprofit_yoy'] is None:
                result['netprofit_yoy'] = row.get('netprofit_yoy')
                if result['netprofit_yoy'] is not None:
                    result['netprofit_yoy'] = float(result['netprofit_yoy'])
            if result['profit_dedt_yoy'] is None:
                result['profit_dedt_yoy'] = row.get('dt_netprofit_yoy')
                if result['profit_dedt_yoy'] is not None:
                    result['profit_dedt_yoy'] = float(result['profit_dedt_yoy'])
            result['profit_dedt_yi'] = (row.get('profit_dedt', 0) or 0) / 1e8
        if inc is not None and not inc.empty and (result['revenue_yi'] == 0 or result['netprofit_yi'] == 0):
            row = inc.iloc[0]
            if result['revenue_yi'] == 0:
                result['revenue_yi'] = (row.get('revenue', 0) or 0) / 1e8
            if result['netprofit_yi'] == 0:
                result['netprofit_yi'] = (row.get('n_income', 0) or 0) / 1e8
        if not result['source']:
            result['source'] = '财报'
        return result
    except Exception:
        return result


def _get_ann_date(pro_api, ts_code, end_date):
    """从利润表接口获取指定报告期的公告日期，返回格式化字符串如 2025-10-28，失败返回空"""
    try:
        # period 为报告期最后一天，如 20251231、20250930
        df = pro_api.income(ts_code=ts_code, period=str(end_date), fields='end_date,ann_date')
        if df is None or df.empty:
            return ""
        matched = df[df['end_date'].astype(str) == str(end_date)]
        if matched.empty:
            matched = df
        ann = matched.iloc[0].get('ann_date')
        if not ann or str(ann) in ('nan', 'None', ''):
            return ""
        s = str(ann)[:10].replace('-', '')
        if len(s) == 8:  # YYYYMMDD
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        if len(s) >= 10 and '-' in str(ann):
            return str(ann)[:10]
        return ""
    except Exception:
        return ""


class BusinessModelAnalyzer:
    """商业模式分析器 - 精简版"""

    def __init__(self, ts_code):
        self.ts_code = ts_code
        self.company_name = ""
        self.industry = ""
        self._load_basic_info()

    def _load_basic_info(self):
        try:
            basic = pro.stock_basic(ts_code=self.ts_code, fields='ts_code,name,industry')
            if not basic.empty:
                self.company_name = basic.iloc[0]['name']
                self.industry = basic.iloc[0]['industry']
        except:
            pass

    def analyze_business_model(self):
        print("商业模式分析")
        
        self._analyze_revenue_structure()
        self._analyze_profit_model()
        self._analyze_industry_chain()
        self._evaluate_model_health()

    def _analyze_revenue_structure(self):
        print(f"\n- **主营业务构成**")
        
        try:
            fina_mainbz = pro.fina_mainbz(ts_code=self.ts_code, type='P', limit=20)
            if not fina_mainbz.empty:
                latest_period = fina_mainbz['end_date'].iloc[0]
                latest_data = fina_mainbz[fina_mainbz['end_date'] == latest_period]
                total_revenue = latest_data['bz_sales'].sum() or 0
                
                seen = set()
                businesses = []
                for _, row in latest_data.iterrows():
                    name = row.get('bz_item', '未知')
                    if name not in seen:
                        seen.add(name)
                        sales = row.get('bz_sales', 0) or 0
                        profit = row.get('bz_profit', 0) or 0
                        margin = (profit / sales * 100) if sales > 0 else 0
                        pct = (sales / total_revenue * 100) if total_revenue > 0 else 0
                        businesses.append((name, sales/1e8, pct, margin))
                
                # MD 表格形式：括号内加入财报报告期与发布日期
                period_desc = _format_report_period(latest_period)
                ann_desc = _get_ann_date(pro, self.ts_code, latest_period)
                period_info = period_desc
                if ann_desc:
                    period_info = f"{period_desc}，发布于{ann_desc}"
                print(f"\n核心业务收入构成（最近一期，{period_info}）：\n")
                print("| 业务类型 | 收入(亿) | 占比 | 毛利率 |")
                print("|:---------|----------|------|--------|")
                for name, sales, pct, margin in businesses[:5]:
                    print(f"| {name} | {sales:.2f} | {pct:.1f}% | {margin:.1f}% |")
                
                top3_pct = sum(b[2] for b in businesses[:3])
                if top3_pct > 80:
                    print(f"\n⚠️ 业务集中度风险：前3大业务占比{top3_pct:.1f}%")
            else:
                print("\n> 暂无主营业务构成数据")
        except:
            print("\n> 主营业务分析暂不可用")

    def _analyze_profit_model(self):
        print(f"\n- **盈利能力分析**")
        
        try:
            fina = pro.fina_indicator(ts_code=self.ts_code, limit=4)
            if not fina.empty:
                latest = fina.iloc[0]
                gm = latest.get('grossprofit_margin', 0) or 0
                nm = latest.get('netprofit_margin', 0) or 0
                roe = latest.get('roe', 0) or 0
                debt = latest.get('debt_to_assets', 0) or 0
                
                gm_tag = '高毛利' if gm > 40 else '中毛利' if gm > 20 else '低毛利'
                roe_tag = '优秀' if roe > 15 else '良好' if roe > 10 else '一般'
                debt_tag = '稳健' if debt < 40 else '适中' if debt < 60 else '偏高'
                
                # MD 表格形式
                print(f"\n核心财务指标：\n")
                print("| 指标 | 数值 | 评价 |")
                print("|:-----|------|------|")
                print(f"| 毛利率 | {gm:.1f}% | {gm_tag} |")
                print(f"| 净利率 | {nm:.1f}% | - |")
                print(f"| ROE | {roe:.1f}% | {roe_tag} |")
                print(f"| 资产负债率 | {debt:.1f}% | {debt_tag} |")
                
                # 业绩增长（有业绩预告优先用预告，对比去年同期）
                growth = _fetch_growth_data(self.ts_code)
                if growth.get('source') and (growth.get('revenue_yi') or growth.get('netprofit_yi') or
                                             growth.get('revenue_yoy') is not None or growth.get('netprofit_yoy') is not None or
                                             growth.get('profit_dedt_yoy') is not None):
                    period = growth.get('period_desc') or '最新期'
                    rev_yi = growth.get('revenue_yi', 0) or 0
                    rev_yoy = growth.get('revenue_yoy')
                    np_yi = growth.get('netprofit_yi', 0) or 0
                    np_yoy = growth.get('netprofit_yoy')
                    dedt_yi = growth.get('profit_dedt_yi', 0) or 0
                    dedt_yoy = growth.get('profit_dedt_yoy')
                    print(f"\n业绩增长（较去年同期，数据来源：{growth['source']}，{period}）：\n")
                    print("| 指标 | 数值(亿) | 同比增速(%) |")
                    print("|:-----|---------:|------------:|")
                    _rev_yoy = f"{rev_yoy:.1f}" if rev_yoy is not None else "-"
                    _np_yoy = f"{np_yoy:.1f}" if np_yoy is not None else "-"
                    _dedt_yoy = f"{dedt_yoy:.1f}" if dedt_yoy is not None else "-"
                    print(f"| 营收 | {rev_yi:.1f} | {_rev_yoy} |")
                    print(f"| 净利润 | {np_yi:.1f} | {_np_yoy} |")
                    print(f"| 扣非净利润 | {dedt_yi:.1f} | {_dedt_yoy} |")
                
                print(f"\n> ⚠️ **【待补充】** 盈利模式定位：需结合行业特性、大模型或网络搜索补充")
                print(f"> **参考数据**：毛利率 {gm:.1f}%、净利率 {nm:.1f}%、ROE {roe:.1f}%、行业 {self.industry}")
        except:
            print("\n> 盈利能力分析暂不可用")

    def _analyze_industry_chain(self):
        print(f"\n- **产业链分析**")
        print(f"> ⚠️ **【待补充】** 产业链：无法从单一数据源一次性补全，需结合大模型/网络搜索")
        print(f"> **建议搜索**：`{self.company_name} {self.industry} 产业链 上下游` 或 `{self.industry} 产业链结构`")

    def _evaluate_model_health(self):
        print(f"\n- **商业模式五维评估**")
        analysis_data = {}
        try:
            fina = pro.fina_indicator(ts_code=self.ts_code, limit=2)
            if not fina.empty:
                analysis_data['roe'] = fina.iloc[0].get('roe', 0) or 0
                analysis_data['gm'] = fina.iloc[0].get('grossprofit_margin', 0) or 0
                analysis_data['debt'] = fina.iloc[0].get('debt_to_assets', 0) or 0
        except:
            pass
        try:
            cashflow = pro.cashflow(ts_code=self.ts_code, limit=1)
            if not cashflow.empty:
                analysis_data['op_cash'] = cashflow.iloc[0].get('n_cashflow_act', 0)
        except:
            pass
        roe = analysis_data.get('roe', 0)
        gm = analysis_data.get('gm', 0)
        debt = analysis_data.get('debt', 0)
        op_cash = analysis_data.get('op_cash', 0)
        print(f"\n> ⚠️ **【待补充】** 商业模式五维评估：需结合大模型/网络搜索深度分析")
        print(f"> **参考数据**：ROE {roe:.1f}%、毛利率 {gm:.1f}%、资产负债率 {debt:.1f}%、经营现金流{'为正' if (op_cash or 0) > 0 else '为负或为零'}")


class CompetitiveAnalyzer:
    """竞争格局分析器 - 增强版：表格化、多维度、含待补充建议"""

    def __init__(self, ts_code):
        self.ts_code = ts_code
        self.company_name = ""
        self.industry = ""
        self._load_basic_info()

    def _load_basic_info(self):
        try:
            basic = pro.stock_basic(ts_code=self.ts_code, fields='ts_code,name,industry')
            if not basic.empty:
                self.company_name = basic.iloc[0]['name']
                self.industry = basic.iloc[0]['industry']
        except:
            pass

    def analyze_competition(self):
        print("\n竞争格局分析")

        if not self.industry:
            print("> 无法获取行业信息")
            return

        self._compare_competitors()
        self._analyze_moat()
        self._print_supplement_hints()

    def _compare_competitors(self):
        """行业地位对比 - 多维度表格，确保标的公司被纳入"""
        print(f"\n- **同业对比（按市值排序）**\n")
        
        try:
            peers = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name,industry')
            industry_peers = peers[peers['industry'] == self.industry]
            
            # 确保标的公司一定在待取数列表中（stock_basic 前 N 不一定含标的）
            codes_to_fetch = list(set(industry_peers['ts_code'].tolist()[:40]) | {self.ts_code})
            
            all_metrics = []
            for code in codes_to_fetch:
                try:
                    fina = pro.fina_indicator(ts_code=code, limit=1)
                    daily = pro.daily_basic(ts_code=code, limit=1)
                    if not fina.empty and not daily.empty:
                        row_f = fina.iloc[0]
                        row_d = daily.iloc[0]
                        revenue_yi = 0
                        netprofit_yi = 0
                        try:
                            inc = pro.income(ts_code=code, limit=1, fields='revenue,n_income')
                            if not inc.empty:
                                revenue_yi = (inc.iloc[0].get('revenue', 0) or 0) / 1e8
                                netprofit_yi = (inc.iloc[0].get('n_income', 0) or 0) / 1e8
                        except Exception:
                            pass
                        name = self.company_name if code == self.ts_code else (
                            industry_peers[industry_peers['ts_code']==code]['name'].iloc[0] if len(industry_peers[industry_peers['ts_code']==code]) > 0 else code)
                        # profit_dedt 扣非净利润(元)，dt_netprofit_yoy 扣非净利润同比增速(%)
                        profit_dedt_yi = (row_f.get('profit_dedt', 0) or 0) / 1e8
                        dt_netprofit_yoy = row_f.get('dt_netprofit_yoy', 0) or 0
                        all_metrics.append({
                            'ts_code': code,
                            'name': name,
                            'end_date': row_f.get('end_date', ''),
                            'roe': row_f.get('roe', 0) or 0,
                            'market_cap': row_d.get('total_mv', 0),
                            'gm': row_f.get('grossprofit_margin', 0) or 0,
                            'revenue_yi': revenue_yi,
                            'netprofit_yi': netprofit_yi,
                            'profit_dedt_yi': profit_dedt_yi,
                            'tr_yoy': row_f.get('tr_yoy', 0) or 0,
                            'netprofit_yoy': row_f.get('netprofit_yoy', 0) or 0,
                            'dt_netprofit_yoy': dt_netprofit_yoy,
                        })
                except:
                    continue
            
            all_metrics.sort(key=lambda x: x['market_cap'], reverse=True)
            
            target_rank = None
            target_data = None
            for i, m in enumerate(all_metrics, 1):
                if m['ts_code'] == self.ts_code:
                    target_rank = i
                    target_data = m
                    break
            
            if not all_metrics:
                print("> 竞争对比数据暂不可用")
                return
            
            total = len(all_metrics)
            # 取标的或龙头报告期作为表头说明（各公司期可能略有差异）
            ref_end = (target_data or all_metrics[0]).get('end_date', '')
            period_desc = _format_report_period(ref_end) if ref_end else "最新披露"
            
            # 多维度对比表（净利润为归母净利润，扣非净利为扣除非经常损益后）
            print(f"**财务数据期**：{period_desc}\n")
            print("| 排名 | 公司 | 市值(亿) | 营收(亿) | 净利润(亿) | 扣非净利(亿) | 营收同比增速(%) | 净利同比增速(%) | 扣非同比增速(%) | ROE(%) | 毛利率(%) |")
            print("|:----:|:-----|---------:|---------:|-----------:|-------------:|------------:|------------:|------------:|-------:|----------:|")
            
            def _fmt_row(m, rank):
                cap_yi = m['market_cap'] / 1e4 if m['market_cap'] else 0
                rev_yi = m.get('revenue_yi', 0) or 0
                np_yi = m.get('netprofit_yi', 0) or 0
                dedt_yi = m.get('profit_dedt_yi', 0) or 0
                roe = m['roe'] if m['roe'] and -100 < m['roe'] < 100 else 0
                gm = m['gm'] if m['gm'] and 0 <= m['gm'] <= 100 else 0
                tr_yoy = m['tr_yoy'] if m['tr_yoy'] and -200 < m['tr_yoy'] < 500 else 0
                np_yoy = m['netprofit_yoy'] if m['netprofit_yoy'] and -500 < m['netprofit_yoy'] < 1000 else 0
                dedt_yoy = m.get('dt_netprofit_yoy', 0) or 0
                if dedt_yoy and not (-500 < dedt_yoy < 1000):
                    dedt_yoy = 0
                prefix = "★ " if m['ts_code'] == self.ts_code else ""
                return f"| {rank} | {prefix}{m['name']} | {cap_yi:.1f} | {rev_yi:.1f} | {np_yi:.1f} | {dedt_yi:.1f} | {tr_yoy:.1f} | {np_yoy:.1f} | {dedt_yoy:.1f} | {roe:.1f} | {gm:.1f} |"
            
            # 展示：取市值前10，若标的不在前10则额外追加一行
            shown = []
            for i, m in enumerate(all_metrics[:10], 1):
                shown.append(m['ts_code'])
                print(_fmt_row(m, i))
            
            # 标的若不在前10，额外追加一行
            if target_data and target_data['ts_code'] not in shown:
                print(_fmt_row(target_data, target_rank))
            
            # 标的公司地位摘要（含营收、净利润及同比）
            if target_rank and target_data:
                cap_yi = target_data['market_cap'] / 1e4 if target_data['market_cap'] else 0  # total_mv 单位万元
                rev_yi = target_data.get('revenue_yi', 0) or 0
                np_yi = target_data.get('netprofit_yi', 0) or 0
                tr_yoy = target_data.get('tr_yoy', 0) or 0
                np_yoy = target_data.get('netprofit_yoy', 0) or 0
                print(f"\n- **行业地位**：{self.company_name} 市值排名第 {target_rank}/{total} 名，市值约 {cap_yi:.1f} 亿元。")
                dedt_yi = target_data.get('profit_dedt_yi', 0) or 0
                dedt_yoy = target_data.get('dt_netprofit_yoy', 0) or 0
                print(f"- **核心业绩（最近一期）**：营收 {rev_yi:.1f} 亿元（同比增速 {tr_yoy:.1f}%），净利润 {np_yi:.1f} 亿元（同比增速 {np_yoy:.1f}%），扣非净利 {dedt_yi:.1f} 亿元（同比增速 {dedt_yoy:.1f}%）。")
                if target_rank > 1 and all_metrics:
                    leader = all_metrics[0]
                    gap = (leader['market_cap'] / target_data['market_cap'] - 1) * 100 if target_data['market_cap'] else 0
                    print(f"- 与龙头 **{leader['name']}** 相比：市值落后约 {gap:.0f}%；")
                    print(f"- ROE：{target_data['roe']:.1f}% vs 龙头 {leader['roe']:.1f}%；")
                    if target_data['tr_yoy'] and target_data['tr_yoy'] != 0:
                        print(f"- 营收同比增速：{target_data['tr_yoy']:.1f}%（高于龙头更优）。")
        except Exception as e:
            print("> 竞争对比暂不可用")

    def _analyze_moat(self):
        """护城河/壁垒分析 - 需网络搜索补充（与行业地位财务对比互补）"""
        print(f"\n- **护城河与竞争壁垒（需搜索分析）**\n")
        print("> 以下维度无法从财务数据直接得出，建议通过招股书、年报、研报、新闻搜索补充：\n\n")
        print("| 维度 | 关注点 | 建议搜索关键词 |")
        print("|:-----|:-------|:---------------|")
        print(f"| 特定客户源 | 前五大客户、客户集中度、认证/准入壁垒 | `{self.company_name} 前五大客户 主要客户` |")
        print(f"| 技术/专利壁垒 | 核心技术、专利数量、研发投入占比 | `{self.company_name} 核心技术 专利` |")
        print(f"| 供应链/产能 | 关键供应商、产能利用率、扩产节奏 | `{self.company_name} 供应商 产能` |")
        print(f"| 客户粘性 | 认证周期、切换成本、长期协议 | `{self.company_name} 客户认证 合同` |")
        print(f"| 差异化定位 | 与龙头/同业差异、细分领域优势 | `{self.company_name} vs 竞争对手 差异化` |")
        print()

    def _print_supplement_hints(self):
        """竞争维度待验证 - 精简提示"""
        print(f"\n- **竞争分析待验证**\n")
        print(f"> 细分竞争对手、产业链关系、市场份额等需网络搜索补充。建议：`{self.company_name} 竞争对手 产业链`")
        print()


def analyze_business_and_competition(ts_code):
    """主入口：执行商业模式和竞争格局分析"""
    business = BusinessModelAnalyzer(ts_code)
    business.analyze_business_model()
    
    competition = CompetitiveAnalyzer(ts_code)
    competition.analyze_competition()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 business_analysis.py <ts_code>")
        print("Example: python3 business_analysis.py 000001.SZ")
        sys.exit(1)
    
    ts_code = sys.argv[1]
    analyze_business_and_competition(ts_code)
