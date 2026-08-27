m5 = RANK(TS_PCTCHANGE($adj_close@1w, 5))
ma12 = RANK(DIVIDE(SUBTRACT($adj_close, TS_MEAN($adj_close@1w, 12)), TS_MEAN($adj_close@1w, 12)))
CS_ZSCORE(ADD(m5, ma12))
