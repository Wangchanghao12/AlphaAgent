aer = TS_EFFICIENCY_RATIO($amount, 60)
vrc = TS_RANKCORR($vwap, $volume, 15)
comb = ADD(CS_ZSCORE(RANK(NEG(aer))), CS_ZSCORE(RANK(NEG(vrc))))
RANK(CS_WINSORIZE(comb, 0.01, 0.99))
