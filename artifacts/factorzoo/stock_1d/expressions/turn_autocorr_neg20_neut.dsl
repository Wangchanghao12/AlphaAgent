turn_ac = TS_CORR($turnover_rate, DELAY($turnover_rate, 1), 20)
CS_NEUTRALIZE(RANK(NEG(CS_WINSORIZE(turn_ac, 0.01, 0.99))), CS_BUCKET(LOG($float_cap), 10))
