#!/usr/bin/env python3
"""
A股综合投研分析 - 整合七维分析框架
改进版：更好的Markdown格式输出
"""
import os
import sys
import subprocess
import re
from datetime import datetime
from io import StringIO
from urllib.parse import urlparse

# 添加技能根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_tushare_token():
    """获取Tushare Token（从环境变量或~/.bashrc）"""
    token = (os.environ.get('TUSHARE_TOKEN') or '').strip()
    
    # 如果环境变量未设置，尝试从~/.bashrc读取
    if not token:
        try:
            with open(os.path.expanduser('~/.bashrc'), 'r') as f:
                for line in f:
                    if 'TUSHARE_TOKEN' in line and 'export' in line:
                        parts = line.split('=')
                        if len(parts) >= 2:
                            token = parts[1].strip().strip('"').strip("'")
                            break
        except:
            pass
    
    return token


def search_with_kimi(query, limit=5):
    """使用 Moonshot $web_search 联网搜索（需配置 MOONSHOT_API_KEY）"""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        from kimi_search import kimi_search
        return kimi_search(query, limit=limit)
    except Exception:
        return []


class OutputCapture:
    """输出捕获器，同时打印到控制台并保存到文件"""
    def __init__(self, save_to_file=False, file_path=None):
        self.save_to_file = save_to_file
        self.file_path = file_path
        self.buffer = StringIO()
        self.file_handle = None
        if save_to_file and file_path:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            self.file_handle = open(file_path, 'w', encoding='utf-8')
    
    def write(self, text):
        """写入输出"""
        self.buffer.write(text)
        if self.file_handle:
            self.file_handle.write(text)
            self.file_handle.flush()
        sys.__stdout__.write(text)
        sys.__stdout__.flush()
    
    def flush(self):
        """刷新缓冲区"""
        if self.file_handle:
            self.file_handle.flush()
        sys.__stdout__.flush()
    
    def close(self):
        """关闭文件"""
        if self.file_handle:
            self.file_handle.close()
    
    def get_content(self):
        """获取内容"""
        return self.buffer.getvalue()


def _normalize_date_for_display(raw):
    """将日期字符串规范为 (sort_key, display_str)，无效则返回 None"""
    if not raw or str(raw).strip() in ('', '未知'):
        return None
    raw = str(raw).strip()
    # 2026-02-24 或 2026-03-10
    m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', raw)
    if m:
        y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
        return (f"{y}-{mo}-{d}", f"{y}-{mo}-{d}")
    # 2026年3月10日、2026年1月9日
    m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', raw)
    if m:
        y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
        return (f"{y}-{mo}-{d}", f"{y}-{mo}-{d}")
    # 2025年3月、2026年1月
    m = re.search(r'(\d{4})年(\d{1,2})月', raw)
    if m:
        y, mo = m.group(1), m.group(2).zfill(2)
        return (f"{y}-{mo}-01", f"{y}年{int(mo)}月")
    return None


def _parse_date_from_text(text):
    """从文本中提取日期，返回 (sort_key, display_str)。无日期时返回 ('', '近期')"""
    if not text:
        return ('', '近期')
    # 2026-02-24 或 2026-03-10
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
    if m:
        return (m.group(0), m.group(0))
    # 2026年3月10日、2026年1月9日
    m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
    if m:
        y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
        key = f"{y}-{mo}-{d}"
        return (key, key)
    # 2025年3月（无日）
    m = re.search(r'(\d{4})年(\d{1,2})月', text)
    if m:
        y, mo = m.group(1), m.group(2).zfill(2)
        return (f"{y}-{mo}-01", f"{y}年{int(mo)}月")
    # X月X日（无年，用当前年）
    m = re.search(r'(\d{1,2})月(\d{1,2})日', text)
    if m:
        y = datetime.now().year
        mo, d = m.group(1).zfill(2), m.group(2).zfill(2)
        return (f"{y}-{mo}-{d}", f"{y}-{mo}-{d}")
    return ('', '近期')


