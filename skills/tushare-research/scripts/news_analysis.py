#!/usr/bin/env python3
"""
A股消息面分析脚本 - 使用Tushare数据
包含：业绩公告（近3个月）、资本运作、重大事项
优化：研报单独详细列出，一致性预期总结
"""
import os
import sys
import tushare as ts
import pandas as pd
from datetime import datetime, timedelta

# 初始化Tushare（从环境变量 TUSHARE_TOKEN 传入）
_token = (os.environ.get('TUSHARE_TOKEN') or '').strip()
pro = ts.pro_api(_token) if _token else ts.pro_api()

# ==================== 行业分析知识库 ====================

def get_industry_policy_keywords(industry):
    """获取行业政策关键词映射"""
    policy_map = {
        # 新能源/电力
        '电气设备': {
            'category': '新能源产业链',
            'policy_direction': '大力扶持',
            'key_policies': [
                '双碳目标（2030碳达峰/2060碳中和）',
                '新能源发电装机规划',
                '储能产业政策',
                '智能电网建设',
                '分布式光伏整县推进'
            ],
            'policy_risks': [
                '补贴退坡影响',
                '电网消纳瓶颈',
                '原材料价格波动（硅料、锂等）'
            ]
        },
        '电力': {
            'category': '公用事业',
            'policy_direction': '改革深化',
            'key_policies': [
                '电力市场化改革',
                '煤电容量电价机制',
                '绿电交易机制',
                '跨省跨区输电',
                '电力现货市场建设'
            ],
            'policy_risks': [
                '煤价波动对火电盈利影响',
                '新能源消纳压力',
                '电价管制风险'
            ]
        },
        # 半导体/科技
        '半导体': {
            'category': '战略性新兴产业',
            'policy_direction': '国产替代',
            'key_policies': [
                '集成电路大基金',
                '国产替代专项政策',
                '设备材料国产化',
                '先进制程攻关',
                '封测产业扶持'
            ],
            'policy_risks': [
                '美国技术封锁升级',
                '产能过剩风险（成熟制程）',
                '研发投入周期长'
            ]
        },
        '元器件': {
            'category': '电子制造',
            'policy_direction': '产业升级',
            'key_policies': [
                '基础电子元器件产业发展',
                'MLCC等被动元件国产替代',
                '汽车电子产业扶持',
                '5G基站建设'
            ],
            'policy_risks': [
                '下游消费电子需求波动',
                '日韩厂商竞争压力'
            ]
        },
        # 医药
        '医药生物': {
            'category': '民生保障',
            'policy_direction': '集采常态化',
            'key_policies': [
                '药品/器械集采扩围',
                '医保谈判（国谈）',
                '创新药审评加速',
                '中医药振兴',
                '医疗新基建'
            ],
            'policy_risks': [
                '集采降价压力',
                '医保控费趋严',
                '创新药内卷（同质化严重）'
            ]
        },
        '医疗器械': {
            'category': '高端制造',
            'policy_direction': '国产替代+集采',
            'key_policies': [
                '高端医疗器械国产替代',
                '医疗设备更新改造贴息贷款',
                '创新器械审评审批改革'
            ],
            'policy_risks': [
                '高值耗材集采扩围',
                'DRG/DIP支付方式改革影响'
            ]
        },
        # 消费
        '食品饮料': {
            'category': '大消费',
            'policy_direction': '促消费',
            'key_policies': [
                '扩大内需战略',
                '消费复苏刺激政策',
                '食品安全监管强化'
            ],
            'policy_risks': [
                '消费复苏不及预期',
                '原材料成本上涨',
                '食品安全事件'
            ]
        },
        '白酒': {
            'category': '大消费',
            'policy_direction': '规范发展',
            'key_policies': [
                '白酒新国标实施',
                '消费税改革预期',
                '限制公款消费常态化'
            ],
            'policy_risks': [
                '消费税政策变化',
                '年轻消费群体流失',
                '渠道库存去化压力'
            ]
        },
        # 汽车
        '汽车整车': {
            'category': '制造业支柱',
            'policy_direction': '新能源转型',
            'key_policies': [
                '新能源汽车购置税减免延续',
                '双积分政策',
                '汽车以旧换新补贴',
                '充电桩基础设施建设',
                '智能网联汽车准入'
            ],
            'policy_risks': [
                '补贴退坡',
                '价格战持续',
                '产能过剩隐忧'
            ]
        },
        '汽车零部件': {
            'category': '汽车产业链',
            'policy_direction': '电动化/智能化',
            'key_policies': [
                '新能源汽车零部件国产化',
                '汽车芯片自主可控',
                '线控底盘/智能驾驶扶持'
            ],
            'policy_risks': [
                '整车厂年降压力',
                '技术路线切换风险'
            ]
        },
        # 房地产/建材
        '房地产开发': {
            'category': '传统行业',
            'policy_direction': '防风险+稳预期',
            'key_policies': [
                '保交楼专项借款',
                '房企融资三支箭',
                '限购限贷政策优化',
                '城中村改造',
                '保障房建设'
            ],
            'policy_risks': [
                '销售复苏持续性存疑',
                '债务违约风险',
                '人口结构长期压力'
            ]
        },
        '建材': {
            'category': '地产链',
            'policy_direction': '供给侧优化',
            'key_policies': [
                '水泥玻璃产能置换',
                '绿色建材推广',
                '光伏玻璃产能放开'
            ],
            'policy_risks': [
                '地产需求下滑',
                '产能过剩',
                '环保限产'
            ]
        },
        # 金融
        '银行': {
            'category': '金融系统核心',
            'policy_direction': '服务实体',
            'key_policies': [
                'LPR改革深化',
                '存款利率市场化',
                '房地产融资协调机制',
                '普惠金融定向降准',
                '资本新规实施'
            ],
            'policy_risks': [
                '净息差持续收窄',
                '房地产贷款不良暴露',
                '地方债务风险'
            ]
        },
        '证券': {
            'category': '资本市场',
            'policy_direction': '高质量发展',
            'key_policies': [
                '全面注册制改革',
                '活跃资本市场',
                '中长期资金入市',
                '并购重组市场化'
            ],
            'policy_risks': [
                '市场波动影响经纪收入',
                'IPO/再融资节奏变化',
                '佣金率下行'
            ]
        },
        '保险': {
            'category': '金融保障',
            'policy_direction': '回归保障',
            'key_policies': [
                '偿二代二期工程',
                '个人养老金制度',
                '健康险税优政策',
                '保险资金运用改革'
            ],
            'policy_risks': [
                '利率下行影响投资收益',
                '代理人渠道转型阵痛',
                '车险综改压力'
            ]
        },
        # 周期品
        '有色金属': {
            'category': '周期资源',
            'policy_direction': '保供稳价',
            'key_policies': [
                '战略性矿产资源安全',
                '电解铝产能天花板',
                '稀有金属出口管制',
                '再生金属利用'
            ],
            'policy_risks': [
                '全球衰退风险影响需求',
                '新能源金属供给释放',
                '汇率波动'
            ]
        },
        '小金属': {
            'category': '战略资源',
            'policy_direction': '保供稳价+战略储备',
            'key_policies': [
                '战略性矿产资源安全（钴/铜/钼等）',
                '稀有金属出口管制（钨/钼/稀土等）',
                '海外资源开发支持政策',
                '再生金属利用',
                '矿产资源权益金改革'
            ],
            'policy_risks': [
                '资源国政策变化（资源民族主义）',
                '出口管制政策调整',
                '海外资产安全风险',
                '环保要求趋严'
            ]
        },
        '煤炭': {
            'category': '能源安全',
            'policy_direction': '保供+转型',
            'key_policies': [
                '煤炭保供稳价',
                '长协煤机制',
                '煤电联营',
                '煤炭清洁高效利用'
            ],
            'policy_risks': [
                '新能源替代长期压力',
                '碳排放约束趋严',
                '煤价调控风险'
            ]
        },
        '钢铁': {
            'category': '传统制造',
            'policy_direction': '去产能+绿色化',
            'key_policies': [
                '粗钢产量压减',
                '超低排放改造',
                '电炉钢发展',
                '废钢回收利用'
            ],
            'policy_risks': [
                '地产需求下滑',
                '铁矿石对外依存度高',
                '碳达峰约束'
            ]
        },
        '化工': {
            'category': '中游制造',
            'policy_direction': '安全+绿色',
            'key_policies': [
                '化工园区安全整治',
                '双碳目标约束',
                '新材料产业扶持',
                '产能置换政策'
            ],
            'policy_risks': [
                '安全生产事故风险',
                '环保限产',
                '原油价格波动'
            ]
        },
        # 通信
        '通信设备': {
            'category': '信息基础设施',
            'policy_direction': '新基建',
            'key_policies': [
                '5G网络深度覆盖',
                '千兆光网建设',
                '算力网络布局',
                '卫星互联网发展',
                '6G技术研发'
            ],
            'policy_risks': [
                '运营商资本开支波动',
                '海外市场受限',
                '技术迭代风险'
            ]
        },
        '通信服务': {
            'category': '电信运营',
            'policy_direction': '提速降费+数字化转型',
            'key_policies': [
                '5G应用创新',
                '算力网络建设',
                '数据要素市场化',
                '电信普遍服务'
            ],
            'policy_risks': [
                '提速降费压力',
                '传统业务饱和',
                'OTT业务替代'
            ]
        },
        # 计算机/互联网
        '计算机': {
            'category': '数字经济',
            'policy_direction': '自主可控',
            'key_policies': [
                '信创产业推进',
                '数据要素市场化',
                '人工智能+行动',
                '东数西算工程',
                '国产操作系统替代'
            ],
            'policy_risks': [
                '财政IT支出承压',
                '信创招标节奏波动',
                '人力成本上升'
            ]
        },
        '互联网': {
            'category': '平台经济',
            'policy_direction': '常态化监管',
            'key_policies': [
                '平台经济规范健康发展',
                '数据安全法/个人信息保护法',
                '反垄断常态化',
                '支持平台企业参与国际竞争'
            ],
            'policy_risks': [
                '监管政策不确定性',
                '流量红利见顶',
                '国际竞争加剧'
            ]
        },
        # 军工
        '国防军工': {
            'category': '国家安全',
            'policy_direction': '装备现代化',
            'key_policies': [
                '十四五装备建设规划',
                '国防预算增长',
                '军品定价机制改革',
                '军民融合深度发展',
                '国产大飞机产业链'
            ],
            'policy_risks': [
                '订单交付节奏波动',
                '军审定价压力',
                '技术泄密风险'
            ]
        },
        # 传媒
        '传媒': {
            'category': '内容产业',
            'policy_direction': '规范+扶持',
            'key_policies': [
                '游戏版号常态化发放',
                '未成年人防沉迷',
                '短剧/微剧监管',
                '文化出海支持',
                'AI生成内容监管'
            ],
            'policy_risks': [
                '内容监管趋严',
                '版号发放节奏',
                'AI对内容生产冲击'
            ]
        },
        # 交通运输
        '交通运输': {
            'category': '物流基础设施',
            'policy_direction': '降本增效',
            'key_policies': [
                '交通强国建设',
                '物流降本增效',
                '多式联运发展',
                '智慧交通建设',
                '快递进村/出海'
            ],
            'policy_risks': [
                '燃油成本波动',
                '价格战持续',
                '人力成本上升'
            ]
        },
        '航运港口': {
            'category': '外贸物流',
            'policy_direction': '枢纽建设',
            'key_policies': [
                '港口资源整合',
                '智慧港口建设',
                '航运中心建设',
                '绿色航运'
            ],
            'policy_risks': [
                '全球贸易波动',
                '运价周期性波动',
                '地缘政治冲突'
            ]
        },
        # 农林牧渔
        '农林牧渔': {
            'category': '民生基础',
            'policy_direction': '保供稳价',
            'key_policies': [
                '粮食安全战略',
                '生猪产能调控',
                '种业振兴',
                '农业现代化',
                '乡村振兴'
            ],
            'policy_risks': [
                '猪周期波动',
                '极端天气影响',
                '疫病风险'
            ]
        },
        # 机械设备
        '机械设备': {
            'category': '装备制造',
            'policy_direction': '高端化+智能化',
            'key_policies': [
                '高端数控机床发展',
                '工业机器人推广',
                '设备更新改造',
                '专精特新培育',
                '智能制造示范'
            ],
            'policy_risks': [
                '下游投资周期波动',
                '核心零部件进口依赖',
                '价格战'
            ]
        },
        # 建筑装饰
        '建筑装饰': {
            'category': '基建地产链',
            'policy_direction': '稳增长',
            'key_policies': [
                '基建投资托底',
                '城市更新行动',
                '装配式建筑推广',
                '一带一路建设'
            ],
            'policy_risks': [
                '地产新开工下滑',
                '地方政府债务约束',
                '应收账款风险'
            ]
        },
        # 轻工制造
        '轻工制造': {
            'category': '出口导向',
            'policy_direction': '产业升级',
            'key_policies': [
                '家居以旧换新',
                '出口转内销支持',
                '绿色包装推广',
                '智能制造改造'
            ],
            'policy_risks': [
                '海外需求波动',
                '汇率波动',
                '原材料价格上涨'
            ]
        },
        # 纺织服装
        '纺织服装': {
            'category': '传统出口',
            'policy_direction': '品牌化+出海',
            'key_policies': [
                '纺织业高质量发展',
                '国潮品牌扶持',
                '跨境电商支持',
                'RCEP关税优惠'
            ],
            'policy_risks': [
                '海外订单转移东南亚',
                '棉花价格波动',
                '品牌升级压力'
            ]
        },
        # 社会服务
        '社会服务': {
            'category': '消费服务',
            'policy_direction': '复苏支持',
            'key_policies': [
                '文旅消费刺激',
                '职业教育改革',
                '养老服务发展',
                '免税政策优化'
            ],
            'policy_risks': [
                '消费复苏不及预期',
                '人力成本刚性',
                '政策监管变化'
            ]
        },
        # 环保
        '环保': {
            'category': '绿色产业',
            'policy_direction': '减污降碳',
            'key_policies': [
                '污染防治攻坚',
                '碳监测评估',
                '环保装备高质量发展',
                '绿色金融支持'
            ],
            'policy_risks': [
                '地方财政支付压力',
                '行业竞争加剧',
                '技术路线不确定'
            ]
        },
        # 美容护理
        '美容护理': {
            'category': '消费升级',
            'policy_direction': '规范发展',
            'key_policies': [
                '化妆品监管条例',
                '医美行业整顿',
                '国货品牌扶持'
            ],
            'policy_risks': [
                '监管趋严',
                '流量成本上升',
                '国际品牌竞争'
            ]
        },
        # 综合
        '综合': {
            'category': '多元化经营',
            'policy_direction': '聚焦主业',
            'key_policies': [
                '国企改革深化',
                '主业聚焦要求',
                '低效资产处置'
            ],
            'policy_risks': [
                '业务分散风险',
                '管理复杂度',
                '估值折价'
            ]
        }
    }
    
    # 模糊匹配
    for key in policy_map:
        if key in industry or industry in key:
            return policy_map[key]
    
    return {
        'category': '一般行业',
        'policy_direction': '中性',
        'key_policies': ['关注行业专项政策', '产业政策导向'],
        'policy_risks': ['政策变化风险', '监管不确定性']
    }


