vc = TS_CORR($vwap, $volume, 15)
ner = NEG(TS_EFFICIENCY_RATIO($volume, 90))
comb = ADD(CS_ZSCORE(RANK(NEG(vc))), CS_ZSCORE(RANK(ner)))
RANK(CS_WINSORIZE(comb, 0.01, 0.99))
