# 量价背离：EMA平滑量能
ret5 = TS_MEAN($ret, 5)
vol_ema = EMA($volume, 10)
vol_chg_ema = TS_PCTCHANGE(vol_ema, 5)
RANK(SUBTRACT(ret5, vol_chg_ema))