def get_industry_cycle_info(industry):
    """获取行业周期信息"""
    cycle_map = {
        '半导体': {
            'cycle_type': '技术驱动型周期（3-5年）',
            'cycle_position': '当前处于周期底部回升阶段',
            'cycle_duration': '3-5年',
            'cycle_indicators': [
                '存储芯片价格（DRAM/NAND）',
                '晶圆厂产能利用率',
                '下游消费电子/服务器需求',
                '库存周转天数'
            ],
            'current_phase_features': [
                'AI算力需求拉动高端芯片',
                '消费电子复苏缓慢',
                '存储芯片价格触底回升',
                '国产替代持续推进'
            ]
        },
        '有色金属': {
            'cycle_type': '商品周期（8-10年大周期，2-3年小周期）',
            'cycle_position': '高位震荡期',
            'cycle_duration': '8-10年',
            'cycle_indicators': [
                'LME/LME金属价格',
                '全球PMI指数',
                '中国基建投资增速',
                '新能源金属供需平衡'
            ],
            'current_phase_features': [
                '铜铝价格维持高位',
                '新能源金属供给释放',
                '美联储降息预期支撑',
                '全球制造业复苏缓慢'
            ]
        },
        '小金属': {
            'cycle_type': '供需驱动周期（钴/钼/钨等）',
            'cycle_position': '分化（铜/钴强势，钼/钨调整）',
            'cycle_duration': '3-5年',
            'cycle_indicators': [
                'LME铜价/钴价',
                '钼精矿/钨精矿价格',
                '下游新能源/钢铁需求',
                '刚果(金)/南美矿山供应',
                '中国收储政策'
            ],
            'current_phase_features': [
                '铜：新能源需求强劲，供应偏紧',
                '钴：刚果(金)供应主导，电动车需求增长',
                '钼：钢铁行业需求波动，价格高位震荡',
                '钨：硬质合金需求稳定，供应集中'
            ]
        },
        '煤炭': {
            'cycle_type': '政策主导型周期',
            'cycle_position': '高位震荡',
            'cycle_duration': '无明显周期',
            'cycle_indicators': [
                '港口动力煤价格',
                '电厂库存天数',
                '长协煤签约率',
                '进口煤数量'
            ],
            'current_phase_features': [
                '保供稳价政策常态化',
                '长协煤占比提升',
                '电煤需求季节性波动',
                '新能源替代长期压力'
            ]
        },
        '钢铁': {
            'cycle_type': '地产驱动型周期（3-4年）',
            'cycle_position': '底部震荡',
            'cycle_duration': '3-4年',
            'cycle_indicators': [
                '螺纹钢价格',
                '高炉开工率',
                '钢材社会库存',
                '地产新开工面积'
            ],
            'current_phase_features': [
                '地产需求持续低迷',
                '基建托底效果有限',
                '粗钢产量压减常态化',
                '行业盈利处于低位'
            ]
        },
        '化工': {
            'cycle_type': '成本+需求双驱动周期',
            'cycle_position': '分化（油化工弱，煤化工/新材料强）',
            'cycle_duration': '3-5年',
            'cycle_indicators': [
                '原油价格（布伦特/WTI）',
                '化工品价格指数（CCPI）',
                '下游地产/汽车/农业需求',
                '产能投放节奏'
            ],
            'current_phase_features': [
                '油价中枢下移利好成本',
                '地产链化工品需求弱',
                '新能源化工品（PVDF等）供给释放',
                '新材料国产替代加速'
            ]
        },
        '医药生物': {
            'cycle_type': '创新驱动型（非典型周期）',
            'cycle_position': '政策消化期',
            'cycle_duration': '无固定周期',
            'cycle_indicators': [
                '医保基金收支增速',
                '新药审批数量',
                '集采品种数量',
                '医院诊疗量恢复'
            ],
            'current_phase_features': [
                '集采影响边际减弱',
                '创新药出海加速',
                '医疗反腐常态化',
                '院内诊疗恢复中'
            ]
        },
        '白酒': {
            'cycle_type': '库存周期（3-4年）',
            'cycle_position': '去库存阶段',
            'cycle_duration': '3-4年',
            'cycle_indicators': [
                '批价（茅台/五粮液）',
                '渠道库存天数',
                '动销回款情况',
                '宴席/商务活动恢复'
            ],
            'current_phase_features': [
                '高端酒批价承压',
                '渠道库存去化中',
                '次高端竞争加剧',
                '消费场景逐步恢复'
            ]
        },
        '汽车整车': {
            'cycle_type': '产品周期（3-5年车型周期）',
            'cycle_position': '新能源转型深化期',
            'cycle_duration': '3-5年',
            'cycle_indicators': [
                '乘用车销量增速',
                '新能源车渗透率',
                '库存系数',
                '价格战激烈程度'
            ],
            'current_phase_features': [
                '新能源渗透率超50%',
                '价格战持续激烈',
                '智能化成为新竞争点',
                '出口成为增长引擎'
            ]
        },
        '房地产开发': {
            'cycle_type': '政策+人口长周期（15-20年）',
            'cycle_position': '下行周期中段',
            'cycle_duration': '15-20年',
            'cycle_indicators': [
                '商品房销售面积',
                '新开工面积',
                '土地购置面积',
                '房价环比变化'
            ],
            'current_phase_features': [
                '销售降幅收窄但未转正',
                '新开工持续低迷',
                '政策放松效果有限',
                '房企分化加剧'
            ]
        },
        '农林牧渔': {
            'cycle_type': '猪周期（3-4年）',
            'cycle_position': '周期上行阶段',
            'cycle_duration': '3-4年',
            'cycle_indicators': [
                '能繁母猪存栏量',
                '生猪出栏均重',
                '猪粮比',
                '养殖利润'
            ],
            'current_phase_features': [
                '能繁母猪去化充分',
                '猪价进入上行通道',
                '养殖利润大幅改善',
                '二次育肥增加波动'
            ]
        },
        '电力': {
            'cycle_type': '煤价驱动型周期',
            'cycle_position': '盈利改善期',
            'cycle_duration': '2-3年',
            'cycle_indicators': [
                '秦皇岛动力煤价格',
                '火电利用小时数',
                '市场化交易电价',
                '容量电价执行情况'
            ],
            'current_phase_features': [
                '煤价中枢下移利好火电',
                '容量电价机制落地',
                '新能源装机快速增长',
                '绿电交易规模扩大'
            ]
        },
        '航运港口': {
            'cycle_type': '全球贸易周期',
            'cycle_position': '运价回归常态',
            'cycle_duration': '5-8年',
            'cycle_indicators': [
                'BDI/SCFI/CCFI指数',
                '集装箱船订单量',
                '美西港口拥堵情况',
                '全球贸易量增速'
            ],
            'current_phase_features': [
                '集运运价回归常态',
                '油运景气度较高',
                '干散货运价低迷',
                '红海危机推升运价'
            ]
        },
        '国防军工': {
            'cycle_type': '五年规划采购周期',
            'cycle_position': '十四五后半程',
            'cycle_duration': '5年',
            'cycle_indicators': [
                '国防预算增速',
                '军品采购订单',
                '型号研制进度',
                '军贸出口情况'
            ],
            'current_phase_features': [
                '十四五订单集中释放',
                '新型号批产加速',
                '军贸出口突破',
                '产业链业绩兑现'
            ]
        },
        '计算机': {
            'cycle_type': '财政支出+技术迭代周期',
            'cycle_position': 'AI应用落地期',
            'cycle_duration': '3-5年',
            'cycle_indicators': [
                '政府IT支出预算',
                '信创招标进度',
                'AI算力投资',
                '数据要素政策'
            ],
            'current_phase_features': [
                'AI大模型应用落地',
                '信创招标逐步恢复',
                '数据要素市场化提速',
                '算力基础设施建设'
            ]
        },
        '通信设备': {
            'cycle_type': '运营商资本开支周期',
            'cycle_position': '5G后周期',
            'cycle_duration': '5-7年',
            'cycle_indicators': [
                '三大运营商资本开支',
                '5G基站建设进度',
                '5G用户数',
                '算力网络投资'
            ],
            'current_phase_features': [
                '5G建设进入后周期',
                '算力网络投资增加',
                '海外5G建设放缓',
                '6G技术研发启动'
            ]
        },
        '机械设备': {
            'cycle_type': '投资驱动周期',
            'cycle_position': '结构性分化',
            'cycle_duration': '3-5年',
            'cycle_indicators': [
                '制造业固定资产投资',
                '挖掘机销量',
                '出口订单情况',
                '设备更新政策'
            ],
            'current_phase_features': [
                '传统机械需求平淡',
                '人形机器人等新赛道爆发',
                '设备更新政策刺激',
                '出口保持韧性'
            ]
        },
        '传媒': {
            'cycle_type': '内容供给周期',
            'cycle_position': 'AI赋能期',
            'cycle_duration': '2-3年',
            'cycle_indicators': [
                '游戏版号发放数量',
                '电影票房恢复',
                '广告市场增速',
                'AI应用落地'
            ],
            'current_phase_features': [
                '版号发放常态化',
                '短剧/微剧爆发',
                'AI生成内容兴起',
                '广告市场弱复苏'
            ]
        },
        '银行': {
            'cycle_type': '信贷周期',
            'cycle_position': '息差承压期',
            'cycle_duration': '3-5年',
            'cycle_indicators': [
                '净息差（NIM）',
                '不良率/关注类贷款',
                '信贷增速',
                '中间业务收入'
            ],
            'current_phase_features': [
                '净息差持续收窄',
                '资产质量压力可控',
                '信贷需求偏弱',
                '财富管理转型'
            ]
        },
        '证券': {
            'cycle_type': '市场活跃度周期',
            'cycle_position': '底部区域',
            'cycle_duration': '3-5年',
            'cycle_indicators': [
                'A股成交额',
                'IPO/再融资规模',
                '两融余额',
                '基金发行规模'
            ],
            'current_phase_features': [
                '市场成交低迷',
                'IPO节奏放缓',
                '财富管理转型阵痛',
                '并购重组活跃'
            ]
        },
        '电气设备': {
            'cycle_type': '政策驱动周期',
            'cycle_position': '增速放缓期',
            'cycle_duration': '无明显周期',
            'cycle_indicators': [
                '光伏装机量',
                '风电装机量',
                '储能装机量',
                '电网投资增速'
            ],
            'current_phase_features': [
                '光伏产能过剩价格下行',
                '风电装机稳步增长',
                '储能装机爆发',
                '电网投资加速'
            ]
        }
    }
    
    # 模糊匹配
    for key in cycle_map:
        if key in industry or industry in key:
            return cycle_map[key]
    
    return {
        'cycle_type': '一般周期',
        'cycle_position': '需结合宏观判断',
        'cycle_duration': '不确定',
        'cycle_indicators': ['行业景气指数', '下游需求变化', '产能利用率'],
        'current_phase_features': ['关注行业数据变化', '跟踪龙头企业动向']
    }


