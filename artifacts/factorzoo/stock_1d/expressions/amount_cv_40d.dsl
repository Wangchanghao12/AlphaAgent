am_cv = DIVIDE(TS_STD($amount, 40), TS_MEAN($amount, 40))
CS_NEUTRALIZE(RANK(FILLNA(am_cv, 0.5)), CS_BUCKET(LOG($float_cap), 10))
