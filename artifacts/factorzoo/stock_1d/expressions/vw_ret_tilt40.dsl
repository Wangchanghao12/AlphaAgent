vw_ret = DIVIDE(TS_SUM(MULTIPLY($ret, $turnover_rate_f), 40), TS_SUM($turnover_rate_f, 40))
ew_ret = TS_MEAN($ret, 40)
RANK(SUBTRACT(vw_ret, ew_ret))