def get_industry_global_factors(industry):
    """获取行业国际形势因素"""
    global_map = {
        '半导体': {
            'export_dependency': '低（进口依赖高）',
            'import_dependency': '极高（设备/材料/EDA）',
            'tariff_sensitivity': '极高',
            'key_export_markets': ['东南亚', '欧洲'],
            'key_import_sources': ['美国（设备/EDA）', '日本（材料/设备）', '荷兰（光刻机）', '韩国（存储）'],
            'geopolitical_risks': [
                '美国芯片法案对华限制',
                '先进制程设备禁运',
                'EDA软件断供风险',
                '人才流动限制'
            ],
            'global_supply_chain': '上游（设备/材料/EDA）被美日荷垄断，中游制造分散，下游设计全球化'
        },
        '有色金属': {
            'export_dependency': '中（铝材/加工品）',
            'import_dependency': '高（铜矿/铝土矿/锂矿）',
            'tariff_sensitivity': '中',
            'key_export_markets': ['东南亚', '欧洲', '美国'],
            'key_import_sources': ['智利/秘鲁（铜）', '澳大利亚（锂/铝土矿）', '印尼（镍）', '刚果（钴）'],
            'geopolitical_risks': [
                '资源国政策变化（资源民族主义）',
                '中美关税影响',
                '物流成本波动（红海危机）',
                'ESG约束（海外矿山）'
            ],
            'global_supply_chain': '上游资源分布不均，中游冶炼加工集中在中国，下游应用全球分散'
        },
        '小金属': {
            'export_dependency': '高（钴/钼/钨等）',
            'import_dependency': '极高（铜/钴矿依赖海外）',
            'tariff_sensitivity': '中',
            'key_export_markets': ['欧洲', '美国', '日本', '韩国'],
            'key_import_sources': [
                '刚果(金)（钴/铜）',
                '智利/秘鲁（铜）',
                '澳大利亚（铜/钴）',
                '南美（铜）'
            ],
            'geopolitical_risks': [
                '刚果(金)政局不稳（钴/铜主要来源）',
                '资源民族主义抬头（加税/国有化）',
                'ESG要求提高（童工/环境）',
                '中美在非洲资源竞争',
                '南美左翼政府政策变化',
                '红海危机影响物流成本'
            ],
            'global_supply_chain': '上游矿山资源集中在刚果(金)/南美，中游冶炼加工在中国，下游应用全球（新能源/钢铁/电子）'
        },
        '煤炭': {
            'export_dependency': '低',
            'import_dependency': '中（炼焦煤/动力煤补充）',
            'tariff_sensitivity': '低',
            'key_export_markets': ['东南亚', '日本', '韩国'],
            'key_import_sources': ['澳大利亚', '印尼', '蒙古', '俄罗斯'],
            'geopolitical_risks': [
                '中澳关系影响澳煤进口',
                '俄乌冲突影响俄煤供应',
                '蒙古通关效率',
                '国际煤价波动传导'
            ],
            'global_supply_chain': '中国煤炭自给率高，进口作为补充，主要受国内政策主导'
        },
        '石油石化': {
            'export_dependency': '低',
            'import_dependency': '极高（原油对外依存度超70%）',
            'tariff_sensitivity': '中',
            'key_export_markets': ['东南亚'],
            'key_import_sources': ['中东（沙特/伊拉克/阿联酋）', '俄罗斯', '非洲', '南美'],
            'geopolitical_risks': [
                '中东局势（红海/霍尔木兹）',
                '俄乌冲突影响俄油供应',
                'OPEC+减产政策',
                '美国制裁伊朗/委内瑞拉'
            ],
            'global_supply_chain': '上游原油高度依赖进口，中游炼化集中，下游化工品出口'
        },
        '钢铁': {
            'export_dependency': '中（钢材出口）',
            'import_dependency': '极高（铁矿石对外依存度超80%）',
            'tariff_sensitivity': '高（反倾销）',
            'key_export_markets': ['东南亚', '中东', '非洲'],
            'key_import_sources': ['澳大利亚（必和必拓/力拓）', '巴西（淡水河谷）'],
            'geopolitical_risks': [
                '中澳关系影响铁矿石供应',
                '海外反倾销调查',
                '碳边境税（CBAM）',
                '海运费波动'
            ],
            'global_supply_chain': '上游铁矿石被澳巴垄断，中游钢铁产能集中在中国，下游应用全球'
        },
        '化工': {
            'export_dependency': '高（化工品出口大国）',
            'import_dependency': '高（高端化学品/原油）',
            'tariff_sensitivity': '中',
            'key_export_markets': ['东南亚', '印度', '欧洲', '美国'],
            'key_import_sources': ['中东（原油）', '韩国/日本（高端化学品）', '欧洲（特种化学品）'],
            'geopolitical_risks': [
                '原油价格波动',
                '中美关税影响',
                '欧洲能源成本（天然气）',
                '红海危机影响物流'
            ],
            'global_supply_chain': '上游原油依赖进口，中游大宗化工品产能集中在中国，下游精细化工欧美领先'
        },
        '医药生物': {
            'export_dependency': '中（原料药/器械）',
            'import_dependency': '高（创新药/高端器械）',
            'tariff_sensitivity': '中',
            'key_export_markets': ['美国', '欧洲', '印度', '日本'],
            'key_import_sources': ['美国（创新药）', '欧洲（高端器械）', '印度（原料药）'],
            'geopolitical_risks': [
                '美国生物安全法案（药明系）',
                '创新药出海FDA审查',
                '原料药供应链安全',
                '医保谈判国际化'
            ],
            'global_supply_chain': '上游研发欧美领先，中游制造向中国转移，下游市场全球化'
        },
        '医疗器械': {
            'export_dependency': '中（低值耗材）',
            'import_dependency': '高（高端设备）',
            'tariff_sensitivity': '中',
            'key_export_markets': ['欧洲', '美国', '东南亚'],
            'key_import_sources': ['美国（GPS影像设备）', '德国（手术机器人）', '日本（内窥镜）'],
            'geopolitical_risks': [
                '高端设备进口限制',
                '集采后外企降价压力',
                '国产替代加速',
                '出海认证壁垒'
            ],
            'global_supply_chain': '上游核心部件进口，中游组装制造在中国，下游市场全球'
        },
        '汽车整车': {
            'export_dependency': '快速提升（已成全球最大出口国）',
            'import_dependency': '低',
            'tariff_sensitivity': '高',
            'key_export_markets': ['俄罗斯', '中东', '东南亚', '欧洲', '南美'],
            'key_import_sources': ['德国（豪华车）', '日本（零部件）'],
            'geopolitical_risks': [
                '欧盟反补贴调查（电动车）',
                '美国关税壁垒（100%）',
                '俄罗斯市场依赖度',
                '出海认证标准'
            ],
            'global_supply_chain': '中国已成全球最大汽车出口国，但面临贸易壁垒升级'
        },
        '汽车零部件': {
            'export_dependency': '高',
            'import_dependency': '中（芯片/高端材料）',
            'tariff_sensitivity': '中',
            'key_export_markets': ['欧洲', '美国', '墨西哥'],
            'key_import_sources': ['德国（高端零部件）', '日本（精密零部件）', '韩国（电池材料）'],
            'geopolitical_risks': [
                '跟随整车厂出海布局',
                '墨西哥近岸外包机会',
                '芯片供应安全',
                '原材料价格波动'
            ],
            'global_supply_chain': '跟随中国整车厂出海，在墨西哥/东南亚建厂规避关税'
        },
        '纺织服装': {
            'export_dependency': '极高（全球纺织出口第一）',
            'import_dependency': '中（棉花/高端面料）',
            'tariff_sensitivity': '高',
            'key_export_markets': ['美国', '欧洲', '日本', '东南亚'],
            'key_import_sources': ['美国（棉花）', '澳大利亚（羊毛）', '东南亚（成衣回流）'],
            'geopolitical_risks': [
                '订单向东南亚转移',
                '新疆棉禁令影响',
                '中美关税',
                'RCEP关税优惠利用'
            ],
            'global_supply_chain': '中低端产能向东南亚转移，中国保留高附加值环节（面料/品牌）'
        },
        '轻工制造': {
            'export_dependency': '极高（家具/玩具/文具出口大国）',
            'import_dependency': '低',
            'tariff_sensitivity': '高',
            'key_export_markets': ['美国', '欧洲', '日本'],
            'key_import_sources': ['东南亚（木材）', '俄罗斯（木材）'],
            'geopolitical_risks': [
                '美国关税/反倾销',
                '订单转移东南亚',
                '海运费波动',
                '汇率波动'
            ],
            'global_supply_chain': '中国制造优势仍在，但面临产业转移压力，跨境电商成新渠道'
        },
        '电子元器件': {
            'export_dependency': '高（被动元件出口）',
            'import_dependency': '高（高端MLCC/芯片）',
            'tariff_sensitivity': '中',
            'key_export_markets': ['东南亚', '台湾', '韩国', '欧洲'],
            'key_import_sources': ['日本（高端MLCC）', '韩国（存储）', '台湾（晶圆代工）'],
            'geopolitical_risks': [
                '台海局势风险',
                '日韩材料供应',
                '中美科技脱钩',
                '产业链转移压力'
            ],
            'global_supply_chain': '上游材料日韩垄断，中游制造向中国转移，下游应用全球'
        },
        '通信设备': {
            'export_dependency': '中（华为/中兴海外业务受限）',
            'import_dependency': '中（高端芯片）',
            'tariff_sensitivity': '高',
            'key_export_markets': ['中东', '非洲', '东南亚', '拉美'],
            'key_import_sources': ['美国（高端芯片）', '欧洲（光器件）'],
            'geopolitical_risks': [
                '华为/中兴海外受限',
                '5G设备安全审查',
                '芯片供应限制',
                '发展中国家债务风险'
            ],
            'global_supply_chain': '海外5G建设放缓，国内市场为主，芯片国产替代加速'
        },
        '计算机': {
            'export_dependency': '低',
            'import_dependency': '高（芯片/操作系统/数据库）',
            'tariff_sensitivity': '中',
            'key_export_markets': ['一带一路国家'],
            'key_import_sources': ['美国（芯片/操作系统/数据库/中间件）', '欧洲（工业软件）'],
            'geopolitical_risks': [
                '美国技术封锁（芯片/软件）',
                '信创国产替代加速',
                '开源软件供应链安全',
                '数据跨境流动限制'
            ],
            'global_supply_chain': '上游软硬件高度依赖美国，国产替代是长期主线'
        },
        '互联网': {
            'export_dependency': '低（主要国内市场）',
            'import_dependency': '低',
            'tariff_sensitivity': '低',
            'key_export_markets': ['东南亚', '中东', '拉美'],
            'key_import_sources': ['美国（云计算技术）', '开源社区'],
            'geopolitical_risks': [
                '数据安全审查',
                '出海面临本土竞争',
                'AI算力芯片限制',
                '内容监管差异'
            ],
            'global_supply_chain': '主要服务国内市场，出海以电商/游戏/短视频为主'
        },
        '国防军工': {
            'export_dependency': '低（军贸有限）',
            'import_dependency': '中（高端材料/发动机）',
            'tariff_sensitivity': '低',
            'key_export_markets': ['巴基斯坦', '中东', '非洲', '东南亚'],
            'key_import_sources': ['俄罗斯（发动机/材料）', '乌克兰（历史合作）'],
            'geopolitical_risks': [
                '台海局势',
                '俄乌冲突影响俄装备供应',
                '军贸政治敏感性',
                '技术封锁（军用技术）'
            ],
            'global_supply_chain': '自主可控是主线，军贸出口突破中'
        },
        '航运港口': {
            'export_dependency': '服务出口',
            'import_dependency': '服务进口',
            'tariff_sensitivity': '低',
            'key_export_markets': ['全球航线'],
            'key_import_sources': ['全球航线'],
            'geopolitical_risks': [
                '红海危机（胡塞武装）',
                '巴拿马运河干旱',
                '俄乌冲突影响黑海航运',
                '中美贸易量变化'
            ],
            'global_supply_chain': '全球化程度最高，受地缘政治和贸易量双重影响'
        },
        '农林牧渔': {
            'export_dependency': '中（水产/蔬菜）',
            'import_dependency': '高（大豆/玉米/肉类）',
            'tariff_sensitivity': '中',
            'key_export_markets': ['东南亚', '日本', '韩国'],
            'key_import_sources': ['美国（大豆/玉米）', '巴西（大豆）', '澳大利亚（牛肉）', '欧盟（猪肉）'],
            'geopolitical_risks': [
                '中美贸易摩擦（农产品）',
                '粮食安全问题',
                '非洲猪瘟等疫病跨境传播',
                '极端天气影响全球产量'
            ],
            'global_supply_chain': '口粮基本自给，饲料粮高度依赖进口，肉类进口补充'
        },
        '银行': {
            'export_dependency': '低',
            'import_dependency': '低',
            'tariff_sensitivity': '低',
            'key_export_markets': ['一带一路项目'],
            'key_import_sources': ['SWIFT系统', '国际评级'],
            'geopolitical_risks': [
                '中美金融脱钩风险',
                'SWIFT制裁风险',
                '海外资产安全',
                '国际评级下调'
            ],
            'global_supply_chain': '主要服务国内，国际化程度有限，但面临金融安全挑战'
        },
        '证券': {
            'export_dependency': '低',
            'import_dependency': '低',
            'tariff_sensitivity': '低',
            'key_export_markets': ['港股通', 'QDII'],
            'key_import_sources': ['国际投行竞争', '外资机构'],
            'geopolitical_risks': [
                '中概股审计监管',
                '外资流入波动',
                '国际投行竞争',
                '跨境监管合作'
            ],
            'global_supply_chain': '资本市场开放深化，外资机构参与度提升'
        },
        '电力': {
            'export_dependency': '极低',
            'import_dependency': '极低',
            'tariff_sensitivity': '极低',
            'key_export_markets': ['东南亚（电力出口有限）'],
            'key_import_sources': ['澳大利亚（动力煤）', '印尼（动力煤）', '蒙古（焦煤）'],
            'geopolitical_risks': [
                '煤炭进口安全',
                '极端天气（进口依赖地区）',
                '跨境电网合作'
            ],
            'global_supply_chain': '电力难以储存和远距离传输，基本自给自足'
        },
        '电气设备': {
            'export_dependency': '高（光伏/风电/储能设备出口大国）',
            'import_dependency': '中（部分材料/IGBT）',
            'tariff_sensitivity': '高',
            'key_export_markets': ['欧洲', '东南亚', '中东', '拉美'],
            'key_import_sources': ['德国（IGBT）', '日本（材料）', '韩国（电池材料）'],
            'geopolitical_risks': [
                '欧盟反补贴调查（光伏/电动车）',
                '美国关税壁垒',
                '关键材料供应（多晶硅/锂）',
                '海外建厂本地化要求'
            ],
            'global_supply_chain': '中国新能源设备全球领先，但面临贸易壁垒升级'
        },
        '食品饮料': {
            'export_dependency': '低（白酒/调味品少量出口）',
            'import_dependency': '低',
            'tariff_sensitivity': '低',
            'key_export_markets': ['东南亚华人市场', '欧美华人市场'],
            'key_import_sources': ['澳大利亚（大麦）', '新西兰（奶粉）', '欧洲（高端酒）'],
            'geopolitical_risks': [
                '大麦等原料进口',
                '食品安全国际标准',
                '品牌出海文化差异',
                '汇率波动'
            ],
            'global_supply_chain': '主要服务国内市场，进口依赖低'
        }
    }
    
    # 模糊匹配
    for key in global_map:
        if key in industry or industry in key:
            return global_map[key]
    
    return {
        'export_dependency': '待评估',
        'import_dependency': '待评估',
        'tariff_sensitivity': '待评估',
        'key_export_markets': [],
        'key_import_sources': [],
        'geopolitical_risks': ['需关注国际贸易形势', '关注汇率波动'],
        'global_supply_chain': '需具体分析产业链位置'
    }


