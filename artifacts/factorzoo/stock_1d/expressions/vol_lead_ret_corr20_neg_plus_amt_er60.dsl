rc = TS_CORR($volume, DELAY($ret, 1), 20)
aer = TS_EFFICIENCY_RATIO($amount, 60)
comb = ADD(CS_ZSCORE(RANK(NEG(rc))), CS_ZSCORE(RANK(NEG(aer))))
RANK(CS_WINSORIZE(comb, 0.01, 0.99))
