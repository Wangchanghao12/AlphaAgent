ar = RANK($amount)
aer = TS_EFFICIENCY_RATIO(ar, 60)
RANK(CS_WINSORIZE(NEG(aer), 0.01, 0.99))