def get_industry_chain_info(industry):
    """获取产业链信息"""
    chain_map = {
        '半导体': {
            'position': '设计/制造/封测（全产业链布局）',
            'upstream_power': '极高（设备/材料/EDA被垄断）',
            'downstream_power': '中（消费电子/汽车/服务器）',
            'upstream': ['EDA软件', '半导体设备', '硅片/光刻胶/特气'],
            'downstream': ['消费电子', '计算机', '通信设备', '汽车电子', '工业控制'],
            'value_distribution': '上游EDA/设备/材料利润最高（50%+毛利率），中游制造次之（30%+），封测较低（15-20%）'
        },
        '电子元器件': {
            'position': '中游',
            'upstream_power': '高（材料/设备）',
            'downstream_power': '中',
            'upstream': ['金属材料', '化工材料', '陶瓷材料', '制造设备'],
            'downstream': ['消费电子', '通信设备', '汽车电子', '工业设备'],
            'value_distribution': '被动元件毛利率20-40%，连接器15-30%，高端产品利润更高'
        },
        '通信设备': {
            'position': '中游',
            'upstream_power': '高（芯片/光器件）',
            'downstream_power': '低（运营商集中）',
            'upstream': ['通信芯片', '光器件/光模块', 'PCB', '结构件'],
            'downstream': ['电信运营商', '企业网', '政府', '数据中心'],
            'value_distribution': '运营商资本开支决定需求，上游芯片/光器件利润较高'
        },
        '计算机': {
            'position': '下游应用+中游软件',
            'upstream_power': '高（芯片/OS/数据库）',
            'downstream_power': '低（客户分散）',
            'upstream': ['芯片（CPU/GPU）', '操作系统', '数据库', '中间件', '服务器'],
            'downstream': ['政府', '金融', '电信', '企业', '个人'],
            'value_distribution': '软件/服务毛利率高（60%+），硬件集成较低（10-20%）'
        },
        '互联网': {
            'position': '下游平台',
            'upstream_power': '中（云服务商）',
            'downstream_power': '高（用户/广告主）',
            'upstream': ['云计算服务', '带宽', '内容创作者', '支付通道'],
            'downstream': ['C端用户', 'B端广告主', '商家'],
            'value_distribution': '平台抽成/广告毛利率极高（70%+），但获客成本高'
        },
        '医药生物': {
            'position': '下游',
            'upstream_power': '中（原料药/设备）',
            'downstream_power': '低（医院/患者）',
            'upstream': ['原料药', '医药中间体', '制药设备', '包装材料'],
            'downstream': ['医院', '药店', '患者'],
            'value_distribution': '创新药毛利率80%+，仿制药30-50%，原料药更低'
        },
        '医疗器械': {
            'position': '中游',
            'upstream_power': '高（核心部件/材料）',
            'downstream_power': '低（医院集中）',
            'upstream': ['核心零部件', '医用材料', '电子元器件'],
            'downstream': ['医院', '体检机构', '家庭用户'],
            'value_distribution': '高端设备毛利率60%+，低值耗材20-40%'
        },
        '汽车整车': {
            'position': '下游集成',
            'upstream_power': '中（零部件分散）',
            'downstream_power': '中（消费者/经销商）',
            'upstream': ['动力电池', '电机电控', '车身底盘', '电子电气', '内外饰'],
            'downstream': ['个人消费者', '网约车/出租车', '企业客户'],
            'value_distribution': '整车毛利率10-20%，新能源车企亏损或微利'
        },
        '汽车零部件': {
            'position': '中游',
            'upstream_power': '中（原材料/芯片）',
            'downstream_power': '低（整车厂集中）',
            'upstream': ['钢材/铝材', '芯片', '橡胶/塑料', '电子元器件'],
            'downstream': ['整车厂', '售后市场'],
            'value_distribution': '传统零部件毛利率15-25%，智能化部件30%+'
        },
        '电气设备': {
            'position': '中游',
            'upstream_power': '中（硅料/锂/稀土）',
            'downstream_power': '低（运营商/电网集中）',
            'upstream': ['硅料/硅片', '锂/钴/镍', '稀土', 'IGBT/逆变器'],
            'downstream': ['光伏电站', '风电场', '电网', '工商业/户用'],
            'value_distribution': '上游资源利润高（硅料/锂），中游制造利润薄，下游运营稳定'
        },
        '电力': {
            'position': '下游运营',
            'upstream_power': '中（煤炭/设备）',
            'downstream_power': '低（用户分散）',
            'upstream': ['煤炭/天然气', '发电设备', '新能源设备'],
            'downstream': ['工商业用户', '居民用户', '其他电网'],
            'value_distribution': '火电微利，水电/核电稳定，新能源受电价影响'
        },
        '有色金属': {
            'position': '上游资源',
            'upstream_power': 'N/A',
            'downstream_power': '中（加工/应用）',
            'upstream': ['矿山开采'],
            'downstream': ['电力', '建筑', '汽车', '电子', '家电'],
            'value_distribution': '资源端利润随周期波动大，加工端利润稳定但低'
        },
        '煤炭': {
            'position': '上游资源',
            'upstream_power': 'N/A',
            'downstream_power': '高（电力/钢铁集中）',
            'upstream': ['矿山设备', '运输'],
            'downstream': ['电力', '钢铁', '化工', '建材'],
            'value_distribution': '资源端利润高，但受政策调控'
        },
        '钢铁': {
            'position': '中游',
            'upstream_power': '极高（铁矿石垄断）',
            'downstream_power': '低（地产/基建/汽车集中）',
            'upstream': ['铁矿石', '焦炭', '废钢'],
            'downstream': ['房地产', '基建', '汽车', '机械', '家电'],
            'value_distribution': '上游铁矿石利润高，中游钢铁利润薄且波动'
        },
        '化工': {
            'position': '中游',
            'upstream_power': '高（原油/煤炭）',
            'downstream_power': '中（应用分散）',
            'upstream': ['原油', '煤炭', '天然气', '原盐'],
            'downstream': ['农业', '建筑', '汽车', '电子', '纺织', '医药'],
            'value_distribution': '大宗化工品利润薄，精细化工/新材料利润高'
        },
        '建筑材料': {
            'position': '中游',
            'upstream_power': '中（水泥/玻璃原材料）',
            'downstream_power': '低（地产/基建集中）',
            'upstream': ['石灰石', '黏土', '石英砂', '能源'],
            'downstream': ['房地产', '基建', '装修'],
            'value_distribution': '水泥/玻璃区域性明显，运输半径限制，利润受供需影响'
        },
        '房地产开发': {
            'position': '下游',
            'upstream_power': '中（土地/建材/资金）',
            'downstream_power': '高（消费者）',
            'upstream': ['土地', '建筑服务', '建材', '资金'],
            'downstream': ['购房者', '商业租户'],
            'value_distribution': '土地成本占比高，毛利率 historically 20-30%，目前压缩'
        },
        '食品饮料': {
            'position': '下游',
            'upstream_power': '中（农产品）',
            'downstream_power': '高（消费者/渠道）',
            'upstream': ['农产品', '包装材料', '食品添加剂'],
            'downstream': ['商超', '餐饮', '电商', '消费者'],
            'value_distribution': '品牌消费品毛利率高（白酒70%+，调味品40%+）'
        },
        '白酒': {
            'position': '下游',
            'upstream_power': '低（粮食/包装）',
            'downstream_power': '高（经销商/消费者）',
            'upstream': ['粮食（高粱/小麦）', '包装材料'],
            'downstream': ['经销商', '团购', '零售', '消费者'],
            'value_distribution': '高端白酒毛利率80%+，净利率30%+，产业链利润核心'
        },
        '纺织服装': {
            'position': '中游',
            'upstream_power': '中（棉花/化纤）',
            'downstream_power': '低（品牌方集中）',
            'upstream': ['棉花', '化纤', '染料', '面料'],
            'downstream': ['服装品牌', '零售商', '消费者'],
            'value_distribution': '制造端利润薄（5-10%），品牌端利润高（30%+）'
        },
        '轻工制造': {
            'position': '中游',
            'upstream_power': '中（木材/塑料/金属）',
            'downstream_power': '中（零售商/消费者）',
            'upstream': ['木材', '塑料', '金属', '纸张'],
            'downstream': ['零售商', '电商平台', '消费者'],
            'value_distribution': '代工利润薄，自有品牌利润高'
        },
        '农林牧渔': {
            'position': '上游',
            'upstream_power': 'N/A',
            'downstream_power': '低（加工企业集中）',
            'upstream': ['种子/种苗', '饲料', '农药/兽药'],
            'downstream': ['食品加工', '餐饮', '零售'],
            'value_distribution': '养殖端利润波动大（猪周期），种植端利润稳定但低'
        },
        '小金属': {
            'position': '上游资源+中游冶炼',
            'upstream_power': 'N/A',
            'downstream_power': '中（应用分散）',
            'upstream': ['矿山开采', '采矿设备', '能源'],
            'downstream': ['新能源汽车（钴/铜）', '钢铁（钼）', '硬质合金（钨）', '电子/化工'],
            'value_distribution': '上游矿山资源利润高（掌握资源的企业），中游冶炼加工利润中等，下游应用利润分散'
        },
        '银行': {
            'position': '金融服务',
            'upstream_power': 'N/A',
            'downstream_power': 'N/A',
            'upstream': ['存款', '同业负债', '央行资金'],
            'downstream': ['企业贷款', '个人贷款', '政府项目'],
            'value_distribution': '息差收入为主（净息差1.5-2.5%），中间业务占比提升'
        },
        '证券': {
            'position': '金融服务',
            'upstream_power': 'N/A',
            'downstream_power': 'N/A',
            'upstream': ['资本金', '融资渠道'],
            'downstream': ['投资者', '融资企业'],
            'value_distribution': '经纪/投行/资管/自营多元，市场波动影响大'
        },
        '保险': {
            'position': '金融服务',
            'upstream_power': 'N/A',
            'downstream_power': 'N/A',
            'upstream': ['保费收入', '投资收益'],
            'downstream': ['投保人', '被保险人'],
            'value_distribution': '寿险长期业务，财险短期，投资端影响盈利'
        },
        '国防军工': {
            'position': '中游',
            'upstream_power': '高（高端材料/电子）',
            'downstream_power': '极低（军方唯一客户）',
            'upstream': ['高端合金', '复合材料', '电子元器件', '发动机'],
            'downstream': ['军队', '军贸客户'],
            'value_distribution': '成本加成定价，利润稳定但受定价机制约束'
        },
        '传媒': {
            'position': '下游',
            'upstream_power': '中（IP/内容/技术）',
            'downstream_power': '高（用户/广告主）',
            'upstream': ['IP版权', '内容制作', '技术平台'],
            'downstream': ['用户', '广告主', '平台'],
            'value_distribution': '平台抽成高，内容方分成，广告收入为主'
        },
        '交通运输': {
            'position': '服务',
            'upstream_power': '中（燃油/人工/设备）',
            'downstream_power': '中（货主/乘客）',
            'upstream': ['燃油', '人工', '车辆/船舶/飞机', '基础设施'],
            'downstream': ['货主', '乘客', '电商'],
            'value_distribution': '重资产低毛利，规模效应明显'
        },
        '航运港口': {
            'position': '基础设施',
            'upstream_power': '中（设备/人工）',
            'downstream_power': '中（船公司/货主）',
            'upstream': ['港口设备', '人工', '土地'],
            'downstream': ['航运公司', '货主', '贸易公司'],
            'value_distribution': '港口稳定，航运周期性极强'
        },
        '机械设备': {
            'position': '中游',
            'upstream_power': '中（钢材/零部件）',
            'downstream_power': '低（客户集中）',
            'upstream': ['钢材', '铸件', '液压件', '控制系统'],
            'downstream': ['基建', '地产', '制造业', '矿山'],
            'value_distribution': '通用机械利润薄，专用/高端机械利润高'
        },
        '环保': {
            'position': '服务',
            'upstream_power': '低（设备/材料）',
            'downstream_power': '低（政府/企业客户）',
            'upstream': ['环保设备', '药剂', '工程服务'],
            'downstream': ['政府', '工业企业', '市政'],
            'value_distribution': '工程业务利润薄，运营业务稳定，受财政支付影响'
        },
        '社会服务': {
            'position': '服务',
            'upstream_power': '中（人工/租金）',
            'downstream_power': '高（消费者）',
            'upstream': ['人工', '租金', '原材料'],
            'downstream': ['消费者', '企业客户'],
            'value_distribution': '轻资产服务利润高，重资产（酒店/景区）利润波动'
        },
        '美容护理': {
            'position': '下游',
            'upstream_power': '中（原料/代工）',
            'downstream_power': '高（消费者）',
            'upstream': ['化妆品原料', '包装材料', '代工生产'],
            'downstream': ['消费者', '美妆集合店', '电商'],
            'value_distribution': '品牌端利润极高（毛利率70%+），代工端利润薄'
        }
    }
    
    # 模糊匹配
    for key in chain_map:
        if key in industry or industry in key:
            return chain_map[key]
    
    return {
        'position': '需具体分析',
        'upstream_power': '待评估',
        'downstream_power': '待评估',
        'upstream': [],
        'downstream': [],
        'value_distribution': '需具体分析产业链利润分配'
    }


