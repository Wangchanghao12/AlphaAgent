vl = TS_CORR($vwap, DELAY($volume, 1), 20)
aer = TS_EFFICIENCY_RATIO($amount, 90)
comb = ADD(CS_ZSCORE(RANK(vl)), CS_ZSCORE(RANK(aer)))
RANK(CS_WINSORIZE(comb, 0.01, 0.99))