def _news_sort_key(item):
    """新闻排序：有日期的新在前，无日期的(近期)排后。日期降序(新→旧)"""
    dt = item.get('datetime', '') or ''
    if not dt or dt == '近期':
        return ('', '')
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', dt)
    if m:
        return (m.group(0), dt)
    m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', dt)
    if m:
        y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
        return (f"{y}-{mo}-{d}", dt)
    m = re.search(r'(\d{4})年(\d{1,2})月', dt)
    if m:
        y, mo = m.group(1), m.group(2).zfill(2)
        return (f"{y}-{mo}-01", dt)
    return ('', dt)


def indent_third_level_content(text):
    """
    对 - **XXX** 三级标题下的内容添加 4 空格缩进，使结构可视化。
    规则：遇到 - **XXX** 后，直到下一个 - **XXX** 或 ### / ## / --- 之前的所有行都缩进。
    """
    _indent = '    '  # 4 空格
    if not text or not text.strip():
        return text
    lines = text.split('\n')
    result = []
    in_section_content = False
    for line in lines:
        stripped = line.strip()
        is_section_header = bool(re.match(r'^-\s+\*\*[^*]+\*\*', stripped))
        is_top_level = stripped.startswith('###') or stripped.startswith('##') or stripped.startswith('---')

        if is_section_header and not is_top_level:
            in_section_content = True
            result.append(line)
        elif is_top_level:
            in_section_content = False
            result.append(line)
        elif in_section_content:
            # 已有 4 空格缩进则不再添加；若为制表符则替换为 4 空格
            if line.startswith(_indent):
                result.append(line)
            elif line.startswith('\t'):
                result.append(_indent + line.lstrip('\t'))
            else:
                result.append(_indent + line)
        else:
            result.append(line)
    return '\n'.join(result)


def fetch_stock_news_from_tushare(ts_code, company_name, industry='', limit=10, days=30):
    """
    通过 Tushare news 接口获取近期新闻，按公司名/股票代码/行业等关键词过滤。
    接口为全市场新闻，需在 title 或 content 中匹配关键词。
    """
    try:
        import tushare as ts
        from datetime import datetime, timedelta
        _token = get_tushare_token()
        if not _token:
            return []
        pro = ts.pro_api(_token)
        end = datetime.now()
        start = end - timedelta(days=days)
        start_str = start.strftime('%Y-%m-%d 00:00:00')
        end_str = end.strftime('%Y-%m-%d 23:59:59')
        code_short = ts_code.split('.')[0]
        keywords = [code_short, ts_code]
        if company_name:
            keywords.append(company_name)
            short_name = company_name.replace('股份有限公司', '').replace('有限公司', '').replace('集团', '').strip()
            if short_name and short_name != company_name:
                keywords.append(short_name)
            if len(company_name) >= 4:
                keywords.append(company_name[:4])  # 如 华海清科->华海
            if len(company_name) >= 6:
                keywords.append(company_name[2:6])  # 如 中国铝业->国铝业(取中间)
        if industry:
            keywords.append(industry)
        # 公司/代码为必选匹配，行业仅作补充（避免纯行业新闻）
        must_match = [code_short]
        if company_name:
            must_match.extend([company_name, company_name.replace('股份有限公司', '').replace('有限公司', '').replace('集团', '').strip()])
        must_match = [k for k in must_match if k and len(k) >= 2]
        keywords = list(dict.fromkeys(k for k in keywords if k and len(k) >= 2))
        seen = set()
        results = []
        for src in ['sina', 'eastmoney', 'cls', '10jqka', 'yicai', 'jinrongjie', 'wallstreetcn', 'fenghuang', 'yuncaijing']:
            try:
                df = pro.news(src=src, start_date=start_str, end_date=end_str)
                if df is None or df.empty:
                    continue
                for _, row in df.iterrows():
                    title = str(row.get('title', '') or '').strip()
                    content = str(row.get('content', '') or '').strip()
                    text = title + ' ' + content
                    if not any(m in text for m in must_match):
                        continue
                    if not any(kw in text for kw in keywords if kw):
                        continue
                    display = (title or content)[:80].replace('|', '｜').strip()
                    if not display:
                        continue
                    dedup_key = (row.get('datetime', ''), display[:40])
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    dt = row.get('datetime', '')[:19] if row.get('datetime') else 'N/A'
                    content_short = content[:200].replace('|', '｜').replace('\n', ' ').strip() if content else '-'
                    url = (row.get('url') or '').strip() if row.get('url') else ''
                    results.append({'datetime': dt, 'title': display, 'src': src, 'content': content_short, 'url': url})
                    if len(results) >= limit:
                        break
            except Exception:
                continue
            if len(results) >= limit:
                break
        return results[:limit]
    except Exception:
        return []