def get_industry_competition_info(industry):
    """获取行业竞争格局信息"""
    competition_map = {
        '半导体': {
            'concentration': '分散（设计端）/集中（制造端）',
            'entry_barrier': '极高（资金/技术/人才）',
            'homogeneity': '低（差异化大）',
            'key_players': [
                '设计：华为海思、紫光展锐、韦尔股份等',
                '制造：中芯国际、华虹半导体',
                '封测：长电科技、通富微电',
                '设备：北方华创、中微公司',
                '材料：沪硅产业、安集科技'
            ],
            'competition_trends': [
                '国产替代加速，本土企业份额提升',
                '先进制程受限，成熟制程内卷',
                'AI芯片成为新战场',
                '设备材料自主化攻坚'
            ]
        },
        '电子元器件': {
            'concentration': '中（MLCC等被动元件集中）',
            'entry_barrier': '中高（技术积累）',
            'homogeneity': '中（标准化产品）',
            'key_players': [
                'MLCC：村田/三星/国巨/风华高科',
                '连接器：泰科/安费诺/立讯精密',
                '电感：TDK/村田/顺络电子'
            ],
            'competition_trends': [
                '国产替代从低端向高端渗透',
                '汽车电子需求拉动',
                '日韩台厂商仍占高端',
                '价格战激烈'
            ]
        },
        '通信设备': {
            'concentration': '高度集中（华为/中兴双寡头）',
            'entry_barrier': '极高（技术/资金/资质）',
            'homogeneity': '中（标准化+定制化）',
            'key_players': [
                '主设备：华为、中兴、烽火通信',
                '光模块：中际旭创、光迅科技、新易盛',
                '光纤：长飞光纤、亨通光电'
            ],
            'competition_trends': [
                '华为/中兴国内主导，海外受限',
                '光模块向800G/1.6T升级',
                '算力网络带来新需求',
                '海外爱立信/诺基亚竞争'
            ]
        },
        '计算机': {
            'concentration': '分散（细分领域龙头）',
            'entry_barrier': '中（技术/渠道/资质）',
            'homogeneity': '低（差异化大）',
            'key_players': [
                '信创：中国软件、金山办公、太极股份',
                '网络安全：奇安信、深信服、启明星辰',
                'AI：科大讯飞、商汤、海康威视',
                '金融IT：恒生电子、同花顺'
            ],
            'competition_trends': [
                '信创从党政向行业渗透',
                'AI应用落地加速',
                '云化转型深化',
                '行业集中度提升'
            ]
        },
        '互联网': {
            'concentration': '高度集中（平台垄断）',
            'entry_barrier': '极高（网络效应/资金）',
            'homogeneity': '高（同质化竞争）',
            'key_players': [
                '综合：腾讯、阿里、字节、百度',
                '电商：阿里、京东、拼多多',
                '本地生活：美团',
                '短视频：抖音、快手'
            ],
            'competition_trends': [
                '流量红利见顶，存量竞争',
                '出海成为新增长点',
                'AI赋能业务',
                '监管常态化'
            ]
        },
        '医药生物': {
            'concentration': '分散（细分领域龙头）',
            'entry_barrier': '高（研发/注册/渠道）',
            'homogeneity': '低（差异化大）',
            'key_players': [
                '创新药：恒瑞、百济神州、信达生物',
                'CXO：药明康德、康龙化成',
                '器械：迈瑞医疗、联影医疗',
                '中药：片仔癀、云南白药'
            ],
            'competition_trends': [
                '创新药内卷，同质化严重',
                '出海成为必选项',
                '集采倒逼转型创新',
                'CXO受地缘政治影响'
            ]
        },
        '医疗器械': {
            'concentration': '中（细分领域集中）',
            'entry_barrier': '高（技术/注册/渠道）',
            'homogeneity': '中',
            'key_players': [
                '影像：联影医疗、迈瑞医疗、GE/西门子/飞利浦',
                'IVD：迈瑞、安图、新产业',
                '心血管：微创医疗、乐普医疗',
                '骨科：威高股份、春立医疗'
            ],
            'competition_trends': [
                '国产替代加速',
                '集采扩围至器械',
                '高端设备突破中',
                '出海初期'
            ]
        },
        '汽车整车': {
            'concentration': '从分散走向集中',
            'entry_barrier': '极高（资金/技术/品牌）',
            'homogeneity': '中',
            'key_players': [
                '新能源：比亚迪、特斯拉、理想、蔚来、小鹏',
                '传统：大众、丰田、吉利、长安、长城',
                '新势力：小米、华为系（问界等）'
            ],
            'competition_trends': [
                '价格战持续，淘汰赛加速',
                '智能化成为差异化核心',
                '出口成为增长引擎',
                '传统车企转型阵痛'
            ]
        },
        '汽车零部件': {
            'concentration': '分散（细分领域龙头）',
            'entry_barrier': '中（技术/认证/规模）',
            'homogeneity': '中',
            'key_players': [
                '智能化：德赛西威、伯特利、华阳集团',
                '轻量化：文灿股份、爱柯迪',
                '热管理：三花智控、银轮股份',
                '传统：华域汽车、均胜电子'
            ],
            'competition_trends': [
                '跟随整车厂出海布局',
                '智能化部件国产替代',
                'Tier0.5模式兴起',
                '年降压力持续'
            ]
        },
        '电气设备': {
            'concentration': '中（各环节龙头集中）',
            'entry_barrier': '高（技术/资金/渠道）',
            'homogeneity': '中',
            'key_players': [
                '光伏：隆基、通威、晶科、晶澳、天合',
                '风电：金风科技、明阳智能',
                '储能：宁德时代、亿纬锂能、阳光电源',
                '电网：国电南瑞、许继电气'
            ],
            'competition_trends': [
                '光伏产能过剩，价格战激烈',
                '储能装机爆发，竞争加剧',
                '电网投资加速，特高压受益',
                '出海成为必选项'
            ]
        },
        '电力': {
            'concentration': '高（央企主导）',
            'entry_barrier': '极高（牌照/资金）',
            'homogeneity': '高（产品标准化）',
            'key_players': [
                '火电：华能、国电、华电、大唐',
                '水电：长江电力、华能水电',
                '核电：中国核电、中国广核',
                '新能源：三峡能源、龙源电力'
            ],
            'competition_trends': [
                '新能源装机快速增长',
                '煤电从主力向调节性电源转型',
                '电价市场化改革深化',
                '绿电交易规模扩大'
            ]
        },
        '有色金属': {
            'concentration': '中（资源端集中）',
            'entry_barrier': '高（资源/资金/环保）',
            'homogeneity': '高（大宗商品）',
            'key_players': [
                '铜：江西铜业、铜陵有色、紫金矿业',
                '铝：中国铝业、云铝股份',
                '锂：天齐锂业、赣锋锂业',
                '稀土：北方稀土、中国稀土'
            ],
            'competition_trends': [
                '资源整合加速',
                '新能源金属需求增长',
                '绿色低碳转型',
                '海外资源布局'
            ]
        },
        '小金属': {
            'concentration': '中（细分龙头集中）',
            'entry_barrier': '极高（资源/资金/海外运营能力）',
            'homogeneity': '高（标准化产品）',
            'key_players': [
                '铜/钴：洛阳钼业、华友钴业、紫金矿业',
                '钼：洛阳钼业、金钼股份',
                '钨：中钨高新、厦门钨业',
                '稀土：北方稀土、中国稀土'
            ],
            'competition_trends': [
                '海外资源争夺加剧（刚果金/南美）',
                '新能源金属（铜/钴）需求爆发',
                '纵向一体化布局（矿-冶炼-材料）',
                'ESG要求提高，中小矿企出清'
            ]
        },
        '煤炭': {
            'concentration': '高（央企+地方国企）',
            'entry_barrier': '极高（资源/资金/安全）',
            'homogeneity': '高（大宗商品）',
            'key_players': [
                '动力煤：神华、中煤、陕煤',
                '焦煤：山西焦煤、潞安环能',
                '地方国企：兖矿能源、淮北矿业'
            ],
            'competition_trends': [
                '资源整合，集中度提升',
                '长协煤占比提升',
                '智能化矿山建设',
                '新能源替代长期压力'
            ]
        },
        '钢铁': {
            'concentration': '中（宝武系主导）',
            'entry_barrier': '高（资金/环保/产能指标）',
            'homogeneity': '高（标准化产品）',
            'key_players': [
                '宝武系：宝钢股份、太钢不锈',
                '地方国企：鞍钢、首钢、河钢',
                '民营：沙钢、方大特钢'
            ],
            'competition_trends': [
                '宝武系整合加速',
                '产能置换严控新增',
                '绿色低碳转型',
                '特钢差异化竞争'
            ]
        },
        '化工': {
            'concentration': '中（细分领域龙头）',
            'entry_barrier': '中高（资金/技术/环保）',
            'homogeneity': '高（大宗化工）/低（精细化工）',
            'key_players': [
                '综合性：万华化学、恒力石化、荣盛石化',
                '农药：扬农化工、利尔化学',
                '新材料：新宙邦、天赐材料',
                '钛白粉：龙佰集团'
            ],
            'competition_trends': [
                '一体化龙头优势明显',
                '新材料国产替代',
                '环保限产常态化',
                '出海布局加速'
            ]
        },
        '建筑材料': {
            'concentration': '高（区域龙头）',
            'entry_barrier': '中（资金/矿山资源）',
            'homogeneity': '高（标准化产品）',
            'key_players': [
                '水泥：海螺水泥、中国建材、华新水泥',
                '玻璃：旗滨集团、信义玻璃',
                '消费建材：东方雨虹、北新建材'
            ],
            'competition_trends': [
                '水泥区域整合完成',
                '玻璃光伏转型',
                '消费建材集中度提升',
                '地产需求下滑冲击'
            ]
        },
        '房地产开发': {
            'concentration': '从分散走向集中（出清中）',
            'entry_barrier': '极高（资金/土地）',
            'homogeneity': '高（产品同质化）',
            'key_players': [
                '央企：保利、中海、华润、招商',
                '地方国企：建发、华发、越秀',
                '民企：万科、龙湖、滨江（少数幸存）'
            ],
            'competition_trends': [
                '民企出清，央国企主导',
                '产品力竞争取代规模竞争',
                '代建业务兴起',
                '转型运营/服务'
            ]
        },
        '食品饮料': {
            'concentration': '高（品牌龙头）',
            'entry_barrier': '高（品牌/渠道）',
            'homogeneity': '低（差异化大）',
            'key_players': [
                '白酒：茅台、五粮液、泸州老窖、汾酒',
                '调味品：海天、中炬高新、千禾',
                '乳制品：伊利、蒙牛',
                '休闲食品：洽洽、桃李、绝味'
            ],
            'competition_trends': [
                '品牌集中度持续提升',
                '健康化/功能化趋势',
                '渠道变革（零食量贩店）',
                '出海初期'
            ]
        },
        '白酒': {
            'concentration': '高（头部集中）',
            'entry_barrier': '极高（品牌/历史/产能）',
            'homogeneity': '低（香型/价位差异化）',
            'key_players': [
                '高端：茅台、五粮液、国窖1573',
                '次高端：汾酒、洋河、剑南春、郎酒',
                '区域龙头：古井贡、今世缘、迎驾贡'
            ],
            'competition_trends': [
                '高端格局稳定',
                '次高端竞争激烈',
                '酱酒热退潮',
                '渠道库存去化中'
            ]
        },
        '纺织服装': {
            'concentration': '低（分散）',
            'entry_barrier': '低',
            'homogeneity': '高（同质化）',
            'key_players': [
                '制造：申洲国际、华利集团',
                '品牌：安踏、李宁、波司登',
                '电商：SHEIN、Temu'
            ],
            'competition_trends': [
                '制造向东南亚转移',
                '品牌国潮崛起',
                '跨境电商爆发',
                '快反供应链竞争'
            ]
        },
        '轻工制造': {
            'concentration': '低（细分领域龙头）',
            'entry_barrier': '中（规模效应）',
            'homogeneity': '高',
            'key_players': [
                '家居：欧派家居、顾家家居',
                '造纸：太阳纸业、晨鸣纸业',
                '包装：裕同科技、合兴包装',
                '文具：晨光股份'
            ],
            'competition_trends': [
                '出口承压，内需为主',
                '行业集中度提升',
                '智能化/绿色化转型',
                '跨境电商渠道'
            ]
        },
        '农林牧渔': {
            'concentration': '低（养殖端集中中）',
            'entry_barrier': '中（资金/技术/防疫）',
            'homogeneity': '高（大宗商品）',
            'key_players': [
                '养殖：牧原股份、温氏股份、新希望',
                '饲料：海大集团、新希望',
                '种子：隆平高科、大北农',
                '水产：国联水产'
            ],
            'competition_trends': [
                '养殖规模化加速',
                '猪周期波动',
                '种业振兴',
                '预制菜延伸'
            ]
        },
        '银行': {
            'concentration': '高（国有大行主导）',
            'entry_barrier': '极高（牌照/资金）',
            'homogeneity': '高（产品同质化）',
            'key_players': [
                '国有行：工行、建行、农行、中行',
                '股份行：招行、兴业、平安、中信',
                '城商行：北京银行、上海银行',
                '农商行：渝农商行、沪农商行'
            ],
            'competition_trends': [
                '息差收窄，倒逼转型',
                '财富管理竞争加剧',
                '数字化转型',
                '差异化定位'
            ]
        },
        '证券': {
            'concentration': '中（头部集中）',
            'entry_barrier': '高（牌照/资金）',
            'homogeneity': '高（业务同质化）',
            'key_players': [
                '头部：中信、中信建投、中金、华泰',
                '中型：国泰君安、海通、招商、广发',
                '特色：东方财富（互联网券商）'
            ],
            'competition_trends': [
                '头部集中加速',
                '财富管理转型',
                '并购重组活跃',
                '数字化/智能化'
            ]
        },
        '保险': {
            'concentration': '高（寡头垄断）',
            'entry_barrier': '极高（牌照/资金）',
            'homogeneity': '高（产品同质化）',
            'key_players': [
                '寿险：中国人寿、平安寿险、太保寿险',
                '财险：人保财险、平安财险、太保财险',
                '健康险：平安健康、人保健康'
            ],
            'competition_trends': [
                '代理人渠道转型',
                '银保渠道重要性提升',
                '健康险/养老险增长',
                '康养生态布局'
            ]
        },
        '国防军工': {
            'concentration': '高（央企主导）',
            'entry_barrier': '极高（资质/技术/资金）',
            'homogeneity': '中',
            'key_players': [
                '航空：中航沈飞、中航西飞、航发动力',
                '航天：中国卫星、航天电子',
                '船舶：中国船舶、中船防务',
                '兵器：内蒙一机、中兵红箭'
            ],
            'competition_trends': [
                '订单持续高增长',
                '新型号批产加速',
                '产业链专业化整合',
                '军贸出口突破'
            ]
        },
        '传媒': {
            'concentration': '高（平台垄断）',
            'entry_barrier': '高（牌照/内容/资金）',
            'homogeneity': '中',
            'key_players': [
                '游戏：腾讯、网易、米哈游、三七互娱',
                '影视：万达电影、中国电影',
                '广告：分众传媒',
                '出版：中南传媒、凤凰传媒'
            ],
            'competition_trends': [
                '版号发放常态化',
                '短剧/微剧爆发',
                'AI生成内容兴起',
                '出海成为增长点'
            ]
        },
        '交通运输': {
            'concentration': '中（细分领域集中）',
            'entry_barrier': '高（资金/牌照）',
            'homogeneity': '高',
            'key_players': [
                '快递：顺丰、中通、圆通、韵达',
                '航空：国航、东航、南航、春秋',
                '铁路：京沪高铁、大秦铁路',
                '公路：宁沪高速、深高速'
            ],
            'competition_trends': [
                '价格战趋缓，盈利修复',
                '国际化布局加速',
                '智能化/绿色化',
                '综合物流转型'
            ]
        },
        '航运港口': {
            'concentration': '中（央企主导）',
            'entry_barrier': '高（资金/资源）',
            'homogeneity': '高',
            'key_players': [
                '集运：中远海控、海丰国际',
                '油运：中远海能、招商轮船',
                '港口：上港集团、宁波港、招商港口'
            ],
            'competition_trends': [
                '运价周期性波动',
                '船队大型化',
                '绿色航运转型',
                '港口自动化'
            ]
        },
        '机械设备': {
            'concentration': '中（细分领域龙头）',
            'entry_barrier': '中高（技术/资金）',
            'homogeneity': '中',
            'key_players': [
                '工程机械：三一重工、中联重科、徐工机械',
                '工业母机：海天精工、创世纪',
                '机器人：埃斯顿、汇川技术',
                '激光：锐科激光、大族激光'
            ],
            'competition_trends': [
                '国产替代加速',
                '人形机器人等新赛道',
                '出海成为增长点',
                '智能化/高端化'
            ]
        },
        '环保': {
            'concentration': '低（分散）',
            'entry_barrier': '中（技术/资金）',
            'homogeneity': '高',
            'key_players': [
                '水务：北控水务、首创环保',
                '固废：光大环境、瀚蓝环境',
                '大气：龙净环保、清新环境',
                '监测：聚光科技、先河环保'
            ],
            'competition_trends': [
                '运营业务占比提升',
                '资源化转型',
                '碳监测新业务',
                '行业整合加速'
            ]
        },
        '社会服务': {
            'concentration': '低（分散）',
            'entry_barrier': '中（资金/品牌）',
            'homogeneity': '低',
            'key_players': [
                '酒店：锦江酒店、首旅酒店、华住',
                '景区：宋城演艺、中青旅',
                '教育：中公教育、新东方',
                '人服：科锐国际、外服控股'
            ],
            'competition_trends': [
                '消费复苏分化',
                '连锁化率提升',
                '数字化转型',
                '下沉市场拓展'
            ]
        },
        '美容护理': {
            'concentration': '中（品牌分散）',
            'entry_barrier': '中（品牌/渠道）',
            'homogeneity': '低',
            'key_players': [
                '美妆：珀莱雅、贝泰妮、华熙生物',
                '医美：爱美客、昊海生科',
                '代工厂：科丝美诗、莹特丽'
            ],
            'competition_trends': [
                '国货品牌崛起',
                '功效护肤趋势',
                '线上渠道主导',
                '医美监管趋严'
            ]
        }
    }
    
    # 模糊匹配
    for key in competition_map:
        if key in industry or industry in key:
            return competition_map[key]
    
    return {
        'concentration': '待评估',
        'entry_barrier': '待评估',
        'homogeneity': '待评估',
        'key_players': ['需具体分析行业主要参与者'],
        'competition_trends': ['关注行业竞争格局变化']
    }


