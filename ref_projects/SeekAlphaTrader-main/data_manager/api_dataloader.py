import requests
import pandas as pd
import json

class SeekAlphaDatabaseAPI:
    def __init__(self, base_url="http://localhost:40042"):
        self.base_url = base_url
    
    def get_combined_data(self, stock_list, start_date, end_date, 
                         include_quotes=True, include_chips=True, include_money_flow=True):
        """获取股票合并数据"""
        url = f"{self.base_url}/api/v1/data/combined"
        data = {
            "stock_list": stock_list,
            "start_date": start_date,
            "end_date": end_date,
            "include_quotes": include_quotes,
            "include_chips": include_chips,
            "include_money_flow": include_money_flow
        }
        
        response = requests.post(url, json=data)
        try:
            data = response.json()['data']
        except Exception as e:
            print(f"获取合并数据失败: {e}")
            return None

        df = pd.DataFrame(data)
        df.rename(columns={'trade_date': 'datetime', 'instrument_id': 'instrument'}, inplace=True)
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.set_index(['datetime', 'instrument'], inplace=True)
        df.sort_index(inplace=True)
        return df
    
    def get_stock_industry_l1(self, stock_list):
        """获取股票一级行业信息"""
        url = f"{self.base_url}/api/v1/data/stock-industry-l1"
        data = {"stock_list": stock_list}
        
        response = requests.post(url, json=data)
        data = response.json()['data']
        df = pd.DataFrame(data).set_index(['instrument_id'])
        # 去重
        df = df[~df.index.duplicated(keep='first')]
        df.sort_index(inplace=True)
        return df

    def get_index_data(self, index_list, start_date, end_date):
        """获取指数数据"""
        url = f"{self.base_url}/api/v1/data/index"
        data = {
            "index_list": index_list,
            "start_date": start_date,
            "end_date": end_date
        }
        
        response = requests.post(url, json=data)
        data = response.json()['data']
        df = pd.DataFrame(data).set_index(['trade_date'])
        df.drop(columns=['instrument_id'], inplace=True)
        df.rename(columns={'pct_chg': 'return'}, inplace=True)
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)
        return df
    
    def get_stock_5min_data(self, stock_code, start_date, end_date):
        """获取股票5分钟K线数据"""
        url = f"{self.base_url}/api/v1/data/stock-5min"
        data = {
            "stock_code": stock_code,
            "start_date": start_date,
            "end_date": end_date
        }
        
        response = requests.post(url, json=data)
        data = response.json()['data']
        df = pd.DataFrame(data).set_index(['instrument_id', 'trade_time'])
        df.sort_index(inplace=True)
        return df
    
    def get_sector_data(self, stock_list, start_date, end_date):
        """获取板块数据"""
        url = f"{self.base_url}/api/v1/data/sector"
        data = {
            "stock_list": stock_list,
            "start_date": start_date,
            "end_date": end_date
        }
        
        response = requests.post(url, json=data)
        data = response.json()['data']
        
        df = pd.DataFrame(data).set_index(['instrument_id'])
        df.sort_index(inplace=True)
        return df
    
    # 交易管理接口
    def insert_trade_strategy(self, strategy_name, strategy_desc=None, 
                             factor_names=None, factor_expressions=None, extra_params=None):
        """插入交易策略"""
        url = f"{self.base_url}/api/v1/trade/strategy"
        data = {
            "strategy_name": strategy_name,
            "strategy_desc": strategy_desc,
            "factor_names": factor_names,
            "factor_expressions": factor_expressions,
            "extra_params": extra_params
        }
        
        response = requests.post(url, json=data)
        return response.json()

    
    def insert_trade_signals(self, signals):
        """批量插入交易信号"""
        url = f"{self.base_url}/api/v1/trade/signals"
        data = {"signals": signals}
        
        response = requests.post(url, json=data)
        return response.json()
    
    
    def insert_account_data(self, account_id, total_asset, market_value, cash, positions, timestamp):
        """统一插入账户概览和持仓数据"""
        url = f"{self.base_url}/api/v1/trade/account-data"
        data = {
            "account_id": account_id,
            "total_asset": total_asset,
            "market_value": market_value,
            "cash": cash,
            "positions": positions,
            "timestamp": timestamp
        }
        
        response = requests.post(url, json=data)
        return response.json()

    # 查询接口
    def get_signals(self, strategy_name=None, trade_date=None, account_id=None,          page=None, page_size=None):
        """查询交易信号，支持按策略名称、日期和账户ID灵活筛选"""
        url = f"{self.base_url}/api/v1/trade/signals"
        params = {}

        if strategy_name is not None:
            params["strategy_name"] = strategy_name
        if trade_date is not None:
            params["trade_date"] = trade_date
        if account_id is not None:
            params["account_id"] = account_id
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size

        response = requests.get(url, params=params)
        return response.json()

    def get_account_summary(self, account_id, date=None, page=None, page_size=None):
        """查询账户概览"""
        url = f"{self.base_url}/api/v1/trade/account-summary"
        params = {"account_id": account_id}

        if date is not None:
            params["date"] = date
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size

        response = requests.get(url, params=params)
        return response.json()

    def get_account_positions(self, account_id, date=None, page=None, page_size=None):
        """查询账户持仓"""
        url = f"{self.base_url}/api/v1/trade/account-positions"
        params = {"account_id": account_id}

        if date is not None:
            params["date"] = date
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size

        response = requests.get(url, params=params)
        return response.json()

    def get_strategy_by_name(self, strategy_name):
        """根据策略名称查询策略"""
        url = f"{self.base_url}/api/v1/trade/strategy/by-name"
        params = {"strategy_name": strategy_name}

        response = requests.get(url, params=params)
        return response.json()

    def get_strategy_by_id(self, strategy_id):
        """根据策略ID查询策略"""
        url = f"{self.base_url}/api/v1/trade/strategy/by-id"
        params = {"strategy_id": strategy_id}

        response = requests.get(url, params=params)
        return response.json()


if __name__ == "__main__":
    # 使用示例
    api = SeekAlphaDatabaseAPI()

    # 获取合并数据
    result1 = api.get_combined_data(
        stock_list=["000006.SZ", "000008.SZ"],
        start_date="2025-05-06",
        end_date="2025-05-07"
    )

    # 获取行业信息
    result2 = api.get_stock_industry_l1(["000006.SZ", "000008.SZ"])

    # 获取指数数据
    result3 = api.get_index_data(
        index_list=["000905.SH", "000852.SH"],
        start_date="2024-12-01",
        end_date="2024-12-05"
    )

    # 获取5分钟K线数据
    result4 = api.get_stock_5min_data(
        stock_code="002281.SZ",
        start_date="2025-07-01",
        end_date="2025-07-15"
    )

    # 获取板块数据
    result5 = api.get_sector_data(
        stock_list=["885362.TI"],
        start_date="2025-07-01",
        end_date="2025-07-15"
    )

    print("合并数据:\n", result1)
    print("行业信息:\n", result2)
    print("指数数据:\n", result3)
    print("5分钟K线数据:\n", result4)
    print("板块数据:\n", result5)