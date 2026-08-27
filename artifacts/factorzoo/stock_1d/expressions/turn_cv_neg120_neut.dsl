turn_cv = DIVIDE(TS_STD($turnover_rate, 120), TS_MEAN($turnover_rate, 120))
CS_NEUTRALIZE(RANK(NEG(CS_WINSORIZE(turn_cv, 0.01, 0.99))), CS_BUCKET(LOG($float_cap), 10))
