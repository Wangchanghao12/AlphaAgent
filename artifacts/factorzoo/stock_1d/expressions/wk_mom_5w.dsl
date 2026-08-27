ret_w = TS_PCTCHANGE($adj_close@1w, 5)
CS_ZSCORE(CS_WINSORIZE(ret_w, 0.01, 0.99))
