overnight = DIVIDE($open, DELAY($adj_close, 1)) - 1
intraday = DIVIDE($adj_close, $open) - 1
onid = CS_ZSCORE(CS_WINSORIZE(SUBTRACT(TS_MEAN(overnight, 10), TS_MEAN(intraday, 10)), 0.01, 0.99))
pe = CS_ZSCORE(CS_WINSORIZE(TS_PERMUTATION_ENTROPY($adj_close, 20, 4), 0.01, 0.99))
kg = CS_ZSCORE(CS_WINSORIZE(KLINE_GEOMETRY($adj_open, $adj_high, $adj_low, $adj_close, 20), 0.01, 0.99))
SUBTRACT(SUBTRACT(onid, pe), kg)