def run_script_and_capture(script_name, ts_code, trade_date=None):
    """运行脚本并捕获输出"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    args = ['python3', os.path.join(script_dir, script_name), ts_code]
    if trade_date:
        args.append(trade_date)
    
    result = subprocess.run(args, capture_output=True, text=True)
    return result.stdout + result.stderr


def _is_policy_relevant(title, industry, company_name):
    """过滤政策相关性：排除公司公告、无效搜索、与行业无关的通用政策"""
    if not title or len(title) < 4:
        return False
    # 排除：搜索框/占位类
    if title.startswith('搜索：') or title == '无标题':
        return False
    # 排除：公司公告/年报类（属 3.1 公告，非政策）
    exclude_company = ['股东分红', '分红回报', '年度报告', '年报', '会计政策', '募集资金', '公司章程', '公告']
    if any(kw in title for kw in exclude_company):
        return False
    # 排除：Tushare npr 常见但与具体行业无关的通用政策
    exclude_generic = [
        '开发区升级', '开发区更名', '高新技术产业开发区',
        '自然科学基金条例', '科学技术奖励条例', '科学技术奖励',
    ]
    if any(kw in title for kw in exclude_generic):
        return False
    # 排除：人工智能+ 等泛科技政策（非半导体/元器件/通信等科技行业时不相关）
    tech_industries = ['半导体', '元器件', '通信设备', '电气设备', '软件', '互联网']
    if '人工智能' in title and industry and not any(t in industry for t in tech_industries):
        return False
    return True


# 域名 -> 中文来源名称映射
URL_SOURCE_NAMES = {
    'sse.com.cn': '上海证券交易所',
    'szse.com.cn': '深圳证券交易所',
    'bse.com.cn': '北京证券交易所',
    'eastmoney.com': '东方财富',
    'cninfo.com.cn': '巨潮资讯网',
    'sina.com.cn': '新浪',
    '163.com': '网易',
    'hexun.com': '和讯网',
    'finance.sina.com.cn': '新浪财经',
    '10jqka.com.cn': '同花顺',
    'eeo.com.cn': '经济观察网',
    'xueqiu.com': '雪球',
}


def _extract_source_from_url(url):
    """从 URL 提取来源，优先返回中文名称"""
    if not url or url == '#':
        return None
    try:
        parsed = urlparse(url if url.startswith(('http://', 'https://')) else 'https://' + url)
        netloc = parsed.netloc or parsed.path.split('/')[0]
        netloc = netloc.lower().strip()
        if not netloc:
            return None
        # 去掉常见前缀子域名
        for prefix in ('www.', 'wap.', 'm.', 'finance.', 'static.', 'data.', 'api.', 'stock.'):
            if netloc.startswith(prefix):
                netloc = netloc[len(prefix):]
                break
        if not netloc:
            return None
        # 循环去掉子域名前缀，直到匹配映射；避免把 xxx.com.cn 缩成 com.cn
        seen = set()
        while netloc and netloc not in seen:
            if netloc in URL_SOURCE_NAMES:
                return URL_SOURCE_NAMES[netloc]
            seen.add(netloc)
            parts = netloc.split('.')
            if len(parts) <= 2:
                break  # xxx.com 不再缩短
            if len(parts) == 3 and parts[-2:] == ['com', 'cn']:
                break  # 10jqka.com.cn，避免缩成 com.cn
            if len(parts) == 3 and parts[-1] == 'cn':
                break  # xxx.org.cn 等
            netloc = '.'.join(parts[1:])
        return netloc if netloc and netloc != 'com.cn' else None
    except Exception:
        return None


def _parse_policy_year(date_str):
    """从日期字符串提取年份，无法解析时返回 None"""
    if not date_str:
        return None
    m = re.search(r'20(\d{2})', str(date_str))
    return int(m.group(1)) + 2000 if m else None


def _policy_sort_key(r):
    """用于按发布时间倒序排序：(年, 月)，新的在前，未知在最后"""
    date_str = r.get('date') or ''
    year = _parse_policy_year(date_str) or 0
    month = 0
    m = re.search(r'[-年](\d{1,2})月?', str(date_str))
    if m:
        month = int(m.group(1))
    m2 = re.search(r'20\d{2}-(\d{1,2})', str(date_str))
    if m2:
        month = int(m2.group(1))
    return (-year, -month)  # 负值使新的排前面


def _infer_policy_type(title):
    """从标题粗判政策性质，无法判断时返回待补充"""
    if not title:
        return '待补充'
    if any(kw in title for kw in ['扶持', '鼓励', '补贴', '支持', '奖励']):
        return '支持类'
    if any(kw in title for kw in ['意见', '规划', '办法', '条例', '规定', '通知']):
        return '指导类'
    return '待补充'


def _infer_content_type(title):
    """判断内容类型：政策原文 or 政策解读"""
    if not title:
        return '待补充'
    if any(kw in title for kw in ['解读', '分析', '点评', '梳理', '汇总']):
        return '政策解读'
    return '政策原文'


# 行业 -> Tushare npr 政策类型映射（ptype 约110类，此处为常用映射）
INDUSTRY_TO_NPR_PTYPE = {
    '白酒': '农业、畜牧业、渔业', '饮料制造': '农业、畜牧业、渔业', '食品加工': '农业、畜牧业、渔业',
    '化工': '科技', '化工原料': '科技', '化学制品': '科技',
    '半导体': '科技', '元器件': '科技', '电气设备': '科技', '通信设备': '科技',
    '汽车配件': '科技', '专用机械': '科技',
    '化学制药': '卫生', '生物制药': '卫生', '医疗保健': '卫生', '医药商业': '卫生',
    '银行': '对外经贸合作', '保险': '对外经贸合作', '证券': '对外经贸合作',
    '建筑工程': '城市规划', '房地产': '土地',
}


def fetch_policy_from_npr(industry, limit=10):
    """从 Tushare 国家政策法规库 npr 接口获取政策（需单独开权限）"""
    try:
        import tushare as ts
        _token = get_tushare_token()
        pro = ts.pro_api(_token) if _token else ts.pro_api()
        # 最近 2 年
        end_dt = datetime.now()
        start_dt = datetime(end_dt.year - 2, end_dt.month, end_dt.day)
        end_str = end_dt.strftime('%Y-%m-%d 23:59:59')
        start_str = start_dt.strftime('%Y-%m-%d 00:00:00')
        ptype = INDUSTRY_TO_NPR_PTYPE.get(industry, '科技')
        df = pro.npr(ptype=ptype, start_date=start_str, end_date=end_str, fields='pubtime,title,pcode,puborg,url')
        if df.empty or len(df) == 0:
            return []
        results = []
        for _, row in df.head(limit).iterrows():
            pubtime = row.get('pubtime', '')
            if hasattr(pubtime, 'strftime'):
                date_str = pubtime.strftime('%Y-%m-%d')
            else:
                date_str = str(pubtime)[:10] if pubtime else '近期'
            url = (row.get('url', '') or '').strip()
            results.append({'title': str(row.get('title', ''))[:80], 'date': date_str, 'source': 'npr', 'pcode': row.get('pcode', ''), 'url': url})
        return results
    except Exception:
        return []


def print_industry_policy_framework(industry, company_name=''):
    """打印行业政策框架（当搜索无结果时使用）——输出待补充，不输出静态模板"""
    print("> ⚠️ **【待补充】** 政策分析：相关政策、政策目标、对公司的影响分析")
    print(f"> **建议搜索**：`{industry} 政策 2025` 或 `{company_name} 政策影响`")
    print()


def run_analysis(ts_code, trade_date=None, save_md=False):
    """运行完整分析"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(script_dir)
    
    output_capture = None
    md_file_path = None
    if save_md:
        date_str = trade_date if trade_date else datetime.now().strftime('%Y%m%d')
        code_short = ts_code.split('.')[0]
        reports_dir = os.path.join(skill_dir, 'raw_reports')
        os.makedirs(reports_dir, exist_ok=True)
        md_file_path = os.path.join(reports_dir, f'{code_short}_深度研报_{date_str}.md')
        output_capture = OutputCapture(save_to_file=True, file_path=md_file_path)
        old_stdout = sys.stdout
        sys.stdout = output_capture
    
    try:
        # 提前获取公司名称用于标题
        company_name = ""
        industry = ""
        try:
            import tushare as ts
            _token = get_tushare_token()
            pro = ts.pro_api(_token) if _token else ts.pro_api()
            stock_basic = pro.stock_basic(ts_code=ts_code)
            if not stock_basic.empty:
                company_name = stock_basic.iloc[0]['name']
                industry = stock_basic.iloc[0]['industry']
        except:
            pass
        title_name = company_name if company_name else "A股"
        print(f"# 🔍 {title_name}深度投研分析报告\n")
        print(f"- **股票代码**: {ts_code}")
        print(f"- **报告日期**: {trade_date if trade_date else datetime.now().strftime('%Y%m%d')}\n")
        print("> **分析框架**：宏观分析 → 基本面分析 → 消息面分析 → 技术面分析 → 投研结论\n")
        print("---\n")  # 分隔报告元信息与正文
        outputs = {}
        
        # 一、宏观分析
        date_str = trade_date if trade_date else datetime.now().strftime('%Y%m%d')
        print("\n## 一、宏观分析\n")
        print(f"### 1.1 市场走势（{date_str}）\n")
        fund_output = run_script_and_capture('fundamental_analysis.py', ts_code, trade_date)
        
        # 提取宏观分析部分（含【大盘走势】【行业指数走势】【大盘走势总结】【宏观关注点】）
        if '- **大盘走势**' in fund_output:
            macro_start = fund_output.find('- **大盘走势**')
            macro_section = fund_output[macro_start:]
            end_markers = ['📈 公司基本面', '【公司概况】', '---\n📈 公司']
            for marker in end_markers:
                if marker in macro_section:
                    macro_section = macro_section.split(marker)[0]
                    break
            print(indent_third_level_content(macro_section))
        else:
            print(indent_third_level_content(fund_output))
        
        # 1.2 政策分析 - 先尝试搜索实际政策（company_name/industry 已在开头获取）
        print("\n### 1.2 政策分析\n")
        
        # 执行政策搜索：优先 Tushare npr，补充 kimi_search
        policy_results = []
        npr_results = []
        if company_name and industry:
            # 1. Tushare 国家政策法规库 npr（需单独开权限）
            # npr_results = fetch_policy_from_npr(industry, limit=8)
            # if npr_results:
            #     policy_results.extend(npr_results)

            # 2. kimi 网络搜索补充（多角度覆盖行业政策）
            _year = datetime.now().year
            _last_year = datetime.now().year - 1
            search_queries = [
                f"总结2025-至今与“{company_name}”公司（代码：{ts_code}，行业：{industry}）的相关政策，只要最相关、最直接、最新的政策，比如十五五相关政策，与政策无关的信息不要返回",
            ]
            for query in search_queries:
                try:
                    results = search_with_kimi(query, limit=10)
                    if results:
                        for r in results:
                            r['source'] = r.get('source', 'kimi')
                            r['date'] = r.get('date', '未知')
                            if not r.get('snippet') and r.get('title'):
                                r['snippet'] = ''
                        policy_results.extend(results)
                except:
                    pass

            # 构建政策段落并统一缩进
            policy_lines = [f"- **分析对象**：{company_name}（{ts_code}）所属行业：{industry}\n"]
            if policy_results:
                seen_keys = set()
                unique_results = []
                def _title_key(t):
                    return (t or '')[:50].strip()
                for r in policy_results:
                    key = _title_key(r.get('title'))
                    if key and key not in seen_keys:
                        seen_keys.add(key)
                        unique_results.append(r)
                # 仅保留 2025 年及以后的政策，按时间倒序（新的在前）
                filtered = [r for r in unique_results if (_parse_policy_year(r.get('date')) or 0) >= 2025]
                filtered.sort(key=_policy_sort_key)

                if filtered:
                    policy_lines.append("- **最新政策动态**")
                    policy_lines.append("")
                    policy_lines.append("| 发布时间 | 标题 | 内容摘要 | 链接 |")
                    policy_lines.append("|:---------|:-----|:---------|:-----|")
                    for result in filtered[:8]:
                        date = result.get('date', '未知')
                        title = (result.get('title', '') or '')[:55].replace('|', '｜')
                        url = result.get('url', '') or ''
                        url_cell = f"[链接]({url})" if url and url != '#' else '-'
                        summary = (result.get('snippet', '') or '').strip()[:100].replace('|', '｜').replace('\n', ' ')
                        summary = summary if summary else '待补充'
                        policy_lines.append(f"| {date} | {title} | {summary} | {url_cell} |")
                    policy_lines.append("")
                    policy_lines.append("- **政策分析**\n")
                    policy_lines.append("> ⚠️ **【待补充】** 政策目标、适用时间、短期/中期影响、对公司的具体影响（需基于搜索结果补充）")
                    policy_lines.append("")
                else:
                    policy_lines.append("> ⚠️ **【待补充】** 政策分析：相关政策、政策目标、对公司的影响分析")
                    policy_lines.append(f"> **建议搜索**：`{industry} 政策 2025` 或 `{company_name} 政策影响`")
                    policy_lines.append("")
            else:
                policy_lines.append("> ⚠️ **【待补充】** 政策分析：相关政策、政策目标、对公司的影响分析")
                policy_lines.append(f"> **建议搜索**：`{industry} 政策 2025` 或 `{company_name} 政策影响`")
                policy_lines.append("")
            print(indent_third_level_content("\n".join(policy_lines)))
        else:
            print(indent_third_level_content("\n> ⚠️ **【待补充】** 政策分析：无法获取公司/行业信息\n> **建议**：手动指定股票后重试，或搜索 `行业名 政策 2025`"))
        
        outputs['fundamental'] = fund_output
        
        # ========== 第二章：仅 2.1；2.2/2.3 及第三～六章仍注释 ==========
        # 二、基本面分析（--- 仅用于一级章节之间）
        print("\n---\n")
        print("## 二、基本面分析\n")
        
        # 2.1 商业模式（包含产业链分析）
        print("\n### 2.1 商业模式深度解析\n")
        business_output = run_script_and_capture('business_analysis.py', ts_code, trade_date)
        if '竞争格局分析' in business_output:
            # 按「竞争格局分析」切分：2.1 仅商业模式，2.2 仅竞争格局
            parts = business_output.split('竞争格局分析', 1)
            biz_section = parts[0].strip()
            # 去掉开头的「商业模式分析」行，避免与 2.1 标题重复
            if biz_section.startswith('商业模式分析'):
                biz_section = biz_section.replace('商业模式分析', '', 1).lstrip('\n')
            print(indent_third_level_content(biz_section))
        else:
            print(indent_third_level_content(business_output))
        
        # 2.2 竞争格局
        print("\n### 2.2 竞争格局全面评估\n")
        if '竞争格局分析' in business_output:
            comp_section = business_output.split('竞争格局分析', 1)[1].lstrip('\n')
            print(indent_third_level_content(comp_section))
        else:
            print("> 竞争格局分析数据未完整生成")
        
        # 2.3 市场预期分析
        print("\n### 2.3 市场预期深度分析\n")
        expectation_output = run_script_and_capture('market_expectation_analysis.py', ts_code, trade_date)
        # 直接打印精简版输出
        if '市场预期分析' in expectation_output:
            start = expectation_output.find('市场预期分析')
            print(indent_third_level_content(expectation_output[start:]))
        else:
            print(indent_third_level_content(expectation_output))
        outputs['expectation'] = expectation_output
        
        # 三、消息面分析
        print("\n---\n")
        print("\n## 三、消息面分析\n")
        
        print("\n### 3.1 近期公告汇总\n")
        news_output = run_script_and_capture('news_analysis.py', ts_code, trade_date)
        outputs['news'] = news_output
        
        # 3.1：仅【近期公告汇总】到【机构研报】之前（公告列表+分析指引）
        news_for_report = []
        if '【近期公告汇总' in news_output:
            start = news_output.find('【近期公告汇总')
            end = news_output.find('【机构研报')
            if end == -1:
                end = len(news_output)
            section = news_output[start:end]
            lines = section.split('\n')
            buf = []
            in_guidance = False
            for line in lines:
                if '【公告汇总分析】' in line:
                    if buf:
                        news_for_report.append('- **公告列表**\n')
                        news_for_report.extend(buf)
                        buf = []
                    news_for_report.append('- **公告汇总分析**（待补充）\n')
                    in_guidance = True
                elif in_guidance and line.strip():
                    news_for_report.append(line)
                elif not in_guidance and line.strip() and '【近期公告汇总' not in line:
                    buf.append(line)
            if buf and '- **公告列表**' not in str(news_for_report):
                news_for_report = ['- **公告列表**\n'] + buf + news_for_report
        if not news_for_report:
            news_for_report = ['- **公告列表**\n', '> 暂无近期公告数据（需 anns_d 权限或 kimi_search 补充）']
        print(indent_third_level_content('\n'.join(news_for_report)))
        
        # 3.2：机构研报
        print("\n### 3.2 机构研报\n")
        research_for_report = []
        if '【机构研报' in news_output:
            start = news_output.find('【机构研报')
            end = news_output.find('【资本运作')
            if end == -1:
                end = len(news_output)
            section = news_output[start:end]
            for line in section.split('\n'):
                if line.strip() and '【机构研报' not in line:
                    research_for_report.append(line)
        if research_for_report:
            print(indent_third_level_content('- **研报明细**\n\n' + '\n'.join(research_for_report)))
            print(indent_third_level_content('\n- **研报观点汇总分析**（待补充）\n> ⚠️ **【待补充】** 请基于以上研报列表及链接，总结各机构核心观点、目标价/评级、重要信息，并提炼一致性判断及分歧点'))
        else:
            print(indent_third_level_content('- **研报明细**\n> 近6个月暂无机构研报覆盖'))
        
        print("\n### 3.3 行业个股新闻\n")
        news_items = fetch_stock_news_from_tushare(ts_code, company_name, industry=industry, limit=10, days=30)
        # 使用 kimi_search 补充更多新闻（需配置 MOONSHOT_API_KEY）
        _year = datetime.now().year
        existing_titles = {item.get('title', '')[:40] for item in news_items}
        kimi_news = search_with_kimi(f"{company_name or ts_code} 新闻 {_year}", limit=6)
        for r in kimi_news:
            tit = (r.get('title') or '')[:80].replace('|', '｜').strip()
            snippet = (r.get('snippet') or '')[:200].replace('|', '｜').replace('\n', ' ').strip()
            # 过滤模型返回的无效结果：工具调用占位符、搜索占位标题
            if tit.startswith('搜索：') or '$web_search' in snippet or '$web_search' in tit:
                continue
            if not tit or tit[:40] in existing_titles:
                continue
            existing_titles.add(tit[:40])
            snippet = snippet or '-'
            # 优先使用模型返回的 date 字段，否则从 snippet 解析
            norm = _normalize_date_for_display(r.get('date'))
            _sort_key, _disp = (norm if norm else _parse_date_from_text(snippet))
            url = (r.get('url') or '').strip()
            if url == '#':
                url = ''
            news_items.append({
                'datetime': _disp,
                'title': tit,
                'src': 'kimi',
                'content': snippet,
                'url': url,
            })
                
        # 按时间排序（新→旧），无日期的排最后；统一格式
        news_items.sort(key=_news_sort_key, reverse=True)
        if news_items:
            news_lines = ["| 时间 | 标题 | 来源 | 内容 |", "|:-----|:-----|:-----|:-----|"]
            for item in news_items[:15]:
                content = item.get('content', '-') or '-'
                url = item.get('url', '') or ''
                src_from_url = _extract_source_from_url(url)
                src_display = src_from_url or item.get('src', '-') or '-'
                if url and url != '#' and src_from_url:
                    src_display = f"[{src_from_url}]({url})"
                elif url and url != '#' and not src_from_url:
                    src_display = f"[链接]({url})"
                news_lines.append(f"| {item['datetime']} | {item['title']} | {src_display} | {content} |")
            print(indent_third_level_content('- **近期新闻**\n\n' + '\n'.join(news_lines)))
            print(indent_third_level_content('\n- **新闻汇总分析**（待补充）\n> ⚠️ **【待补充】** 请基于以上新闻提炼关键信息、市场情绪及对公司的潜在影响。'))
        else:
            print(indent_third_level_content('- **近期新闻**\n> 近1个月暂无相关新闻（Tushare news 接口需单独权限）\n> 建议使用 kimi_search 补充：`{} 新闻 {}`'.format(company_name or ts_code, _year)))
        
        # # print("\n### 3.5 研报交叉验证（近一年）\n")
        # # report_output = run_script_and_capture('report_analysis.py', ts_code, trade_date)
        # # print(report_output)
        # # outputs['report'] = report_output
        # #
        # 四、技术面分析
        print("\n## 四、技术面分析\n")
        
        print("\n### 4.1 📊 技术指标分析（基于数据计算）\n")
        tech_output = run_script_and_capture('technical_analysis.py', ts_code, trade_date)
        print(tech_output)
        outputs['technical'] = tech_output
        #
        print("\n### 4.2 👁️ 视觉分析（基于K线图解读）\n")
        print("> ⚠️ **【待补充】**（可由 Agent 指派 subagent 执行）\n")
        print("> 1. **读取 K 线图**：`read charts/{}_kline.png`".format(ts_code.replace('.', '_')))
        print("> 2. **阅读文档**：`references/wave_structure_abc.md`")
        print("> 3. **根据 K 线图进行趋势结构判断（必遵参考）**：完成 ABC 三浪划分 → 回撤比例/时间/量能/MACD 四维打分 → **趋势结构得分（0～100）**与**强弱结论** → **是否在合适买点（B 末/C 初）**。输出中须包含得分、强弱结论及买点位置判断。\n")
        
        # 五、投研结论
        print("\n## 五、投研结论")
        print("\n> ⚠️ **投研结论需要基于以上分析人工撰写**\n")
        print("**应包含**：五维交叉验证、综合评级、交易预案、操作建议、风险提示")
        
        # 六、数据来源
        print(f"""
\n## 六、数据来源与免责声明

\n### 数据来源汇总
        
| 章节 | 数据类型 | 来源/接口 |
|:-----|:---------|:----------|
| 一、宏观分析 | 股票基本信息 | Tushare - pro.stock_basic() |
| | 大盘指数 | Tushare - pro.index_daily() |
| | A股日线/涨跌家数 | Tushare - pro.daily() |
| | 行业指数 | Tushare - pro.ths_daily() |
| | GDP/PMI/Shibor/汇率 | Tushare - pro.cn_gdp / cn_pmi / shibor / fx_daily() |
| | 政策分析 | Kimi Moonshot API - $web_search 联网搜索 |
| 三、消息面分析 | 近期公告 | Tushare - pro.anns_d()（需单独权限） |
| | 机构研报 | Tushare - pro.research_report() |
| | 行业新闻 | Tushare - pro.news()；Kimi $web_search 补充 |
| 四、技术面分析 | 日线/K线 | Tushare - pro.daily() / pro.adj_factor() |
| | 换手率等 | Tushare - pro.daily_basic() |
        
\n### 免责声明

- **数据来源**: Tushare Pro API、Kimi Moonshot 联网搜索、东方财富等公开数据平台
- **报告生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **免责声明**: 本报告仅供参考，不构成投资建议
- **风险提示**: 股市有风险，投资需谨慎
        """)
        # ========== 注释结束 ==========
        
        if save_md and md_file_path:
            print(f"\n---\n\n✅ 研报已保存至: `{md_file_path}`")
    
    finally:
        if output_capture:
            sys.stdout = old_stdout
            output_capture.close()
            return md_file_path
    
    return None


if __name__ == '__main__':
    args = sys.argv[1:]
    save_md = '--save-md' in args
    
    if save_md:
        args.remove('--save-md')
    
    if len(args) < 1:
        print("用法: python3 research_report.py <股票代码> [日期YYYYMMDD] [--save-md]")
        print("示例: python3 research_report.py 000001.SZ")
        print("      python3 research_report.py 600519.SH 20260302")
        print("      python3 research_report.py 688585.SH --save-md")
        sys.exit(1)
    
    ts_code = args[0]
    trade_date = args[1] if len(args) > 1 else None
    
    md_path = run_analysis(ts_code, trade_date, save_md)
    
    if md_path and save_md:
        sys.__stdout__.write(f"\n📄 MD文件路径: {md_path}\n")
