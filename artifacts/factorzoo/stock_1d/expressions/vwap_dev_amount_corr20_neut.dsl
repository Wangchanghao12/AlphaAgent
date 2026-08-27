vz = TS_ZSCORE($vwap, 20)
vac = TS_CORR(vz, $amount, 20)
CS_NEUTRALIZE(RANK(CS_WINSORIZE(vac, 0.01, 0.99)), CS_BUCKET(LOG($float_cap), 10))
