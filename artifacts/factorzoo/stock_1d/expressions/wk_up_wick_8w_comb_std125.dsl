upwk = DIVIDE(SUBTRACT($high@1w, MAXIMUM($close@1w, $open@1w)), SUBTRACT($high@1w, $low@1w))
uwm = CS_WINSORIZE(TS_MEAN(upwk, 8), 0.01, 0.99)
uws = CS_WINSORIZE(TS_STD(upwk, 8), 0.01, 0.99)
CS_ZSCORE(ADD(CS_ZSCORE(uwm), MULTIPLY(CS_ZSCORE(uws), 1.25)))