def get_industry_watchlist(industry):
    """获取行业关注清单"""
    watchlist_map = {
        '半导体': {
            'policy_events': [
                '美国对华芯片政策更新',
                '国产大基金三期投资动向',
                '先进制程设备进口许可',
                '半导体设备/材料国产化进展'
            ],
            'industry_events': [
                '存储芯片价格走势（DRAM/NAND）',
                'AI芯片需求变化',
                '晶圆厂产能利用率',
                '主要厂商库存去化进度'
            ],
            'data_releases': [
                '全球半导体销售额（SIA月度数据）',
                '中国集成电路进出口数据',
                '主要晶圆厂月度营收',
                '台积电/三星业绩指引'
            ]
        },
        '新能源': {
            'policy_events': [
                '新能源发电装机规划更新',
                '储能产业政策变化',
                '电网投资计划',
                '绿电交易机制完善'
            ],
            'industry_events': [
                '光伏组件价格走势',
                '硅料/碳酸锂价格变化',
                '新能源车渗透率',
                '储能招标量'
            ],
            'data_releases': [
                '月度光伏/风电装机量',
                '动力电池装车量',
                '新能源车销量',
                '电网投资完成额'
            ]
        },
        '医药': {
            'policy_events': [
                '国家医保谈判（国谈）',
                '药品/器械集采扩围',
                '创新药审评审批政策',
                '医疗反腐动态'
            ],
            'industry_events': [
                '创新药出海进展（FDA批准）',
                '主要药企管线进展',
                '医院诊疗量恢复情况',
                'CXO订单变化'
            ],
            'data_releases': [
                '医保基金收支数据',
                '新药获批数量',
                '医药制造业利润',
                '医药出口数据'
            ]
        },
        '消费': {
            'policy_events': [
                '促消费政策出台',
                '消费税改革进展',
                '节假日消费刺激',
                '消费券发放'
            ],
            'industry_events': [
                '节假日消费数据',
                '渠道库存去化',
                '新品发布/营销动态',
                '原材料价格变化'
            ],
            'data_releases': [
                '社会消费品零售总额',
                'CPI/PPI数据',
                '消费者信心指数',
                '居民可支配收入'
            ]
        },
        '地产': {
            'policy_events': [
                '房地产调控政策变化',
                '保交楼政策进展',
                '房企融资支持政策',
                '限购限贷政策优化'
            ],
            'industry_events': [
                '房企债务违约风险',
                '销售数据变化',
                '土地市场热度',
                '二手房成交情况'
            ],
            'data_releases': [
                '商品房销售面积/金额',
                '70城房价指数',
                '房地产开发投资',
                '房企到位资金'
            ]
        },
        '金融': {
            'policy_events': [
                '货币政策（降准降息）',
                'LPR调整',
                '房地产融资协调机制',
                '资本市场改革政策'
            ],
            'industry_events': [
                '信贷投放节奏',
                '息差变化',
                '资产质量压力',
                '财富管理转型进展'
            ],
            'data_releases': [
                '社融/M2数据',
                '人民币贷款数据',
                '银行业利润',
                'A股成交额'
            ]
        },
        '周期': {
            'policy_events': [
                '供给侧改革政策',
                '环保限产政策',
                '产能置换政策',
                '保供稳价政策'
            ],
            'industry_events': [
                '大宗商品价格走势',
                '库存变化',
                '下游需求恢复',
                '产能利用率'
            ],
            'data_releases': [
                'PPI数据',
                '工业增加值',
                'PMI数据',
                '主要工业品产量'
            ]
        },
        '小金属': {
            'policy_events': [
                '战略性矿产资源政策',
                '稀有金属出口管制政策',
                '海外资源开发支持政策',
                '矿产资源权益金调整'
            ],
            'industry_events': [
                'LME铜价/钴价/钼价走势',
                '刚果(金)矿山供应情况',
                '南美铜矿产量变化',
                '中国收储动态',
                'ESG合规要求变化'
            ],
            'data_releases': [
                '全球铜/钴供需平衡表',
                '中国铜/钴进口数据',
                '新能源汽车销量（钴需求）',
                '钢铁产量（钼需求）',
                '主要矿山企业产量报告'
            ]
        },
        '科技': {
            'policy_events': [
                '信创政策推进',
                'AI产业政策',
                '数据要素政策',
                '科技自立自强政策'
            ],
            'industry_events': [
                'AI大模型进展',
                '信创招标情况',
                '华为/苹果等新品发布',
                '技术突破/专利动态'
            ],
            'data_releases': [
                '软件业务收入',
                '信息技术服务收入',
                '电信业务总量',
                '数字经济核心产业增加值'
            ]
        }
    }
    
    # 模糊匹配
    for key in watchlist_map:
        if key in industry or industry in key:
            return watchlist_map[key]
    
    # 通用关注清单
    return {
        'policy_events': [
            '行业监管政策变化',
            '产业扶持政策',
            '环保/安全政策',
            '进出口政策'
        ],
        'industry_events': [
            '龙头企业动态',
            '行业供需变化',
            '价格走势',
            '技术变革'
        ],
        'data_releases': [
            '行业月度产量/销量数据',
            '行业价格指数',
            '进出口数据',
            '主要企业业绩预告'
        ]
    }


