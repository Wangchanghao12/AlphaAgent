import requests
import pandas as pd


class SeekAlphaAPI:
    def __init__(self, base_url="http://localhost:40024"):
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
        data = response.json()['data']

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
        return df

if __name__ == "__main__":
    api = SeekAlphaAPI()
    df = api.get_combined_data(stock_list=['000009.SZ', '000021.SZ', '000027.SZ', '600056.SH', '600060.SH', '600062.SH'], start_date='2018-01-01', end_date='2024-12-31')
    industry_df = api.get_stock_industry_l1(stock_list=['000009.SZ', '000021.SZ', '000027.SZ', '600056.SH', '600060.SH', '600062.SH'])
    # df = df.join(industry_df)
    df.to_csv('.debug/debug_df.csv', index=True)
    print(df)