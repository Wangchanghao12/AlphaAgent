body_rev = CS_ZSCORE(CS_WINSORIZE(NEG(TS_SUM(DIVIDE(SUBTRACT($close, $open), $open), 10)), 0.01, 0.99))
mom_decay = CS_ZSCORE(CS_WINSORIZE(SUBTRACT(TS_MEAN($ret, 120), TS_MEAN($ret, 20)), 0.01, 0.99))
wk_er = CS_ZSCORE(CS_WINSORIZE(TS_EFFICIENCY_RATIO($adj_close@1w, 8), 0.01, 0.99))
MULTIPLY(3, ADD(ADD(body_rev, mom_decay), MULTIPLY(wk_er, 3)))
