rcd = CS_ZSCORE(CS_WINSORIZE(TS_RANKCORR($adj_close, $adj_open, 40), 0.01, 0.99))
body_rev = CS_ZSCORE(CS_WINSORIZE(NEG(TS_SUM(DIVIDE(SUBTRACT($close, $open), $open), 10)), 0.01, 0.99))
ADD(ADD(rcd, rcd), body_rev)
