# 20日反转×换手加速(3日vs30日)——放量超跌反弹
ret20 = TS_MEAN($ret, 20)
turn_chg = DIVIDE(SUBTRACT(TS_MEAN($turnover_rate, 3), TS_MEAN($turnover_rate, 30)), ADD(TS_MEAN($turnover_rate, 30), 0.01))
sig = MULTIPLY(NEG(CS_ZSCORE(ret20)), CS_ZSCORE(turn_chg))
RANK(CS_NEUTRALIZE(sig, CS_BUCKET(LOG($float_cap), 10)))
