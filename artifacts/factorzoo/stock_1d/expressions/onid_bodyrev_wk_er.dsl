overnight = DIVIDE($open, DELAY($adj_close, 1)) - 1
intraday = DIVIDE($adj_close, $open) - 1
onid = CS_ZSCORE(CS_WINSORIZE(SUBTRACT(TS_MEAN(overnight, 10), TS_MEAN(intraday, 10)), 0.01, 0.99))
body_rev = CS_ZSCORE(CS_WINSORIZE(NEG(TS_SUM(DIVIDE(SUBTRACT($close, $open), $open), 10)), 0.01, 0.99))
wk_er = CS_ZSCORE(CS_WINSORIZE(TS_EFFICIENCY_RATIO($adj_close@1w, 8), 0.01, 0.99))
ADD(ADD(onid, body_rev), wk_er)