# ==================== 原有函数 ====================

def get_recent_date(months=3):
    """获取N个月前的日期"""
    return (datetime.now() - timedelta(days=30*months)).strftime('%Y%m%d')

def get_date_range(months=6):
    """获取日期范围 (start_date, end_date)，默认近6个月以覆盖更多业绩公告"""
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=30*months)).strftime('%Y%m%d')
    return start_date, end_date

def analyze_announcements(ts_code):
    """分析公告信息 - 只显示近3个月"""
    print("---")
    print(f"📰 消息面分析 - {ts_code}")
    print("---")
    
    # 获取公司基本信息
    try:
        basic = pro.stock_basic(ts_code=ts_code, fields='name,industry')
        if not basic.empty:
            company_name = basic.iloc[0]['name']
            industry = basic.iloc[0]['industry']
            print(f"\n【公司信息】")
            print(f"  公司名称: {company_name}")
            print(f"  所属行业: {industry}")
    except:
        company_name = ts_code
    
    # 【近期公告汇总】- 以全部公告为主（业绩已在基本面章节体现，此处聚焦全部公告供模型分析）
    print(f"\n【近期公告汇总 - 近2个月】")
    try:
        end_d = datetime.now().strftime('%Y%m%d')
        start_d = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')  # 近2个月
        df = pro.anns_d(ts_code=ts_code, start_date=start_d, end_date=end_d)
        if df is not None and not df.empty:
            df = df.sort_values('ann_date', ascending=False).head(20)
            print("| 公告日期 | 公告标题 | 链接 |")
            print("|:---------|:---------|:-----|")
            for _, row in df.iterrows():
                ann_date = row.get('ann_date', 'N/A')
                title = (row.get('title', '') or '')[:80]
                title = title.replace('|', '｜')
                url = (row.get('url', '') or '').strip()
                link = f"[原文]({url})" if url else "-"
                print(f"| {ann_date} | {title} | {link} |")
            print("")
            print("【公告汇总分析】")
            print("> ⚠️ **【待补充】** 请基于以上公告列表进行分析，重点关注：")
            print("> - 重大合同/订单、募集资金变更、资产收购/出售")
            print("> - 高管变动、董事会/股东会决议、股权激励")
            print("> - 诉讼/问询、业绩说明、分红送转")
            print("> - 结合公司业务与行业背景，判断对股价的潜在影响")
        else:
            print("  近2个月暂无公告数据")
    except Exception as e:
        err_msg = str(e)
        if '权限' in err_msg or 'permission' in err_msg.lower():
            print("  ⚠️ 本接口需 Tushare anns_d 单独权限")
        else:
            print(f"  获取失败: {e}")

def analyze_research_reports(ts_code):
    """分析机构研报 - 表格展示近半年最多10篇，含链接"""
    print(f"\n【机构研报 - 详细分析】")
    
    try:
        # 近6个月日期范围
        end_d = datetime.now().strftime('%Y%m%d')
        start_d = (datetime.now() - timedelta(days=180)).strftime('%Y%m%d')
        df = pro.research_report(ts_code=ts_code, start_date=start_d, end_date=end_d)
        
        if df is None or len(df) == 0:
            print("  近6个月暂无机构研报覆盖")
            return
        
        # 按日期排序，取最近10篇
        df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d', errors='coerce')
        df = df.sort_values('trade_date', ascending=False).head(10)
        
        if df.empty:
            print("  近6个月暂无研报覆盖")
            return
        
        # 表格展示：日期 | 机构 | 分析师 | 标题 | 摘要 | 链接
        print("")
        print("| 日期 | 机构 | 分析师 | 标题 | 摘要 | 链接 |")
        print("|:-----|:-----|:-------|:-----|:-----|:-----|")
        
        for _, row in df.iterrows():
            report_date = row['trade_date'].strftime('%Y-%m-%d') if pd.notna(row['trade_date']) else 'N/A'
            org = (row.get('inst_csname', '') or '')[:8]
            author = (row.get('author', '') or '')[:12]
            title = (row.get('title') or row.get('file_name', '') or '')[:50]
            title = str(title).replace('|', '｜')
            abstr = (row.get('abstr', '') or '')[:80]
            abstr = str(abstr).replace('|', '｜').replace('\n', ' ')
            abstr = abstr.strip() or '-'
            url = (row.get('url', '') or '').strip()
            link = f"[原文]({url})" if url else "-"
            print(f"| {report_date} | {org} | {author} | {title} | {abstr} | {link} |")
        
        # 简要一致性预期
        keywords_positive = ['增长', '突破', '向好', '改善', '提升', '超预期', '看好']
        keywords_negative = ['下滑', '承压', '风险', '谨慎', '下调', '低于预期']
        def _tit(x): return str(x.get('title') or x.get('file_name', '') or '')
        positive_count = sum(1 for _, r in df.iterrows() if any(kw in _tit(r) for kw in keywords_positive))
        negative_count = sum(1 for _, r in df.iterrows() if any(kw in _tit(r) for kw in keywords_negative))
        neutral_count = len(df) - positive_count - negative_count
        
        if positive_count > negative_count:
            sentiment = "偏乐观"
        elif negative_count > positive_count:
            sentiment = "偏谨慎"
        else:
            sentiment = "中性"
        print("")
        print(f"  机构情绪: {sentiment} | 积极{positive_count}份 中性{neutral_count}份 谨慎{negative_count}份")
        
    except Exception as e:
        import traceback
        print(f"  获取研报失败: {e}")
        traceback.print_exc()

