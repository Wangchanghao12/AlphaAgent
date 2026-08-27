# 250日价格分位+40日低波动+10日反转，市值中性化
raw = ADD(ADD(TS_RANK($adj_close, 250), NEG(RANK(TS_STD($ret, 40)))), NEG(RANK(TS_MEAN($ret, 10))))
CS_NEUTRALIZE(raw, CS_BUCKET(LOG($float_cap), 10))