def analyze_capital_changes(ts_code):
    """分析资本运作 - 近3个月"""
    print(f"\n【资本运作 - 近3个月】")
    recent_date = get_recent_date(3)
    
    # 增减持
    try:
        df = pro.stk_holdertrade(ts_code=ts_code, start_date=recent_date, limit=5)
        if not df.empty:
            print(f"\n  【增减持情况】")
            for _, row in df.iterrows():
                ann_date = row.get('ann_date', 'N/A')
                change_type = row.get('type', 'unknown')
                name = row.get('holder_name', 'unknown')
                change_vol = row.get('change_vol', 0) / 10000
                print(f"    {ann_date} | {name} {change_type} {change_vol:.2f}万股")
        else:
            print(f"\n  【增减持情况】近3个月暂无数据")
    except:
        print(f"\n  【增减持情况】获取失败")
    
    # 回购
    try:
        df = pro.repurchase(ts_code=ts_code, start_date=recent_date, limit=3)
        if not df.empty:
            print(f"\n  【回购情况】")
            for _, row in df.iterrows():
                ann_date = row['ann_date']
                repurchase_vol = row.get('repurchase_vol', 0)
                repurchase_amount = row.get('repurchase_amount', 0)
                if repurchase_vol and repurchase_vol > 0:
                    print(f"    {ann_date} | 回购 {repurchase_vol/10000:.2f}万股 / {repurchase_amount/10000:.2f}万元")
                else:
                    print(f"    {ann_date} | 公告回购计划（尚未实施）")
        else:
            print(f"\n  【回购情况】近3个月暂无数据")
    except:
        pass

def analyze_restricted_shares(ts_code):
    """分析限售股解禁 - 近3个月及未来3个月"""
    print(f"\n【限售股解禁 - 近3个月及未来3个月】")
    
    try:
        # 获取近3个月和未来3个月的解禁
        past_date = get_recent_date(3)
        future_date = (datetime.now() + timedelta(days=90)).strftime('%Y%m%d')
        
        df = pro.share_float(ts_code=ts_code, start_date=past_date, end_date=future_date, limit=10)
        
        if not df.empty:
            for _, row in df.iterrows():
                float_date = row['float_date']
                float_share = row.get('float_share', 0) / 10000
                float_ratio = row.get('float_ratio', 0)
                
                # 判断是已解禁还是待解禁
                float_dt = datetime.strptime(float_date, '%Y%m%d')
                now = datetime.now()
                status = "【已解禁】" if float_dt < now else "【待解禁】"
                
                print(f"  {status} {float_date}")
                print(f"    解禁数量: {float_share:.2f}万股")
                print(f"    解禁比例: {float_ratio:.2f}%")
        else:
            print("  近3个月及未来3个月无限售股解禁")
    except:
        print("  获取限售股解禁数据失败")

def analyze_industry_news(ts_code):
    """分析行业动态 - 深度版：政策、周期、国际形势"""
    print(f"\n---")
    print(f"【行业深度分析 - 政策/周期/国际形势】")
    print(f"---")
    
    try:
        # 获取公司基本信息
        basic = pro.stock_basic(ts_code=ts_code, fields='name,industry,area')
        if basic.empty:
            print("  获取公司信息失败")
            return
            
        company_name = basic.iloc[0]['name']
        industry = basic.iloc[0]['industry']
        area = basic.iloc[0].get('area', '未知')
        
        print(f"\n  公司名称: {company_name}")
        print(f"  所属行业: {industry}")
        print(f"  所属地区: {area}")
        
        # 1. 政策环境分析
        print(f"\n  📜 【政策环境分析】")
        print(f"  " + "-" * 66)
        
        # 获取行业政策关键词映射
        policy_keywords = get_industry_policy_keywords(industry)
        print(f"\n    【行业政策定位】")
        print(f"      行业属性: {policy_keywords.get('category', '一般行业')}")
        print(f"      政策导向: {policy_keywords.get('policy_direction', '中性')}")
        
        if policy_keywords.get('key_policies'):
            print(f"\n    【重点政策领域】")
            for policy in policy_keywords['key_policies']:
                print(f"      • {policy}")
        
        if policy_keywords.get('policy_risks'):
            print(f"\n    【政策风险点】")
            for risk in policy_keywords['policy_risks']:
                print(f"      ⚠️ {risk}")
        
        # 2. 行业周期分析
        print(f"\n  🔄 【行业周期分析】")
        print(f"  " + "-" * 66)
        
        cycle_info = get_industry_cycle_info(industry)
        print(f"\n    【周期属性】")
        print(f"      周期类型: {cycle_info.get('cycle_type', '未知')}")
        print(f"      周期位置判断: {cycle_info.get('cycle_position', '待观察')}")
        print(f"      典型周期长度: {cycle_info.get('cycle_duration', 'N/A')}")
        
        if cycle_info.get('cycle_indicators'):
            print(f"\n    【周期判断指标】")
            for indicator in cycle_info['cycle_indicators']:
                print(f"      • {indicator}")
        
        if cycle_info.get('current_phase_features'):
            print(f"\n    【当前阶段特征】")
            for feature in cycle_info['current_phase_features']:
                print(f"      • {feature}")
        
        # 3. 国际形势影响
        print(f"\n  🌍 【国际形势影响】")
        print(f"  " + "-" * 66)
        
        global_info = get_industry_global_factors(industry)
        print(f"\n    【国际贸易关联度】")
        print(f"      出口依赖度: {global_info.get('export_dependency', '中等')}")
        print(f"      进口依赖度: {global_info.get('import_dependency', '中等')}")
        print(f"      关税敏感度: {global_info.get('tariff_sensitivity', '中等')}")
        
        if global_info.get('key_export_markets'):
            print(f"\n    【主要出口市场】")
            print(f"      {', '.join(global_info['key_export_markets'])}")
        
        if global_info.get('key_import_sources'):
            print(f"\n    【主要进口来源】")
            print(f"      {', '.join(global_info['key_import_sources'])}")
        
        if global_info.get('geopolitical_risks'):
            print(f"\n    【地缘政治风险】")
            for risk in global_info['geopolitical_risks']:
                print(f"      ⚠️ {risk}")
        
        if global_info.get('global_supply_chain'):
            print(f"\n    【全球供应链位置】")
            print(f"      {global_info['global_supply_chain']}")
        
        # 4. 产业链分析
        print(f"\n  🔗 【产业链位置分析】")
        print(f"  " + "-" * 66)
        
        chain_info = get_industry_chain_info(industry)
        print(f"\n    【产业链环节】")
        print(f"      所处位置: {chain_info.get('position', '中游')}")
        print(f"      上游议价能力: {chain_info.get('upstream_power', '中等')}")
        print(f"      下游议价能力: {chain_info.get('downstream_power', '中等')}")
        
        if chain_info.get('upstream'):
            print(f"\n    【上游】{', '.join(chain_info['upstream'])}")
        if chain_info.get('downstream'):
            print(f"    【下游】{', '.join(chain_info['downstream'])}")
        
        if chain_info.get('value_distribution'):
            print(f"\n    【价值链利润分配】")
            print(f"      {chain_info['value_distribution']}")
        
        # 5. 竞争格局概览
        print(f"\n  ⚔️ 【行业竞争格局】")
        print(f"  " + "-" * 66)
        
        competition_info = get_industry_competition_info(industry)
        print(f"\n    【竞争强度】")
        print(f"      行业集中度: {competition_info.get('concentration', '分散')}")
        print(f"      进入壁垒: {competition_info.get('entry_barrier', '中等')}")
        print(f"      同质化程度: {competition_info.get('homogeneity', '中等')}")
        
        if competition_info.get('key_players'):
            print(f"\n    【主要参与者类型】")
            for player in competition_info['key_players']:
                print(f"      • {player}")
        
        if competition_info.get('competition_trends'):
            print(f"\n    【竞争趋势】")
            for trend in competition_info['competition_trends']:
                print(f"      • {trend}")
        
        # 6. 近期需关注事项
        print(f"\n  📋 【近期需关注事项】")
        print(f"  " + "-" * 66)
        
        watchlist = get_industry_watchlist(industry)
        if watchlist.get('policy_events'):
            print(f"\n    【政策事件】")
            for event in watchlist['policy_events']:
                print(f"      📌 {event}")
        
        if watchlist.get('industry_events'):
            print(f"\n    【行业事件】")
            for event in watchlist['industry_events']:
                print(f"      📌 {event}")
        
        if watchlist.get('data_releases'):
            print(f"\n    【数据发布】")
            for data in watchlist['data_releases']:
                print(f"      📊 {data}")
        
        # 7. 分析建议
        print(f"\n  💡 【分析建议】")
        print(f"  " + "-" * 66)
        
        policy_direction = policy_keywords.get('policy_direction', '中性')
        cycle_position = cycle_info.get('cycle_position', '待观察')
        
        print(f"\n    【综合判断】")
        if '扶持' in policy_direction or '鼓励' in policy_direction:
            policy_signal = "政策面偏正面"
        elif '调控' in policy_direction or '限制' in policy_direction:
            policy_signal = "政策面偏负面"
        else:
            policy_signal = "政策面中性"
        
        print(f"      • 政策信号: {policy_signal}")
        print(f"      • 周期位置: {cycle_position}")
        
        # 国际形势风险等级
        tariff_sensitivity = global_info.get('tariff_sensitivity', '中')
        geopolitical_risks = global_info.get('geopolitical_risks', [])
        
        if tariff_sensitivity == '极高' or len(geopolitical_risks) >= 3:
            global_risk = "国际形势风险较高，需密切关注"
        elif tariff_sensitivity == '高' or len(geopolitical_risks) >= 2:
            global_risk = "国际形势存在一定风险"
        else:
            global_risk = "国际形势风险相对可控"
        
        print(f"      • 国际风险: {global_risk}")
        
        print(f"\n    【投资关注点】")
        print(f"      1. 政策变化对行业的影响方向和力度")
        print(f"      2. 行业周期所处位置及拐点信号")
        print(f"      3. 国际形势变化对进出口/供应链的影响")
        print(f"      4. 产业链上下游议价能力变化")
        print(f"      5. 行业竞争格局演变趋势")
        
        print("\n---")
        
    except Exception as e:
        print(f"\n  行业分析出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 news_analysis.py <股票代码>")
        print("示例: python3 news_analysis.py 000001.SZ")
        print("      python3 news_analysis.py 600519.SH")
        sys.exit(1)
    
    ts_code = sys.argv[1]
    
    print(f"\n【消息面分析框架】")
    print(f"  本分析涵盖以下五个维度：")
    print(f"  1. 业绩公告: 业绩预告、快报、正式财报（只关注近3个月）")
    print(f"  2. 机构研报: 详细列出每篇，总结一致性预期")
    print(f"  3. 资本运作: 定增、减持、回购、激励（近3个月）")
    print(f"  4. 限售解禁: 近3个月已解禁 + 未来3个月待解禁")
    print(f"  5. 行业动态: 政策、供需、价格、技术")
    print(f"\n  ⚠️ 消息面时效性：公告只看3个月内，研报看6个月内")
    print("\n---")
    
    # 分析公告信息
    analyze_announcements(ts_code)
    
    # 分析机构研报（详细版）
    analyze_research_reports(ts_code)
    
    # 分析资本运作
    analyze_capital_changes(ts_code)
    
    # 分析限售股解禁
    analyze_restricted_shares(ts_code)
    
    # 分析行业动态
    analyze_industry_news(ts_code)
